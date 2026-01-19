"""Utility functions"""

# Standard libraries
from pathlib import Path

# Third-party libraries
from tqdm import tqdm

def merge_json_files(files_to_merge: list[Path], output_file: Path):
    """Merges json files

    Args:
        files_to_merge: The json files to merge
        output_file: The output file
    """
    with open(file=output_file, mode="wb") as combined_file:
        combined_file.write(b"[")
        for index, file_path in enumerate(tqdm(files_to_merge, unit="json file", desc="joining json files"), start=1):
            with open(file=file_path, mode="rb") as result_file:
                combined_file.write(result_file.read().replace(b"\r\n", b"")[1:-1])
            if index < len(files_to_merge):
                combined_file.write(b',')
        combined_file.write(b"]")
