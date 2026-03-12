"""Tenant models and context."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Tenant:
    """Represents a registered tenant."""

    id: str
    name: str = ""
    plan: str = "free"
    metadata: dict[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    is_active: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "plan": self.plan,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Tenant:
        return cls(
            id=str(data["id"]),
            name=str(data.get("name", "")),
            plan=str(data.get("plan", "free")),
            metadata=dict(data.get("metadata", {})),  # type: ignore[arg-type]
            created_at=datetime.fromisoformat(str(data["created_at"])),
            updated_at=datetime.fromisoformat(str(data["updated_at"])),
            is_active=bool(data.get("is_active", True)),
        )


@dataclass
class TenantContext:
    """Runtime context passed when evaluating flags and configs.

    tenant_id: required — identifies the tenant
    user_id:   optional — enables per-user rollout strategies
    metadata:  optional — arbitrary key/value for custom rollout logic
    """

    tenant_id: str
    user_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
