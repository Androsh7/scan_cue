"""Defines functions for building multiple scanners"""

# Standard libraries
import os
import time
from datetime import timedelta
from pathlib import Path, PurePosixPath
from typing import Literal

# Third-party libraries
from loguru import logger
from tqdm import tqdm

# Project libraries
from config import AWS_REGION_SET, BUILD_DIR, MASSCAN_ERROR_FILE, MASSCAN_OUTPUT_FILE
from masscan import MasscanCommand, MasscanResults
from scanner import Scanner


def build_cluster(
    cluster_name: str, instance_type: str, build_count: int, region_list: list[Literal[AWS_REGION_SET]]
) -> list[Scanner]:
    scanner_list = []

    # Build all
    for index in tqdm(range(1, build_count + 1), unit="scanner", desc="Building scanners"):
        scanner_list.append(
            Scanner(
                name=f"{cluster_name}_{index}",
                instance_type=instance_type,
                region=region_list[index % len(region_list)],
            )
        )

    # Get status
    completed_builds = []
    with tqdm(total=len(scanner_list), desc="Scanner setup", unit="scanner") as progress_bar:
        while len(completed_builds) < len(scanner_list):
            start_time = time.time()
            for scanner in scanner_list:
                if scanner.name not in completed_builds and scanner.is_built():
                    progress_bar.update()
                    completed_builds.append(scanner.name)
            while time.time() - start_time < 15:
                time.sleep(0.5)

    return scanner_list


def start_masscan_mission(scanner_list: list[Scanner], masscan_command: MasscanCommand):
    for index, scanner in enumerate(tqdm(scanner_list, desc="Starting scan missions", unit="mission"), start=1):
        scanner.start_command(
            masscan_command.create_command(shard=index, shard_total=len(scanner_list), seed="scan_cue")
        )


def status_masscan_mission(scanner_list: list[Scanner]) -> MasscanResults:
    total_found = 0
    total_rate = 0.0
    total_completion = 0.0
    total_eta = 0
    count = 0

    for scanner in scanner_list:
        status_string = scanner.read_remote_file(MASSCAN_ERROR_FILE, tail=1)
        try:
            results = MasscanResults.from_rate_string(status_string)
            total_found += results.found
            total_rate += results.rate
            total_completion += results.completion
            total_eta += results.eta.total_seconds()
            count += 1
        except AttributeError:
            pass

    return MasscanResults(
        rate=total_rate,
        completion=total_completion / count if count else 0,
        eta=timedelta(seconds=int(total_eta / count if count else 1)),
        found=total_found,
    )


def download_masscan_results(cluster_name: str, scanner_list: list[Scanner]) -> Path:
    result_dir = BUILD_DIR / f"{cluster_name}_output"
    os.makedirs(result_dir, exist_ok=True)
    for scanner in tqdm(scanner_list, unit="scanner", desc="saving output"):
        out_file_path = result_dir / f"{scanner.name}.json"
        with open(file=out_file_path, mode="w", encoding="utf-8") as out_file:
            out_file.write(scanner.read_remote_file(remote_file=PurePosixPath(MASSCAN_OUTPUT_FILE)))
    logger.info(f"Saved results to {result_dir}")
