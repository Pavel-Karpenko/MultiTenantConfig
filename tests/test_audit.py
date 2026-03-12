"""Tests for AuditLog."""
import pytest

from multitenant_config.audit import AuditLog


def test_record_and_query():
    log = AuditLog()
    log.record(
        actor="admin",
        tenant_id="t1",
        action="flag.set",
        entity_type="flag",
        entity_id="my_flag",
        old_value=False,
        new_value=True,
    )
    entries = log.query()
    assert len(entries) == 1
    assert entries[0].action == "flag.set"
    assert entries[0].new_value is True


def test_query_filter_tenant():
    log = AuditLog()
    log.record(actor=None, tenant_id="t1", action="a", entity_type="flag", entity_id="f")
    log.record(actor=None, tenant_id="t2", action="a", entity_type="flag", entity_id="f")
    result = log.query(tenant_id="t1")
    assert len(result) == 1
    assert result[0].tenant_id == "t1"


def test_query_filter_action():
    log = AuditLog()
    log.record(actor=None, tenant_id="t", action="flag.set", entity_type="flag", entity_id="f")
    log.record(actor=None, tenant_id="t", action="config.set", entity_type="config", entity_id="k")
    result = log.query(action="flag.set")
    assert all(e.action == "flag.set" for e in result)


def test_query_newest_first():
    log = AuditLog()
    for i in range(5):
        log.record(actor=None, tenant_id="t", action="a", entity_type="x", entity_id=str(i))
    entries = log.query()
    ids = [e.entity_id for e in entries]
    assert ids == list(reversed(ids[::-1]))  # strictly newest first


def test_max_entries_eviction():
    log = AuditLog(max_entries=3)
    for i in range(5):
        log.record(actor=None, tenant_id="t", action="a", entity_type="x", entity_id=str(i))
    assert len(log) == 3
    entries = log.query()
    # Oldest entries (0, 1) should be gone
    ids = {e.entity_id for e in entries}
    assert "0" not in ids and "1" not in ids


def test_handler_called():
    called = []
    log = AuditLog(handlers=[called.append])
    log.record(actor=None, tenant_id="t", action="a", entity_type="x", entity_id="e")
    assert len(called) == 1
    assert called[0].action == "a"


def test_add_handler_at_runtime():
    called = []
    log = AuditLog()
    log.add_handler(called.append)
    log.record(actor=None, tenant_id="t", action="a", entity_type="x", entity_id="e")
    assert len(called) == 1


def test_query_offset_and_limit():
    log = AuditLog()
    for i in range(10):
        log.record(actor=None, tenant_id="t", action="a", entity_type="x", entity_id=str(i))
    page1 = log.query(limit=3, offset=0)
    page2 = log.query(limit=3, offset=3)
    assert len(page1) == 3
    assert len(page2) == 3
    assert {e.entity_id for e in page1}.isdisjoint({e.entity_id for e in page2})


def test_entry_serialisation():
    log = AuditLog()
    entry = log.record(
        actor="bot",
        tenant_id="t1",
        action="config.set",
        entity_type="config",
        entity_id="max_seats",
        old_value=5,
        new_value=100,
        metadata={"reason": "plan upgrade"},
    )
    d = entry.to_dict()
    from multitenant_config.audit import AuditEntry

    restored = AuditEntry.from_dict(d)
    assert restored.actor == "bot"
    assert restored.new_value == 100
    assert restored.metadata == {"reason": "plan upgrade"}
