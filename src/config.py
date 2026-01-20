"""Config"""

# Standard libraries
from pathlib import Path

VERSION = "0.1.0"
SOURCE_DIR = Path(__file__).parent
BUILD_DIR = Path().home() / ".scan_cue"

# AWS constants
AWS_STARTUP_SCRIPT = """\
#!/bin/bash
set -euo pipefail

sudo dnf -y install git make gcc libpcap-devel tmux
git clone https://github.com/robertdavidgraham/masscan.git
cd masscan/
make
sudo make install
"""
AWS_EC2_STATES = ("pending", "running", "shutting-down", "terminated", "stopping", "stopped")
AWS_SSM_PROFILE_NAME = "scan_cue_scanner_profile"
DEFAULT_EC2_TYPE = "t4g.nano"

# SSH constants
SSH_TIMEOUT = 20

# Masscan constants
MASSCAN_OUTPUT_FILE = "/home/ec2-user/scan_output.json"
MASSCAN_ERROR_FILE = "/home/ec2-user/error.txt"
DEFAULT_IP_EXCLUDE_LIST = ["10.0.0.1/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.1/8"]
DEFAULT_MASSCAN_RATE = 25000000  # Max theoretical rate
DEFAULT_MASSCAN_RETRIES = 3

# Default arguments
DEFAULT_CLUSTER_NAME = "scan_cue_cluster"

# Log level
LOG_LEVELS = ("trace", "debug", "info", "warning", "critical")
LOG_LEVEL_NUM_DICT = {
    "trace": 0,
    "debug": 1,
    "info": 2,
    "warning": 3,
    "critical": 4,
}
LOG_COLOR_DICT = {
    "trace": "blue",
    "debug": "blue",
    "info": "white",
    "warning": "orange",
    "critical": "red",
}
