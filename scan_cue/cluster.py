"""Defines functions for building multiple scanners"""

# Standard libraries
import csv
import json
import time
from pathlib import Path, PurePosixPath

# Third-party libraries
# Project libraries
from scan_cue.config import BUILD_DIR, MASSCAN_ERROR_FILE, MASSCAN_OUTPUT_FILE
from scan_cue.masscan import MasscanCommand, MasscanResults
from scan_cue.scanner import Scanner
from scan_cue.ui import ScannerUI
from scan_cue.utils import merge_json_files


def build_cluster(
    ui: ScannerUI, cluster_name: str, instance_type: str, build_count: int, region_list: list[str]
) -> list[Scanner]:
    """Build a cluster of EC2s

    Args:
        ui: UI object
        cluster_name: Name of the cluster
        instance_type: The instance type, I.E: "t4g.nano"
        build_count: The number of instances to build
        region_list: The list of regions to pick from

    Returns:
        List of scanners
    """
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
            ui.advance_progress_bar(0)
            if scanner.name not in completed_builds and scanner.is_built():
                completed_builds.append(scanner.name)
        while time.time() - start_time < 5:
            time.sleep(0.5)
    ui.hide_progress_bar()

    return scanner_list


def start_masscan_mission(ui: ScannerUI, scanner_list: list[Scanner], masscan_command: MasscanCommand):
    """Starts masscan missions across a cluster

    Args:
        ui: UI object
        scanner_list: The list of scanners
        masscan_command: The masscan command object
    """
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
    """Status a masscan mission on a scanner

    Args:
        scanner: The scanner to status

    Returns:
        The masscan progress object or None if the progress could not be parsed
    """
    status_string = scanner.read_remote_file(MASSCAN_ERROR_FILE, tail=1)
    try:
        return MasscanResults.from_rate_string(status_string)
    except AttributeError:
        return None


def status_masscan_cluster_missions(ui: ScannerUI, scanner_list: list[Scanner]):
    """Runs status_masscan_mission across a cluster

    Args:
        ui: The UI object
        scanner_list: The list of scanners
    """
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


def download_masscan_results(
    ui: ScannerUI, scanner_list: list[Scanner], output_file_path: Path
):
    """Download masscan results and combine them into a csv file

    Args:
        ui: The UI object
        scanner_list: The list of scanners
        output_file_path: The output path to the csv
    """
    ui.show_progress_bar()
    ui.update_progress_bar(current_progress=0, total_progress=len(scanner_list), description="Downloading results")

    # Download the raw JSON files and write them to a CSV file
    with open(file=output_file_path, mode="w", encoding="utf-8", newline="") as out_file:
        writer = csv.writer(out_file)
        writer.writerow(["ip", "port", "timestamp", "ttl", "banner"])
        for scanner in scanner_list:
            ui.advance_progress_bar()
            masscan_dict_list = json.loads(scanner.read_remote_file(remote_file=PurePosixPath(MASSCAN_OUTPUT_FILE)))
            try:
                for masscan_dict in masscan_dict_list:
                    ip = masscan_dict["ip"]
                    timestamp = masscan_dict["timestamp"]
                    for port_dict in masscan_dict["ports"]:
                        port = port_dict["port"]
                        ttl = port_dict["ttl"]
                        writer.writerow(
                            [
                                ip,
                                port,
                                timestamp,
                                ttl,
                                json.dumps(port_dict["service"]) if port_dict.get("service") is not None else None,
                            ]
                        )
            except KeyError:
                ui.log("warning", f"Failed to parse: {masscan_dict}")
    ui.hide_progress_bar()
    ui.log("info", f"Saved results to {output_file_path}")


def delete_cluster(ui: ScannerUI, scanner_list: list[Scanner]):
    """Deletes a list of scanners

    Args:
        ui: The UI object
        scanner_list: The list of scanners
    """
    ui.show_progress_bar()
    ui.update_progress_bar(current_progress=0, total_progress=len(scanner_list), description="Destroying scanners")
    for scanner in scanner_list:
        ui.advance_progress_bar()
        scanner.__del__()
        scanner.delete_on_exit = False
    ui.hide_progress_bar()
