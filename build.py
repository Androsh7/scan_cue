"""Build script for scan_cue"""

# Standard libraries
import argparse
import subprocess
from pathlib import Path

PARENT_DIR = Path(__file__).parent
PYTHON_VERSION = "3.13"

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="build.py", description="Build scan_cue executable")
    subparsers = parser.add_subparsers(dest="platform", help="Target platform")
    linux_parser = subparsers.add_parser("linux", help="Build Linux executable")
    linux_parser.add_argument(
        "--architecture",
        type=str,
        choices=["x86_64", "aarch64"],
        required=True,
        help="Target architecture (x86_64 or aarch64)",
    )
    linux_parser.add_argument(
        "--libc",
        type=str,
        required=True,
        help="The libc and its major.minor version (e.g., glibc-2.17)",
    )
    linux_parser.add_argument(
        "--output-file",
        type=Path,
        default=PARENT_DIR / "scan_cue.bin",
        help="Output file path for the Linux executable",
    )
    windows_parser = subparsers.add_parser("windows", help="Build Windows executable")
    windows_parser.add_argument(
        "--output-file",
        type=Path,
        default=PARENT_DIR / "scan_cue.exe",
        help="Output file path for the Windows executable",
    )
    args = parser.parse_args()

    # Build a linux executable
    if args.platform == "linux":
        container_name = f"scan_cue_compiler_{args.architecture}_{args.libc}_py{PYTHON_VERSION}"
        image_name = f"androsh7/nuitka-compiler:latest-{args.architecture}-{args.libc}-py{PYTHON_VERSION}"
        subprocess.run(
            f"""\
docker create --name {container_name} {image_name} sleep infinity \
&& docker cp {PARENT_DIR / "scan_cue"} {container_name}:/src/scan_cue \
&& docker cp {PARENT_DIR / "pyproject.toml"} {container_name}:/src/pyproject.toml \
&& docker start {container_name} \
&& docker exec {container_name} python3 -m pip install .[dev]  \
&& docker exec {container_name} python3 -m nuitka /src/scan_cue/main.py \
    --follow-imports \
    --onefile \
    --onefile-tempdir-spec={{HOME}}/.scan_cue/bin \
    --output-filename=/src/main.bin \
&& docker exec {container_name} /src/main.bin --version \
&& docker cp {container_name}:/src/main.bin {args.output_file} \
&& docker rm --force {container_name}
""",
            check=True,
            shell=True,
        )

    # Build a windows executable
    elif args.platform == "windows":
        subprocess.run(
            f"""\
pip install {PARENT_DIR}.[dev] \
&& nuitka {PARENT_DIR / "scan_cue" / "main.py"} \
    --follow-imports \
    --onefile \
    --onefile-tempdir-spec={{HOME}}/.scan_cue/bin \
    --output-filename={args.output_file}
""",
            shell=True,
            check=True,
        )
    else:
        parser.print_help()
