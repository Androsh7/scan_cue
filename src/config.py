"""Config"""

# Standard libraries
import sys
from pathlib import Path

# Third-party libraries
from loguru import logger

# Project libraries
from aws_query import load_regions

# Set log level
logger.remove()
logger.add(
    sys.stdout,
    level="DEBUG",
)

VERSION = "0.1.0"
SOURCE_DIR = Path(__file__).parent
BUILD_DIR = Path().home() / ".scan_cue"

# AWS constants
AWS_REGION_SET = load_regions()
with open(file=SOURCE_DIR / "setup_script.sh", encoding="utf-8") as setup_file:
    AWS_STARTUP_SCRIPT = setup_file.read()
AWS_EC2_STATES = ("pending", "running", "shutting-down", "terminated", "stopping", "stopped")
AWS_SSM_PROFILE_NAME = "scan_cue_scanner_profile"

# SSH constants
SSH_TIMEOUT = 20

# Masscan constants
MASSCAN_OUTPUT_FILE = "/home/ec2-user/scan_output.json"
MASSCAN_ERROR_FILE = "/home/ec2-user/error.txt"
