"""Audit log — records every mutation with actor, before/after values."""
from __future__ import annotations

import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------


@dataclass
class AuditEntry:
    """Immutable record of a single change."""

    id: str
    timestamp: datetime
    actor: str | None  # username / service account that made the change
    tenant_id: str | None  # None for global changes (e.g. defining a flag)
    action: str  # verb: "tenant.register", "flag.define", "flag.set", "config.set", …
    entity_type: str  # "tenant" | "flag" | "config"
    entity_id: str  # flag_name / config_key / tenant_id
    old_value: Any
    new_value: Any
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "actor": self.actor,
            "tenant_id": self.tenant_id,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditEntry:
        return cls(
            id=str(data["id"]),
            timestamp=datetime.fromisoformat(str(data["timestamp"])),
            actor=data.get("actor"),  # type: ignore[arg-type]
            tenant_id=data.get("tenant_id"),  # type: ignore[arg-type]
            action=str(data["action"]),
            entity_type=str(data["entity_type"]),
            entity_id=str(data["entity_id"]),
            old_value=data.get("old_value"),
            new_value=data.get("new_value"),
            metadata=dict(data.get("metadata", {})),
        )


# ---------------------------------------------------------------------------
# Handler type
# ---------------------------------------------------------------------------

AuditHandler = Callable[[AuditEntry], None]


# ---------------------------------------------------------------------------
# AuditLog
# ---------------------------------------------------------------------------


class AuditLog:
    """Thread-safe in-memory audit log with optional external handlers.

    Parameters
    ----------
    max_entries:
        Maximum number of entries kept in memory (oldest are evicted).
    handlers:
        Callables invoked (in order) for every new entry.  Use them to
        forward entries to an external system (database, Kafka, etc.).
    """

    def __init__(
        self,
        max_entries: int = 10_000,
        handlers: list[AuditHandler] | None = None,
    ) -> None:
        self._entries: deque[AuditEntry] = deque(maxlen=max_entries)
        self._handlers: list[AuditHandler] = handlers or []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def record(
        self,
        *,
        actor: str | None,
        tenant_id: str | None,
        action: str,
        entity_type: str,
        entity_id: str,
        old_value: Any = None,
        new_value: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            id=str(uuid.uuid4()),
            timestamp=_utcnow(),
            actor=actor,
            tenant_id=tenant_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value=old_value,
            new_value=new_value,
            metadata=metadata or {},
        )
        with self._lock:
            self._entries.append(entry)
        for handler in self._handlers:
            handler(entry)
        return entry

    def add_handler(self, handler: AuditHandler) -> None:
        """Register an additional handler (thread-safe)."""
        self._handlers.append(handler)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(
        self,
        *,
        tenant_id: str | None = None,
        entity_type: str | None = None,
        action: str | None = None,
        actor: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEntry]:
        """Return matching entries in reverse-chronological order."""
        with self._lock:
            entries = list(self._entries)

        # Newest first
        entries.reverse()

        if tenant_id is not None:
            entries = [e for e in entries if e.tenant_id == tenant_id]
        if entity_type is not None:
            entries = [e for e in entries if e.entity_type == entity_type]
        if action is not None:
            entries = [e for e in entries if e.action == action]
        if actor is not None:
            entries = [e for e in entries if e.actor == actor]

        return entries[offset : offset + limit]

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


# ---------------------------------------------------------------------------
# Convenience handlers
# ---------------------------------------------------------------------------


def print_handler(entry: AuditEntry) -> None:
    """Simple handler that prints entries to stdout — useful for development."""
    ts = entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    actor = entry.actor or "system"
    tenant = f"[{entry.tenant_id}] " if entry.tenant_id else ""
    print(f"[AUDIT] {ts} {actor} {tenant}{entry.action} {entity_label(entry)}")


def entity_label(entry: AuditEntry) -> str:
    return f"{entry.entity_type}:{entry.entity_id}"
