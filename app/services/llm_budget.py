from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from app.errors import AppError, ErrorCode


@dataclass
class DistillDeadline:
    """One monotonic wall-clock budget shared by every LLM layer."""

    total_budget_seconds: float
    started_monotonic: float
    deadline_monotonic: float
    started_at: datetime
    deadline_at: datetime
    _clock: Callable[[], float] = field(repr=False, compare=False)

    @classmethod
    def start(
        cls,
        total_budget_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        wall_now: datetime | None = None,
    ) -> "DistillDeadline":
        total = max(0.1, float(total_budget_seconds))
        started_monotonic = float(clock())
        started_at = wall_now or datetime.now(timezone.utc)
        return cls(
            total_budget_seconds=total,
            started_monotonic=started_monotonic,
            deadline_monotonic=started_monotonic + total,
            started_at=started_at,
            deadline_at=started_at + timedelta(seconds=total),
            _clock=clock,
        )

    def child(self, maximum_seconds: float) -> "DistillDeadline":
        now_monotonic = float(self._clock())
        remaining = max(0.0, self.deadline_monotonic - now_monotonic)
        total = min(max(0.1, float(maximum_seconds)), max(0.1, remaining))
        now_wall = datetime.now(timezone.utc)
        return DistillDeadline(
            total_budget_seconds=total,
            started_monotonic=now_monotonic,
            deadline_monotonic=min(self.deadline_monotonic, now_monotonic + total),
            started_at=now_wall,
            deadline_at=min(self.deadline_at, now_wall + timedelta(seconds=total)),
            _clock=self._clock,
        )

    def elapsed_seconds(self) -> float:
        return max(0.0, float(self._clock()) - self.started_monotonic)

    def remaining_seconds(self) -> float:
        return max(0.0, self.deadline_monotonic - float(self._clock()))

    def require_remaining(
        self,
        minimum_seconds: float = 0.1,
        *,
        phase: str = "llm_request",
        attempt_index: int = 1,
        provider: str = "",
    ) -> float:
        remaining = self.remaining_seconds()
        if remaining < max(0.1, float(minimum_seconds)):
            raise AppError(
                ErrorCode.LLM_GATEWAY_TIMEOUT,
                "大模型总等待预算已耗尽；没有继续发起请求。",
                details={
                    "provider": provider,
                    "retryable": False,
                    "phase": phase,
                    "attempt_index": attempt_index,
                },
            )
        return remaining

    def request_timeout(
        self,
        configured_timeout_seconds: float,
        *,
        minimum_seconds: float = 0.1,
        phase: str = "llm_request",
        attempt_index: int = 1,
        provider: str = "",
    ) -> float:
        remaining = self.require_remaining(
            minimum_seconds,
            phase=phase,
            attempt_index=attempt_index,
            provider=provider,
        )
        return max(0.1, min(float(configured_timeout_seconds), remaining))

    def public_snapshot(self) -> dict:
        elapsed = self.elapsed_seconds()
        remaining = self.remaining_seconds()
        return {
            "total_budget_seconds": max(1, int(self.total_budget_seconds)),
            "elapsed_seconds": max(0, int(elapsed)),
            "remaining_seconds": max(0, int(remaining)),
            "budget_started_at": self.started_at.isoformat(),
            "deadline_at": self.deadline_at.isoformat(),
        }
