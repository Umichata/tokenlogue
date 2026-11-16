"""Optional provider-confirmed request counts, separate from money and tokens."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DailyRequestQuota:
    used: int
    limit: int
    remaining: int

    def __post_init__(self) -> None:
        values = (self.used, self.limit, self.remaining)
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError("invalid_daily_request_quota")
        if self.remaining != max(0, self.limit - self.used):
            raise ValueError("inconsistent_daily_request_quota")
