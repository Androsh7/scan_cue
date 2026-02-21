"""Class for building AWS objects"""

# Standard libraries
import os
import shutil
import sys
import time
from ipaddress import IPv4Address
from pathlib import Path, PurePosixPath
from typing import Literal

# Third-party libraries
import boto3
from attrs import define, field, validators
from fabric import Connection

from scan_cue.aws import (
    create_ec2,
    create_ec2_key_pair,
    create_security_group,
    get_ami_id,
    get_default_vpc_id,
    get_vpc_subnet_id,
)

# Project libraries
from scan_cue.config import AWS_EC2_STATES, AWS_STARTUP_SCRIPT, BUILD_DIR, SSH_TIMEOUT
from scan_cue.ui import ScannerUI
from scan_cue.utils import create_ssh_key_pair


@define
class Scanner:
    # Required parameters
    ui: ScannerUI = field(validator=validators.instance_of(ScannerUI))
    name: str = field(validator=validators.instance_of(str))
    instance_type: str = field(validator=validators.instance_of(str))
    region: str = field(validator=validators.instance_of(str))
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
    command: str = field(validator=validators.instance_of(str), init=False)

    def __del__(self):
        if sys.meta_path is None:
            return
        if not getattr(self, "delete_on_exit", False):
            return
        if not hasattr(self, "instance_id"):
            return
        self.ui.log("debug", f"Destroying EC2 {self.name}")
        boto3_client = boto3.client("ec2", region_name=self.region)

        # Destroy EC2
        self.ui.log("debug", f"Destroying instance {self.instance_id}")
        boto3_client.terminate_instances(InstanceIds=[self.instance_id])

        # Destroy key pair
        self.ui.log("debug", f"Destroying key pair {self.key_pair_name}")
        boto3_client.delete_key_pair(KeyName=self.key_pair_name)

        # Delete build folder
        self.ui.log("debug", f"Destroying setup dir {self.setup_dir}")
        shutil.rmtree(self.setup_dir)

    def __attrs_post_init__(self):
        # Build setup dir
        self.setup_dir = BUILD_DIR / self.name
        os.makedirs(self.setup_dir, mode=500, exist_ok=True)

        # Build EC2
        self.ui.log("debug", f"Building ec2 {self.name}")
        self.key_pair_name = f"ssh-key-{self.name}"
        self.private_key_path, self.public_key_path = create_ssh_key_pair(output_dir=self.setup_dir)
        create_ec2_key_pair(
            ui=self.ui, region=self.region, key_pair_name=self.key_pair_name, public_key_path=self.public_key_path
        )
        self.ami_id = get_ami_id(region=self.region)
        self.vpc_id = get_default_vpc_id(region=self.region)
        self.security_group_id = create_security_group(ui=self.ui, region=self.region, vpc_id=self.vpc_id)
        self.subnet_id = get_vpc_subnet_id(region=self.region, vpc_id=self.vpc_id)
        self.instance_id = create_ec2(
            region=self.region,
            ami_id=self.ami_id,
            instance_type=self.instance_type,
            key_pair_name=self.key_pair_name,
            startup_script=AWS_STARTUP_SCRIPT,
            subnet_id=self.subnet_id,
            security_group_id=self.security_group_id,
            name=self.name,
        )

    def connection(self) -> Connection:
        """Create a fabric connection object"""
        return Connection(
            host=str(self.public_ip_address),
            user="ec2-user",
            port=22,
            connect_timeout=SSH_TIMEOUT,
            connect_kwargs={
                "key_filename": str(self.private_key_path),
            },
        )

    def cloudinit_status(self, retries: int = 2) -> bool:
        for attempt in range(retries + 1):
            try:
                with self.connection() as conn:
                    cloud_init_status = conn.run("cloud-init status", hide="both").stdout.strip().split(" ")[1]
                if cloud_init_status != "done":
                    self.ui.log("debug", f"{self.name} cloud-init status is {cloud_init_status}")
                    return False
                return True
            except (OSError, EOFError) as ex:
                self.ui.log("warning", f"Attempt to status {self.name} cloud-init status failed with error: {ex}")
                if attempt >= retries:
                    raise
                time.sleep(0.5 * (attempt + 1))

    def is_built(self) -> bool:
        """Returns True if the instance is built"""
        boto3_client = boto3.client("ec2", region_name=self.region)

        # Describe instance
        instance_describe_dict = boto3_client.describe_instances(InstanceIds=[self.instance_id])["Reservations"][0][
            "Instances"
        ][0]
        self.instance_state = instance_describe_dict["State"]["Name"]
        if self.instance_state == "pending":
            self.ui.log("debug", f'{self.name} instance state is "pending"')
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
            self.ui.log("debug", f"{self.name} instance status is not present")
            return False
        system_status = status[0]["SystemStatus"]["Status"]
        instance_status = status[0]["InstanceStatus"]["Status"]
        if system_status != "ok" or instance_status != "ok":
            self.ui.log("debug", f'{self.name} instance_status="{instance_status}", system_status="{instance_status}"')
            return False

        # Set public and private IP address
        if instance_describe_dict.get("PrivateIpAddress") is not None:
            self.private_ip_address = IPv4Address(instance_describe_dict["PrivateIpAddress"])
        if instance_describe_dict.get("PublicIpAddress") is not None:
            self.public_ip_address = IPv4Address(instance_describe_dict["PublicIpAddress"])

        # Validate cloud-init status
        return self.cloudinit_status()

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
            self.command = command

    def is_tmux_running(self, retries: int = 2) -> bool:
        """Returns True if the tmux session is still running"""
        for attempt in range(retries + 1):
            try:
                with self.connection() as conn:
                    result = conn.run(
                        "tmux has-session -t scan",
                        warn=True,
                        hide="both",
                    )
                    self.ui.log(
                        "debug",
                        f"{self.name} - tmux session running: {result.ok}, stdout: {result.stdout}, stderr: {result.stderr}",
                    )
                    return result.ok
            except (OSError, EOFError) as ex:
                self.ui.log("warning", f"Attempt to status {self.name} tmux status failed with error: {ex}")
                if attempt >= retries:
                    raise
                time.sleep(1 * (attempt + 1))

    def read_remote_file(self, remote_file: PurePosixPath, tail: int = None, retries: int = 2) -> str:
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
        for attempt in range(retries + 1):
            try:
                with self.connection() as conn:
                    remote_file_str = conn.run(command, hide="both").stdout.strip()
                return remote_file_str
            except (OSError, EOFError) as ex:
                self.ui.log(
                    "warning", f"Attempt to read remote file {remote_file} on {self.name} failed with error: {ex}"
                )
                if attempt >= retries:
                    raise
                time.sleep(1 * (attempt + 1))
