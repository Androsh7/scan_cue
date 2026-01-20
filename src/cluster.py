"""Defines functions for building multiple scanners"""

# Standard libraries
import os
import time
from pathlib import Path, PurePosixPath

# Third-party libraries
from loguru import logger
from tqdm import tqdm

# Project libraries
from src.config import BUILD_DIR, MASSCAN_ERROR_FILE, MASSCAN_OUTPUT_FILE
from src.masscan import MasscanCommand, MasscanResults
from src.scanner import Scanner
from src.utils import merge_json_files


def build_cluster(cluster_name: str, instance_type: str, build_count: int, region_list: list[str]) -> list[Scanner]:
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


def status_masscan_mission(scanner: Scanner) -> MasscanResults | None:
    status_string = scanner.read_remote_file(MASSCAN_ERROR_FILE, tail=1)
    try:
        return MasscanResults.from_rate_string(status_string)
    except AttributeError:
        return None


def status_masscan_cluster_missions(scanner_list: list[Scanner]):
    completed_scans = []
    while len(completed_scans) < len(scanner_list):
        result_list = []
        for scanner in scanner_list:
            if scanner.name in completed_scans:
                continue
            status = status_masscan_mission(scanner)
            if (status is None or status.completion >= 100) and not scanner.is_tmux_running():
                completed_scans.append(scanner.name)
                continue
            elif status is not None:
                result_list.append(status)
        if len(result_list) > 0:
            combined_result = MasscanResults.from_result_list(result_list)
            logger.info(
                f"scan progress - {int(combined_result.rate * 1000):,} packets/s, ETA {combined_result.eta}, completion {combined_result.completion:.2f}%"
            )


def download_masscan_results(cluster_name: str, scanner_list: list[Scanner]) -> Path:
    result_dir = BUILD_DIR / f"{cluster_name}_output"
    os.makedirs(result_dir, exist_ok=True)
    output_file_paths = []

    # Download the raw JSON files
    for scanner in tqdm(scanner_list, unit="scanner", desc="downloading results"):
        out_file_path = result_dir / f"{scanner.name}.json"
        output_file_paths.append(out_file_path)
        with open(file=out_file_path, mode="w", encoding="utf-8") as out_file:
            out_file.write(scanner.read_remote_file(remote_file=PurePosixPath(MASSCAN_OUTPUT_FILE)))

    # Merge json files
    combined_file_path = BUILD_DIR / f"{cluster_name}_combined.json"
    merge_json_files(files_to_merge=output_file_paths, output_file=BUILD_DIR / combined_file_path)
    logger.info(f"Saved results to {combined_file_path}")


def delete_cluster(scanner_list: list[Scanner]):
    for scanner in tqdm(scanner_list, unit="scanner", desc="destroying scanners"):
        scanner.__del__()
        scanner.delete_on_exit = False
