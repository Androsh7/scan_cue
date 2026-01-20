"""Main logic"""

# Standard libraries
import argparse
import os
import sys
from pathlib import Path

# Third-party libraries
import boto3
from loguru import logger
from tqdm import tqdm

# Project libraries
from src.aws_query import list_all_scanners
from src.cluster import (
    build_cluster,
    delete_cluster,
    download_masscan_results,
    start_masscan_mission,
    status_masscan_cluster_missions,
)
from src.config import (
    BUILD_DIR,
    DEFAULT_CLUSTER_NAME,
    DEFAULT_EC2_TYPE,
    DEFAULT_IP_EXCLUDE_LIST,
    DEFAULT_MASSCAN_RATE,
    DEFAULT_MASSCAN_RETRIES,
    VERSION,
)
from src.masscan import MasscanCommand


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
    parser.add_argument(
        "--name", type=str, default=DEFAULT_CLUSTER_NAME, help=f"Name of the cluster, default: {DEFAULT_CLUSTER_NAME}"
    )
    parser.add_argument("--ip", action="append", dest="ips", help="List of IP addresses to scan")
    parser.add_argument(
        "--exclude-ip",
        action="append",
        default=DEFAULT_IP_EXCLUDE_LIST,
        dest="exclude_ips",
        help=f"List of IP addresses to exclude, default: {DEFAULT_IP_EXCLUDE_LIST}",
    )
    parser.add_argument("--port", action="append", dest="ports", help="List of ports to scan")
    parser.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_MASSCAN_RETRIES,
        help=f"Number of retries for masscan, default: {DEFAULT_MASSCAN_RETRIES}",
    )
    parser.add_argument(
        "--rate",
        type=int,
        default=DEFAULT_MASSCAN_RATE,
        help=f"Max rate of scanning in packets-per-second, default: {DEFAULT_MASSCAN_RATE:,}",
    )
    parser.add_argument("--banners", action="store_true", help='Enables the "--banners" flag for masscan')
    parser.add_argument(
        "--region",
        action="append",
        dest="regions",
        help="The AWS region list to use, if multiple regions are specified agents will be assigned round-robin",
    )
    parser.add_argument("--scanner-count", type=int, help="The number of scanners to build")
    parser.add_argument(
        "--scanner-type",
        type=str,
        default=DEFAULT_EC2_TYPE,
        help=f'The ec2 device type to use, default: "{DEFAULT_EC2_TYPE}"',
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        choices=["trace", "debug", "info", "warning", "critical"],
        help='Sets the application log-level, default: "info"',
    )
    args = parser.parse_args()

    # Set log-level
    logger.remove()
    logger.add(
        sys.stdout,
        level=args.log_level.upper(),
    )

    # List and/or destroy scanners
    if args.list_all_scanners or args.destroy_all_scanners:
        scanner_list = list_all_scanners()
        if scanner_list is None:
            logger.info("No scanners found")
        else:
            logger.info(f"Found {len(scanner_list)} active scanners: {scanner_list}")
        if args.destroy_all_scanners and len(scanner_list) > 0:
            for scanner in tqdm(scanner_list, desc="destroying scanners", unit="scanner"):
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

    # Handle missing inputs
    if args.ips is None:
        parser.error("No IPs were specified")
    if args.ports is None:
        parser.error("No ports were specified")

    cluster_name = args.name
    masscan_command = MasscanCommand(
        ip_include_list=args.ips,
        ip_exclude_list=args.exclude_ips,
        port_list=args.ports,
        rate=args.rate,
        retries=args.retries,
        banner=args.banners,
    )
    logger.info(f'masscan command: "{" ".join(masscan_command.create_base_command())}"')
    scanner_list = build_cluster(
        cluster_name=cluster_name,
        instance_type="t4g.nano",
        build_count=args.scanner_count,
        region_list=args.regions,
    )
    start_masscan_mission(scanner_list, masscan_command=masscan_command)
    status_masscan_cluster_missions(scanner_list)
    download_masscan_results(cluster_name=cluster_name, scanner_list=scanner_list)
    delete_cluster(scanner_list)


if __name__ == "__main__":
    main()
