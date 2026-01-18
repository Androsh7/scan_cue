"""Defines AWS queries"""

# Third-party libraries
import boto3
from loguru import logger
from tqdm import tqdm


def load_regions() -> list[str]:
    """Returns a dictionary of AWS regions and their availability zones"""
    logger.info("Loading AWS regions")
    boto3_client = boto3.client("ec2")

    # Describe regions
    logger.debug("Running boto3 describe_regions")
    region_dict = boto3_client.describe_regions()
    out_list = []
    for region_subdict in region_dict["Regions"]:
        out_list.append(region_subdict["RegionName"])

    return set(out_list)


def list_all_scanners() -> list[dict[str, str]]:
    logger.info("Listing all Scan Cue scanner instances")
    out_list = []
    for region in tqdm(load_regions(), desc="Checking AWS regions", unit="region"):
        logger.debug(f"running boto3 describe_instances for {region}")
        boto3_client = boto3.client("ec2", region_name=region)
        paginator = boto3_client.get_paginator("describe_instances")
        for page in paginator.paginate(Filters=[{"Name": "tag:Type", "Values": ["scan_cue_scanner"]}]):
            for reservation in page["Reservations"]:
                for instance in reservation["Instances"]:
                    if instance["State"]["Name"] != "terminated":
                        logger.info(
                            f"Found instance {instance['InstanceId']} in region {region} with state {instance['State']['Name']}"
                        )
                        out_list.append(
                            {"id": instance["InstanceId"], "key_pair": instance.get("KeyName"), "region": region}
                        )
    return out_list
