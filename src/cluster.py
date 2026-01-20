"""Defines functions for building multiple scanners"""

# Standard libraries
import os
import time
from pathlib import Path, PurePosixPath

# Third-party libraries
# Project libraries
from src.config import BUILD_DIR, MASSCAN_ERROR_FILE, MASSCAN_OUTPUT_FILE
from src.masscan import MasscanCommand, MasscanResults
from src.scanner import Scanner
from src.ui import ScannerUI
from src.utils import merge_json_files


def build_cluster(
    ui: ScannerUI, cluster_name: str, instance_type: str, build_count: int, region_list: list[str]
) -> list[Scanner]:
    scanner_list = []
    ui.show_progress_bar()
    ui.update_progress_bar(current_progress=0, total_progress=build_count, description="Building scanners")
    for index in range(1, build_count + 1):
        ui.advance_progress_bar()
        scanner = Scanner(
            ui=ui,
            name=f"{cluster_name}_{index}",
            instance_type=instance_type,
            region=region_list[index % len(region_list)],
        )
        scanner_list.append(scanner)
        ui.log("debug", f"Created instance {scanner.name} with instance id: {scanner.instance_id}")
    ui.hide_progress_bar()

    # Get status
    completed_builds = []
    ui.show_progress_bar()
    ui.update_progress_bar(current_progress=0, total_progress=len(scanner_list), description="Scanner setup")
    while len(completed_builds) < len(scanner_list):
        start_time = time.time()
        for scanner in scanner_list:
            if scanner.name not in completed_builds and scanner.is_built():
                ui.advance_progress_bar()
                completed_builds.append(scanner.name)
        while time.time() - start_time < 5:
            time.sleep(0.5)
    ui.hide_progress_bar()

    return scanner_list


def start_masscan_mission(ui: ScannerUI, scanner_list: list[Scanner], masscan_command: MasscanCommand):
    ui.show_progress_bar()
    ui.update_progress_bar(
        current_progress=0, total_progress=len(scanner_list), description="Starting masscan missions"
    )
    for index, scanner in enumerate(scanner_list, start=1):
        ui.advance_progress_bar()
        scanner.start_command(
            masscan_command.create_command(shard=index, shard_total=len(scanner_list), seed="scan_cue")
        )
    ui.hide_progress_bar()


def status_masscan_mission(scanner: Scanner) -> MasscanResults | None:
    status_string = scanner.read_remote_file(MASSCAN_ERROR_FILE, tail=1)
    try:
        return MasscanResults.from_rate_string(status_string)
    except AttributeError:
        return None


def status_masscan_cluster_missions(ui: ScannerUI, scanner_list: list[Scanner]):
    ui.show_progress_bar()
    ui.update_progress_bar(current_progress=0, total_progress=100, description="Running scan missions")
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
            ui.update_progress_bar(
                current_progress=combined_result.completion,
                description=f"Running scan missions: {int(combined_result.rate * 1000):,} packet/s",
            )
            ui.log(
                "info",
                f"scan progress - {int(combined_result.rate * 1000):,} packets/s, ETA {combined_result.eta}, completion {combined_result.completion:.2f}%",
            )
    ui.hide_progress_bar()


def download_masscan_results(ui: ScannerUI, cluster_name: str, scanner_list: list[Scanner]) -> Path:
    ui.show_progress_bar()
    ui.update_progress_bar(current_progress=0, total_progress=len(scanner_list), description="Downloading results")
    result_dir = BUILD_DIR / f"{cluster_name}_output"
    os.makedirs(result_dir, exist_ok=True)
    output_file_paths = []

    # Download the raw JSON files
    for scanner in scanner_list:
        ui.advance_progress_bar()
        out_file_path = result_dir / f"{scanner.name}.json"
        output_file_paths.append(out_file_path)
        with open(file=out_file_path, mode="w", encoding="utf-8") as out_file:
            out_file.write(scanner.read_remote_file(remote_file=PurePosixPath(MASSCAN_OUTPUT_FILE)))
    ui.hide_progress_bar()

    # Merge json files
    combined_file_path = BUILD_DIR / f"{cluster_name}_combined.json"
    merge_json_files(ui=ui, files_to_merge=output_file_paths, output_file=BUILD_DIR / combined_file_path)
    ui.log("info", f"Saved results to {combined_file_path}")


def delete_cluster(ui: ScannerUI, scanner_list: list[Scanner]):
    ui.show_progress_bar()
    ui.update_progress_bar(current_progress=0, total_progress=len(scanner_list), description="Destroying scanners")
    for scanner in scanner_list:
        ui.advance_progress_bar()
        scanner.__del__()
        scanner.delete_on_exit = False
    ui.hide_progress_bar()
