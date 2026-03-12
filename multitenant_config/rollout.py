"""Rollout strategy implementations.

All strategies are pure, stateless, and serialisable to/from dict.

Evaluation order in the manager (highest priority first):
  tenant explicit override (AlwaysOn/Off) > tenant rollout > global rollout
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from .tenant import TenantContext

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, type[RolloutStrategy]] = {}


def _register(cls: type[RolloutStrategy]) -> type[RolloutStrategy]:
    _REGISTRY[cls.TYPE] = cls  # type: ignore[attr-defined]
    return cls


def rollout_from_dict(data: dict[str, Any] | None) -> RolloutStrategy | None:
    """Deserialise a rollout strategy from its dict representation."""
    if data is None:
        return None
    type_name = str(data.get("type", ""))
    cls = _REGISTRY.get(type_name)
    if cls is None:
        raise ValueError(f"Unknown rollout strategy type: {type_name!r}")
    return cls.from_dict(data)


def rollout_to_dict(strategy: RolloutStrategy | None) -> dict[str, Any] | None:
    if strategy is None:
        return None
    return strategy.to_dict()


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class RolloutStrategy(ABC):
    """Abstract base for all rollout strategies."""

    TYPE: str  # subclasses must define this class-level constant

    @abstractmethod
    def is_enabled(self, flag_name: str, ctx: TenantContext) -> bool:
        """Return True if the flag should be active for this context."""

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Serialise strategy to a plain dict (must include 'type' key)."""

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict[str, Any]) -> RolloutStrategy:
        """Deserialise from the dict produced by to_dict()."""

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.to_dict()})"


# ---------------------------------------------------------------------------
# Built-in strategies
# ---------------------------------------------------------------------------


@_register
class AlwaysOnRollout(RolloutStrategy):
    """100 % rollout — flag is enabled for every context."""

    TYPE = "always_on"

    def is_enabled(self, flag_name: str, ctx: TenantContext) -> bool:
        return True

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.TYPE}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlwaysOnRollout:
        return cls()


@_register
class AlwaysOffRollout(RolloutStrategy):
    """0 % rollout — flag is disabled for every context."""

    TYPE = "always_off"

    def is_enabled(self, flag_name: str, ctx: TenantContext) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.TYPE}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlwaysOffRollout:
        return cls()


@_register
class PercentageRollout(RolloutStrategy):
    """Hash-based percentage rollout.

    The bucket is deterministic: same (flag_name, sticky_key) always
    lands in the same bucket, guaranteeing a consistent user experience.

    sticky_by:
      "user"   — hash on tenant_id + user_id (falls back to tenant if no user)
      "tenant" — hash on tenant_id only (all users of a tenant get same result)
    """

    TYPE = "percentage"

    def __init__(self, percentage: float, sticky_by: str = "user") -> None:
        if not 0.0 <= percentage <= 100.0:
            raise ValueError(f"percentage must be in [0, 100], got {percentage}")
        if sticky_by not in ("user", "tenant"):
            raise ValueError(f"sticky_by must be 'user' or 'tenant', got {sticky_by!r}")
        self.percentage = percentage
        self.sticky_by = sticky_by

    def _bucket(self, flag_name: str, ctx: TenantContext) -> int:
        if self.sticky_by == "user" and ctx.user_id:
            key = f"{flag_name}:{ctx.tenant_id}:{ctx.user_id}"
        else:
            key = f"{flag_name}:{ctx.tenant_id}"
        digest = hashlib.sha256(key.encode()).digest()
        # Use first 4 bytes as uint32, then mod 100
        return int.from_bytes(digest[:4], "big") % 100

    def is_enabled(self, flag_name: str, ctx: TenantContext) -> bool:
        return self._bucket(flag_name, ctx) < self.percentage

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.TYPE, "percentage": self.percentage, "sticky_by": self.sticky_by}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PercentageRollout:
        return cls(percentage=float(data["percentage"]), sticky_by=str(data.get("sticky_by", "user")))


@_register
class UserListRollout(RolloutStrategy):
    """Enable the flag only for specific user IDs."""

    TYPE = "user_list"

    def __init__(self, user_ids: list[str]) -> None:
        self.user_ids: frozenset[str] = frozenset(user_ids)

    def is_enabled(self, flag_name: str, ctx: TenantContext) -> bool:
        return ctx.user_id is not None and ctx.user_id in self.user_ids

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.TYPE, "user_ids": sorted(self.user_ids)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserListRollout:
        return cls(user_ids=list(data.get("user_ids", [])))


@_register
class TenantListRollout(RolloutStrategy):
    """Enable the flag only for specific tenant IDs."""

    TYPE = "tenant_list"

    def __init__(self, tenant_ids: list[str]) -> None:
        self.tenant_ids: frozenset[str] = frozenset(tenant_ids)

    def is_enabled(self, flag_name: str, ctx: TenantContext) -> bool:
        return ctx.tenant_id in self.tenant_ids

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.TYPE, "tenant_ids": sorted(self.tenant_ids)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TenantListRollout:
        return cls(tenant_ids=list(data.get("tenant_ids", [])))


@_register
class ScheduledRollout(RolloutStrategy):
    """Enable the flag only within a time window [start_at, end_at).

    Either boundary can be omitted (open-ended interval).
    """

    TYPE = "scheduled"

    def __init__(
        self,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> None:
        self.start_at = start_at
        self.end_at = end_at

    def is_enabled(self, flag_name: str, ctx: TenantContext) -> bool:
        now = datetime.now(timezone.utc)
        if self.start_at and now < self.start_at:
            return False
        if self.end_at and now >= self.end_at:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.TYPE,
            "start_at": self.start_at.isoformat() if self.start_at else None,
            "end_at": self.end_at.isoformat() if self.end_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScheduledRollout:
        start = datetime.fromisoformat(str(data["start_at"])) if data.get("start_at") else None
        end = datetime.fromisoformat(str(data["end_at"])) if data.get("end_at") else None
        return cls(start_at=start, end_at=end)


@_register
class AndRollout(RolloutStrategy):
    """Logical AND: all sub-strategies must return True."""

    TYPE = "and"

    def __init__(self, strategies: list[RolloutStrategy]) -> None:
        if not strategies:
            raise ValueError("AndRollout requires at least one strategy")
        self.strategies = strategies

    def is_enabled(self, flag_name: str, ctx: TenantContext) -> bool:
        return all(s.is_enabled(flag_name, ctx) for s in self.strategies)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.TYPE, "strategies": [s.to_dict() for s in self.strategies]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AndRollout:
        strategies = [rollout_from_dict(s) for s in data.get("strategies", [])]
        return cls(strategies=[s for s in strategies if s is not None])


@_register
class OrRollout(RolloutStrategy):
    """Logical OR: at least one sub-strategy must return True."""

    TYPE = "or"

    def __init__(self, strategies: list[RolloutStrategy]) -> None:
        if not strategies:
            raise ValueError("OrRollout requires at least one strategy")
        self.strategies = strategies

    def is_enabled(self, flag_name: str, ctx: TenantContext) -> bool:
        return any(s.is_enabled(flag_name, ctx) for s in self.strategies)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.TYPE, "strategies": [s.to_dict() for s in self.strategies]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrRollout:
        strategies = [rollout_from_dict(s) for s in data.get("strategies", [])]
        return cls(strategies=[s for s in strategies if s is not None])
