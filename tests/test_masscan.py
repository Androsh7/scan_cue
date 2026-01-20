"""Test masscan classes"""

# Standard libraries
from datetime import timedelta

# Project libraries
from src.masscan import MasscanCommand, MasscanResults


def test_create_masscan_command():
    masscan_command = MasscanCommand(
        ip_include_list=["127.0.0.1/24"],
        ip_exclude_list=["1.1.1.1/8"],
        banner=True,
        retries=3,
        port_list=["50-443"],
        rate=5000,
    )
    assert (
        " ".join(masscan_command.create_base_command())
        == "sudo masscan 127.0.0.1/24 --exclude 1.1.1.1/8 --port 50-443 --banners --retries 3 --rate 5000"
    )
    assert (
        masscan_command.create_command(shard=1, shard_total=10, seed="test")
        == "sudo masscan 127.0.0.1/24 --exclude 1.1.1.1/8 --port 50-443 --banners --retries 3 --rate 5000 --shard 1/10 --seed test -oJ /home/ec2-user/scan_output.json 2>/home/ec2-user/error.txt"
    )


RESULT_DICT = {
    "rate:  4.98-kpps,  4.97% done,   0:01:54 remaining, found=0": MasscanResults(
        rate=4.98, completion=4.97, eta=timedelta(minutes=1, seconds=54), found=0
    ),
    "rate:  0.00-kpps, 100.00% done, waiting 8-secs, found=0": MasscanResults(
        rate=0, completion=100, eta=timedelta(seconds=8), found=0
    ),
    "rate:  0.00-kpps, 100.00% done, waiting -1-secs, found=0": MasscanResults(
        rate=0, completion=100, eta=timedelta(seconds=1), found=0
    ),
}


def test_masscan_results():
    for status_string, expected_masscan_result in RESULT_DICT.items():
        print(f"testing: {status_string}")
        assert MasscanResults.from_rate_string(status_string) == expected_masscan_result


def test_merge_masscan_results():
    assert MasscanResults.from_result_list(list(RESULT_DICT.values())) == MasscanResults(
        rate=4.98, completion=68.32333333333334, eta=timedelta(seconds=41), found=0
    )
