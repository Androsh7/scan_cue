#!/bin/bash
set -euo pipefail

sudo dnf -y install git make gcc libpcap-devel tmux
git clone https://github.com/robertdavidgraham/masscan.git
cd masscan/
make
sudo make install