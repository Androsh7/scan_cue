"""Defines the masscan object"""

# Standard libraries
import re
from datetime import timedelta

# Third-party libraries
from attrs import define, field, validators

# Project libraries
from config import DEFAULT_IP_EXCLUDE_LIST, MASSCAN_ERROR_FILE, MASSCAN_OUTPUT_FILE


@define
class MasscanResults:
    rate: float = field(converter=float)
    completion: float = field(converter=float)
    eta: timedelta = field(validator=validators.instance_of(timedelta))
    found: int = field(validator=validators.and_(validators.ge(0), validators.instance_of(int)))

    @classmethod
    def from_rate_string(cls, rate_string: str):
        matches = re.search(
            r"rate: *(\d+(\.\d+)?)-kpps, *(\d+(\.\d+)?)% * done, *(waiting +(-?\d)-secs|(\d+(:\d+){0,2}) remaining), *found=(\d+)",
            rate_string,
        )
        if matches.group(7) is not None:
            eta_split = matches.group(7).split(":")
            completion = float(matches.group(3))
            eta = timedelta(hours=int(eta_split[0]), minutes=int(eta_split[1]), seconds=int(eta_split[2]))
        else:
            # Scan is waiting to complete
            eta = timedelta(seconds=max(int(matches.group(6)), 1))
            completion = 100.0
        return cls(
            rate=float(matches.group(1)),
            completion=completion,
            eta=eta,
            found=int(matches.group(9)),
        )

    @classmethod
    def from_result_list(cls, result_list: list["MasscanResults"]):
        rate = 0
        completion = 0
        eta_seconds = 0
        found = 0
        for result in result_list:
            rate += result.rate
            completion += result.completion
            eta_seconds += result.eta.total_seconds()
            found += result.found

        return cls(
            rate=rate,
            completion=completion / len(result_list),
            eta=timedelta(seconds=int(eta_seconds / len(result_list))),
            found=found,
        )


@define
class MasscanCommand:
    ip_include_list: list[str] = field(
        validator=validators.deep_iterable(
            member_validator=validators.instance_of(str), iterable_validator=validators.instance_of(list)
        )
    )
    port_list: list[str] = field(
        validator=validators.deep_iterable(
            member_validator=validators.instance_of(str), iterable_validator=validators.instance_of(list)
        )
    )
    rate: int = field(validator=validators.and_(validators.ge(1), validators.instance_of(int)))
    retries: int = field(default=1, validator=validators.and_(validators.ge(1), validators.instance_of(int)))
    ip_exclude_list: list[str] = field(
        default=DEFAULT_IP_EXCLUDE_LIST,
        validator=validators.deep_iterable(
            member_validator=validators.instance_of(str), iterable_validator=validators.instance_of(list)
        ),
    )
    banner: bool = field(default=False, validator=validators.instance_of(bool))

    def create_base_command(self) -> list[str]:
        out_command = []
        out_command.extend(["sudo", "masscan"])
        for ip in self.ip_include_list:
            out_command.append(ip)
        for ip in self.ip_exclude_list:
            out_command.extend(["--exclude", ip])
        for port in self.port_list:
            out_command.extend(["--port", port])
        if self.banner:
            out_command.append("--banners")
        out_command.extend(["--retries", str(self.retries)])
        out_command.extend(["--rate", str(self.rate)])
        return out_command

    def create_command(self, shard: int, shard_total: int, seed: str) -> str:
        out_command = self.create_base_command()
        out_command.extend(["--shard", f"{shard}/{shard_total}"])
        out_command.extend(["--seed", seed])
        out_command.extend([f"-oJ {MASSCAN_OUTPUT_FILE}", f"2>{MASSCAN_ERROR_FILE}"])
        return " ".join(out_command)
