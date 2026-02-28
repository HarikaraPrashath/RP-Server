from __future__ import annotations

import urllib.robotparser
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str


class CrawlerPolicy:
    def __init__(self, user_agent: str = "RPServerBot/1.0", min_interval_seconds: int = 20) -> None:
        self.user_agent = user_agent
        self.min_interval = timedelta(seconds=min_interval_seconds)

    def allow_by_interval(self, last_run_iso: str | None) -> PolicyDecision:
        if not last_run_iso:
            return PolicyDecision(True, "No prior run")
        try:
            last_run = datetime.fromisoformat(last_run_iso)
            if last_run.tzinfo is None:
                last_run = last_run.replace(tzinfo=timezone.utc)
        except Exception:
            return PolicyDecision(True, "Invalid last run timestamp")
        now = datetime.now(timezone.utc)
        if now - last_run < self.min_interval:
            return PolicyDecision(False, "Rate limit window active")
        return PolicyDecision(True, "Interval check passed")

    def allow_by_robots(self, base_url: str, path: str = "/") -> PolicyDecision:
        robots_url = base_url.rstrip("/") + "/robots.txt"
        parser = urllib.robotparser.RobotFileParser()
        try:
            parser.set_url(robots_url)
            parser.read()
            allowed = parser.can_fetch(self.user_agent, base_url.rstrip("/") + path)
            return PolicyDecision(allowed, "Robots check")
        except Exception:
            # Fail-open for dev reliability, but surfaced in response details.
            return PolicyDecision(True, "Robots unavailable")
