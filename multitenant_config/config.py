"""Config key models."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .exceptions import ValidationError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Supported scalar types that round-trip cleanly through JSON.
_TYPE_MAP: dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
}


def _type_name(t: type | None) -> str | None:
    if t is None:
        return None
    return t.__name__


def _type_from_name(name: str | None) -> type | None:
    if name is None:
        return None
    t = _TYPE_MAP.get(name)
    if t is None:
        raise ValueError(f"Unsupported config type: {name!r}. Supported: {list(_TYPE_MAP)}")
    return t


@dataclass
class ConfigDefinition:
    """Global definition of a config key with its default value."""

    key: str
    default: Any
    value_type: type | None = None  # None = no type enforcement
    description: str = ""
    secret: bool = False  # when True, values are masked in audit log as "***"
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def validate(self, value: Any) -> Any:
        """Coerce and validate *value* against value_type.

        Raises ValidationError if coercion fails.
        Returns the (possibly coerced) value.
        """
        if self.value_type is None:
            return value
        if isinstance(value, self.value_type):
            return value
        # Attempt coercion for scalar types
        try:
            return self.value_type(value)
        except (ValueError, TypeError) as exc:
            raise ValidationError(
                f"Config {self.key!r} expects {self.value_type.__name__}, "
                f"got {type(value).__name__}: {exc}"
            ) from exc

    def mask(self, value: Any) -> Any:
        """Return a masked representation for audit/display when secret=True."""
        if self.secret:
            return "***"
        return value

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "default": self.default,
            "value_type": _type_name(self.value_type),
            "description": self.description,
            "secret": self.secret,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConfigDefinition:
        return cls(
            key=str(data["key"]),
            default=data["default"],
            value_type=_type_from_name(data.get("value_type")),  # type: ignore[arg-type]
            description=str(data.get("description", "")),
            secret=bool(data.get("secret", False)),
            tags=list(data.get("tags", [])),
            created_at=datetime.fromisoformat(str(data["created_at"])),
            updated_at=datetime.fromisoformat(str(data["updated_at"])),
        )


@dataclass
class TenantConfigOverride:
    """Per-tenant override for a config key."""

    tenant_id: str
    config_key: str
    value: Any
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "config_key": self.config_key,
            "value": self.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TenantConfigOverride:
        return cls(
            tenant_id=str(data["tenant_id"]),
            config_key=str(data["config_key"]),
            value=data["value"],
            created_at=datetime.fromisoformat(str(data["created_at"])),
            updated_at=datetime.fromisoformat(str(data["updated_at"])),
        )


def _json_serialisable(value: Any) -> Any:
    """Best-effort conversion so values can be stored as JSON."""
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)
