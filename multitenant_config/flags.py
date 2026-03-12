"""Feature flag models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .rollout import AlwaysOffRollout, RolloutStrategy, rollout_from_dict, rollout_to_dict


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class FlagDefinition:
    """Global definition of a feature flag."""

    name: str
    description: str = ""
    rollout: RolloutStrategy = field(default_factory=AlwaysOffRollout)
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "rollout": rollout_to_dict(self.rollout),
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FlagDefinition:
        rollout = rollout_from_dict(data.get("rollout")) or AlwaysOffRollout()
        return cls(
            name=str(data["name"]),
            description=str(data.get("description", "")),
            rollout=rollout,
            tags=list(data.get("tags", [])),
            created_at=datetime.fromisoformat(str(data["created_at"])),
            updated_at=datetime.fromisoformat(str(data["updated_at"])),
        )


@dataclass
class TenantFlagOverride:
    """Per-tenant rollout override for a feature flag.

    If rollout is None the override is effectively removed (use global).
    """

    tenant_id: str
    flag_name: str
    rollout: RolloutStrategy
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "flag_name": self.flag_name,
            "rollout": rollout_to_dict(self.rollout),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TenantFlagOverride:
        rollout = rollout_from_dict(data.get("rollout")) or AlwaysOffRollout()
        return cls(
            tenant_id=str(data["tenant_id"]),
            flag_name=str(data["flag_name"]),
            rollout=rollout,
            created_at=datetime.fromisoformat(str(data["created_at"])),
            updated_at=datetime.fromisoformat(str(data["updated_at"])),
        )
