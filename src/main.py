"""Main logic"""

# Standard libraries
import argparse
import os
import sys
from pathlib import Path

# Third-party libraries
import boto3
from loguru import logger

# Project libraries
from aws_query import list_all_scanners
from cluster import (
    build_cluster,
    download_masscan_results,
    start_masscan_mission,
    status_masscan_mission,
)
from config import AWS_REGION_SET, BUILD_DIR, VERSION
from masscan import MasscanCommand


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        prog="Scan Cue", description="Orchestration tool for masscan and nmap using AWS assets"
    )
    parser.add_argument(
        "--version", action="version", version=f"Scan Cue v{VERSION}", help="Displays the version of Scan Cue"
    )
    parser.add_argument(
        "--build-dir", type=Path, default=BUILD_DIR, help=f"Build directory for Scan Cue, default: {BUILD_DIR}"
    )
    parser.add_argument("--list-all-scanners", action="store_true", help="Shows all scanners")
    parser.add_argument("--destroy-all-scanners", action="store_true", help="Destroys all scanners")
    args = parser.parse_args()
    if args.list_all_scanners or args.destroy_all_scanners:
        scanner_list = list_all_scanners(AWS_REGION_SET)
        if scanner_list is None:
            logger.info("No scanners found")
        else:
            logger.info(f"Found {len(scanner_list)} active scanners: {scanner_list}")
        if args.destroy_all_scanners:
            for scanner in scanner_list:
                instance_id = scanner["id"]
                region = scanner["region"]
                key_name = scanner["key_pair"]

                # Delete the instance
                logger.info(f"Deleting EC2 {instance_id} in region {region} with key {key_name}")
                boto3_client = boto3.client("ec2", region_name=region)
                boto3_client.terminate_instances(InstanceIds=[instance_id])
                if key_name is not None:
                    boto3_client.delete_key_pair(KeyName=key_name)
        sys.exit()

    # Make configuration dir
    os.makedirs(args.build_dir, mode=500, exist_ok=True)

    cluster_name = "test_cluster_16"
    scanner_list = build_cluster(
        cluster_name=cluster_name,
        instance_type="t4g.nano",
        build_count=20,
        region_list=["us-west-2"],
    )
    masscan_command = MasscanCommand(
        ip_include_list=["1.1.1.1/0"], port_list=["80,443,8080,8443"], rate=25000000, retries=3
    )
    start_masscan_mission(scanner_list, masscan_command=masscan_command)
    while True:
        status = status_masscan_mission(scanner_list)
        logger.info(
            f"cluster progress - {status.completion:.2f}%, ETA {status.eta}, {int(status.rate * 1000):,} packet/s, found {status.found}"
        )
        if status is None:
            continue
        if status.completion >= 100:
            break
    download_masscan_results(cluster_name=cluster_name, scanner_list=scanner_list)


if __name__ == "__main__":
    main()
