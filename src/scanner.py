"""Class for building AWS objects"""

# Standard libraries
import os
import shutil
import sys
from ipaddress import IPv4Address
from pathlib import Path, PurePosixPath
from typing import Literal

# Third-party libraries
import boto3
from attrs import define, field, validators
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fabric import Connection
from loguru import logger

# Project libraries
from config import AWS_EC2_STATES, AWS_REGION_SET, AWS_SSM_PROFILE_NAME, AWS_STARTUP_SCRIPT, BUILD_DIR, SSH_TIMEOUT


@define
class Scanner:
    # Required parameters
    name: str = field(validator=validators.instance_of(str))
    instance_type: str = field(validator=validators.instance_of(str))
    region: Literal[AWS_REGION_SET] = field(
        validator=validators.and_(validators.instance_of(str), validators.in_(AWS_REGION_SET))
    )
    delete_on_exit: bool = field(default=True, validator=validators.instance_of(bool))

    # Build configs
    ami_id: str = field(validator=validators.instance_of(str), init=False)
    setup_dir: Path = field(validator=validators.instance_of(Path), init=False)
    instance_id: str = field(validator=validators.instance_of(str), init=False)
    vpc_id: str = field(validator=validators.instance_of(str), init=False)
    subnet_id: str = field(validator=validators.instance_of(str), init=False)
    security_group_id: str = field(validator=validators.instance_of(str), init=False)
    key_pair_name: str = field(validator=validators.instance_of(str), init=False)
    public_key_path: Path = field(validator=validators.instance_of(Path), init=False)
    private_key_path: Path = field(validator=validators.instance_of(Path), init=False)

    # Runtime data
    instance_state: Literal[AWS_EC2_STATES] = field(
        validator=validators.and_(validators.instance_of(str), validators.in_(AWS_EC2_STATES)), init=False
    )
    private_ip_address: IPv4Address = field(converter=IPv4Address, init=False)
    public_ip_address: IPv4Address = field(converter=IPv4Address, init=False)

    # Scan data
    command_id: str = field(validator=validators.instance_of(str), init=False)
    command: str = field(validator=validators.instance_of(str), init=False)
    command_status: str = field(validator=validators.instance_of(str), init=False)

    def _create_ssh_key_pair(self, boto3_client: any):
        """Builds an ssh rsa key pair"""
        # Generate a private key
        key = rsa.generate_private_key(backend=default_backend(), public_exponent=65537, key_size=2048)

        # Serialize the private key to PEM format
        private_key = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )

        # Serialize the public key to OpenSSH format
        public_key = key.public_key().public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH,
        )

        # Write the private key to a file
        self.private_key_path = self.setup_dir / "private_rsa.key"
        with open(self.private_key_path, "wb") as private_key_file:
            private_key_file.write(private_key)

        # Write the public key to a file
        self.public_key_path = self.setup_dir / "public_rsa.key"
        with open(self.public_key_path, "wb") as public_key_file:
            public_key_file.write(public_key)

        # Create an AWS key pair
        self.key_pair_name = f"key-pair-{self.name}"
        try:
            boto3_client.delete_key_pair(KeyName=self.key_pair_name)
            logger.debug(f"Deleted existing key pair {self.key_pair_name}")
        except boto3.ClientError as ex:
            if ex.response["Error"]["Code"] != "InvalidKeyPair.NotFound":
                raise
        boto3_client.import_key_pair(
            KeyName=self.key_pair_name,
            PublicKeyMaterial=public_key,
        )
        logger.debug(
            f'Creating key pair: private_path="{self.private_key_path}", public_path="{self.public_key_path}", KeyName="{self.key_pair_name}"'
        )

    def _set_vpc(self, boto3_client: any):
        """Uses the default VPC"""
        vpc_response = boto3_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"][0]
        self.vpc_id = vpc_response["VpcId"]
        logger.debug(f"Using VPC: {self.vpc_id}")

    def _set_subnet(self, boto3_client: any):
        subnet_response = boto3_client.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [self.vpc_id]}])[
            "Subnets"
        ][0]
        self.subnet_id = subnet_response["SubnetId"]
        logger.debug(f"Using Subnet: {self.subnet_id}")

    def _set_security_group(self, boto3_client: any):
        security_group_query_response = boto3_client.describe_security_groups(
            Filters=[
                {"Name": "group-name", "Values": ["scan-cue-ssh-only"]},
                {"Name": "vpc-id", "Values": [self.vpc_id]},
            ]
        )
        if security_group_query_response["SecurityGroups"]:
            self.security_group_id = security_group_query_response["SecurityGroups"][0]["GroupId"]
            logger.debug(f"Using existing security group: {self.security_group_id}")
        else:
            security_group_build_response = boto3_client.create_security_group(
                GroupName="scan-cue-ssh-only",
                Description="Allow ssh access (Scan Cue)",
                VpcId=self.vpc_id,
            )
            self.security_group_id = security_group_build_response["GroupId"]

            # Add ssh access to the security group
            logger.debug(f"Created security group: {self.security_group_id}")
            boto3_client.authorize_security_group_ingress(
                GroupId=self.security_group_id,
                IpPermissions=[
                    {
                        "IpProtocol": "tcp",
                        "FromPort": 22,
                        "ToPort": 22,
                        "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                    }
                ],
            )
            logger.debug(f"Added ssh ingress rule to security group: {self.security_group_id}")

    def _create_ec2(self, boto3_client: any):
        self._set_vpc(boto3_client)
        self._set_subnet(boto3_client)
        self._set_security_group(boto3_client)
        self._create_ssh_key_pair(boto3_client)

        # Get the AMI ID for the region
        self.ami_id = boto3.client("ssm", region_name=self.region).get_parameter(
            Name="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
        )["Parameter"]["Value"]
        logger.debug(f"Using AMI ID: {self.ami_id}")

        build_response = boto3_client.run_instances(
            ImageId=self.ami_id,
            InstanceType=self.instance_type,
            KeyName=self.key_pair_name,
            MinCount=1,
            MaxCount=1,
            UserData=AWS_STARTUP_SCRIPT,
            IamInstanceProfile={"Name": AWS_SSM_PROFILE_NAME},
            NetworkInterfaces=[
                {
                    "DeviceIndex": 0,
                    "SubnetId": self.subnet_id,
                    "Groups": [self.security_group_id],
                    "AssociatePublicIpAddress": True,
                }
            ],
            TagSpecifications=[
                {
                    "ResourceType": "instance",
                    "Tags": [
                        {"Key": "Name", "Value": self.name},
                        {"Key": "Type", "Value": "scan_cue_scanner"},
                    ],
                }
            ],
        )
        self.instance_id = build_response["Instances"][0]["InstanceId"]
        logger.debug(f"Created EC2: {self.instance_id}")

    def __del__(self):
        if sys.meta_path is None:
            return
        if not getattr(self, "delete_on_exit", False):
            return
        if not hasattr(self, "instance_id"):
            return
        logger.debug(f"Destroying EC2 {self.name}")
        boto3_client = boto3.client("ec2", region_name=self.region)

        # Destroy EC2
        logger.debug(f"Destroying instance {self.instance_id}")
        boto3_client.terminate_instances(InstanceIds=[self.instance_id])

        # Destroy key pair
        logger.debug(f"Destroying key pair {self.key_pair_name}")
        boto3_client.delete_key_pair(KeyName=self.key_pair_name)

        # Delete build folder
        logger.debug(f"Destroying setup dir {self.setup_dir}")
        shutil.rmtree(self.setup_dir)

    def __attrs_post_init__(self):
        self.setup_dir = BUILD_DIR / self.name
        os.makedirs(self.setup_dir, mode=500, exist_ok=True)
        logger.debug(f"Building ec2 {self.name}")
        boto3_client = boto3.client("ec2", region_name=self.region)
        self._create_ec2(boto3_client)

    def connection(self) -> Connection:
        """Create a fabric connection object"""
        return Connection(
            host=str(self.public_ip_address),
            user="ec2-user",
            port=22,
            connect_kwargs={
                "key_filename": str(self.private_key_path),
                "timeout": SSH_TIMEOUT,
            },
        )

    def is_built(self) -> bool:
        """Returns True if the instance is built"""
        boto3_client = boto3.client("ec2", region_name=self.region)

        # Describe instance
        instance_describe_dict = boto3_client.describe_instances(InstanceIds=[self.instance_id])["Reservations"][0][
            "Instances"
        ][0]
        self.instance_state = instance_describe_dict["State"]["Name"]
        if self.instance_state == "pending":
            logger.debug(f'{self.name} instance state is "pending"')
            return False
        if self.instance_state not in ["pending", "running"]:
            raise KeyError(f"Unexpected instance state {self.instance_state}")

        # Get instance status
        instance_status_dict = boto3_client.describe_instance_status(
            InstanceIds=[self.instance_id],
            IncludeAllInstances=True,
        )
        status = instance_status_dict.get("InstanceStatuses")
        if status is None:
            logger.debug(f"{self.name} instance status is not present")
            return False
        system_status = status[0]["SystemStatus"]["Status"]
        instance_status = status[0]["InstanceStatus"]["Status"]
        if system_status != "ok" or instance_status != "ok":
            logger.debug(f'{self.name} instance_status="{instance_status}", system_status="{instance_status}"')
            return False

        # Set public and private IP address
        if instance_describe_dict.get("PrivateIpAddress") is not None:
            self.private_ip_address = IPv4Address(instance_describe_dict["PrivateIpAddress"])
        if instance_describe_dict.get("PublicIpAddress") is not None:
            self.public_ip_address = IPv4Address(instance_describe_dict["PublicIpAddress"])

        # Validate cloud-init status
        with self.connection() as conn:
            cloud_init_status = conn.run("cloud-init status", hide="both").stdout.strip().split(" ")[1]
        if cloud_init_status != "done":
            logger.debug(f"{self.name} cloud-init status is {cloud_init_status}")
            return False
        return True

    def get_state(self) -> str:
        """Returns the EC2 state"""
        boto3_client = boto3.client("ec2", region_name=self.region)
        instance_dict = boto3_client.describe_instances(InstanceIds=[self.instance_id])["Reservations"][0]["Instances"][
            0
        ]
        self.instance_state = instance_dict["State"]["Name"]
        return self.instance_state

    def start_command(self, command: str):
        """Sends a command to run on the instance

        Args:
            command: The command to run as a list
            timeout_seconds: The time until the command is considered timed out
        """
        with self.connection() as conn:
            conn.run(f'tmux new -s scan -d "{command}"', hide="both")

    def read_remote_file(self, remote_file: PurePosixPath, tail: int = None) -> str:
        """Returns the content of a remote file

        Args:
            remote_file: The remote file path
            tail: Number of lines to return, if None return all lines

        Returns:
            Content of the file
        """
        if tail is not None:
            command = f"sed 's/\\r/\\n/g' {remote_file} | tail -n {tail}"
        else:
            command = f"cat {remote_file}"
        with self.connection() as conn:
            remote_file_str = conn.run(command, hide="both").stdout.strip()
        return remote_file_str
