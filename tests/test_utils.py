"""Test utilities"""

# Standard libraries
import json
import os
import shutil
from pathlib import Path

# Project libraries
from scan_cue.utils import merge_json_files


class MockProgress:
    def advance_progress_bar(self):
        print("advance progress bar")

    def show_progress_bar(self):
        print("show progress bar")

    def hide_progress_bar(self):
        print("hide progress bar")

    def update_progress_bar(self, current_progress: float, total_progress: float, description: str):
        print(f"{current_progress}/{total_progress}, description: {description}")


def test_json_merge():
    expected_merged_file = [{"test": 12345}, {"test": 23456}, {"test": 34567}, {"test": 45678}, {"test": 56789}]
    test_list = [[{"test": 12345}], [{"test": 23456}], [{"test": 34567}], [{"test": 45678}], [{"test": 56789}]]

    # Create mock json files
    merge_dir = Path(__file__).parent / "test_dir"
    os.makedirs(merge_dir, exist_ok=True)
    input_file_paths = []
    for index, sub_dict in enumerate(test_list):
        input_file_path = merge_dir / f"input_{index}.json"
        with open(file=input_file_path, mode="w", encoding="utf-8") as file:
            json.dump(sub_dict, file)
        input_file_paths.append(input_file_path)

    # Run merge
    merged_file_path = merge_dir / "merged.json"
    merge_json_files(ui=MockProgress(), files_to_merge=input_file_paths, output_file=merged_file_path)

    # Compare merged and unmerged file
    with open(file=merged_file_path, encoding="utf-8") as merge_file:
        assert json.load(merge_file) == expected_merged_file

    # Delete test dir
    shutil.rmtree(merge_dir)


test_json_merge()
