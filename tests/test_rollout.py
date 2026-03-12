"""Tests for rollout strategies."""
import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from multitenant_config import (
    AlwaysOffRollout,
    AlwaysOnRollout,
    AndRollout,
    OrRollout,
    PercentageRollout,
    ScheduledRollout,
    TenantContext,
    TenantListRollout,
    UserListRollout,
    rollout_from_dict,
    rollout_to_dict,
)


CTX = TenantContext(tenant_id="t1", user_id="u1")
CTX_NO_USER = TenantContext(tenant_id="t1")


# ---------------------------------------------------------------------------
# AlwaysOn / AlwaysOff
# ---------------------------------------------------------------------------


def test_always_on():
    assert AlwaysOnRollout().is_enabled("f", CTX) is True


def test_always_off():
    assert AlwaysOffRollout().is_enabled("f", CTX) is False


# ---------------------------------------------------------------------------
# PercentageRollout
# ---------------------------------------------------------------------------


def test_percentage_100_always_on():
    r = PercentageRollout(100)
    assert r.is_enabled("flag", CTX) is True


def test_percentage_0_always_off():
    r = PercentageRollout(0)
    assert r.is_enabled("flag", CTX) is False


def test_percentage_deterministic():
    r = PercentageRollout(50)
    results = [r.is_enabled("flag", CTX) for _ in range(100)]
    # All results must be the same (same hash → same bucket)
    assert len(set(results)) == 1


def test_percentage_sticky_by_tenant():
    r = PercentageRollout(50, sticky_by="tenant")
    ctx_a = TenantContext(tenant_id="t1", user_id="u1")
    ctx_b = TenantContext(tenant_id="t1", user_id="u2")
    # Different users, same tenant → same result
    assert r.is_enabled("flag", ctx_a) == r.is_enabled("flag", ctx_b)


def test_percentage_sticky_by_user_differs_across_users():
    r = PercentageRollout(50, sticky_by="user")
    # With enough users some will be on, some off (probabilistic)
    results = {
        r.is_enabled("flag", TenantContext(tenant_id="t1", user_id=f"u{i}"))
        for i in range(200)
    }
    assert True in results and False in results


def test_percentage_no_user_falls_back_to_tenant():
    r = PercentageRollout(50, sticky_by="user")
    # No user_id → same result as tenant-level hash
    r2 = PercentageRollout(50, sticky_by="tenant")
    assert r.is_enabled("flag", CTX_NO_USER) == r2.is_enabled("flag", CTX_NO_USER)


def test_percentage_invalid():
    with pytest.raises(ValueError):
        PercentageRollout(101)
    with pytest.raises(ValueError):
        PercentageRollout(-1)


# ---------------------------------------------------------------------------
# UserListRollout
# ---------------------------------------------------------------------------


def test_user_list_match():
    r = UserListRollout(["u1", "u2"])
    assert r.is_enabled("f", CTX) is True


def test_user_list_no_match():
    r = UserListRollout(["u99"])
    assert r.is_enabled("f", CTX) is False


def test_user_list_no_user_in_ctx():
    r = UserListRollout(["u1"])
    assert r.is_enabled("f", CTX_NO_USER) is False


# ---------------------------------------------------------------------------
# TenantListRollout
# ---------------------------------------------------------------------------


def test_tenant_list_match():
    r = TenantListRollout(["t1", "t2"])
    assert r.is_enabled("f", CTX) is True


def test_tenant_list_no_match():
    r = TenantListRollout(["t99"])
    assert r.is_enabled("f", CTX) is False


# ---------------------------------------------------------------------------
# ScheduledRollout
# ---------------------------------------------------------------------------


def _past(hours: int = 1) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def _future(hours: int = 1) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def test_scheduled_within_window():
    r = ScheduledRollout(start_at=_past(), end_at=_future())
    assert r.is_enabled("f", CTX) is True


def test_scheduled_before_start():
    r = ScheduledRollout(start_at=_future(), end_at=_future(2))
    assert r.is_enabled("f", CTX) is False


def test_scheduled_after_end():
    r = ScheduledRollout(start_at=_past(2), end_at=_past())
    assert r.is_enabled("f", CTX) is False


def test_scheduled_no_end():
    r = ScheduledRollout(start_at=_past())
    assert r.is_enabled("f", CTX) is True


def test_scheduled_no_start():
    r = ScheduledRollout(end_at=_future())
    assert r.is_enabled("f", CTX) is True


# ---------------------------------------------------------------------------
# AndRollout / OrRollout
# ---------------------------------------------------------------------------


def test_and_all_true():
    r = AndRollout([AlwaysOnRollout(), AlwaysOnRollout()])
    assert r.is_enabled("f", CTX) is True


def test_and_one_false():
    r = AndRollout([AlwaysOnRollout(), AlwaysOffRollout()])
    assert r.is_enabled("f", CTX) is False


def test_or_one_true():
    r = OrRollout([AlwaysOffRollout(), AlwaysOnRollout()])
    assert r.is_enabled("f", CTX) is True


def test_or_all_false():
    r = OrRollout([AlwaysOffRollout(), AlwaysOffRollout()])
    assert r.is_enabled("f", CTX) is False


def test_and_empty_raises():
    with pytest.raises(ValueError):
        AndRollout([])


# ---------------------------------------------------------------------------
# Serialisation / deserialisation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "strategy",
    [
        AlwaysOnRollout(),
        AlwaysOffRollout(),
        PercentageRollout(42.5),
        PercentageRollout(30, sticky_by="tenant"),
        UserListRollout(["a", "b"]),
        TenantListRollout(["x"]),
        ScheduledRollout(start_at=_past(), end_at=_future()),
        ScheduledRollout(),
        AndRollout([AlwaysOnRollout(), PercentageRollout(50)]),
        OrRollout([AlwaysOffRollout(), TenantListRollout(["t1"])]),
    ],
)
def test_round_trip_serialisation(strategy):
    d = rollout_to_dict(strategy)
    assert d is not None
    restored = rollout_from_dict(d)
    assert restored is not None
    # Same class
    assert type(restored) is type(strategy)
    # Same evaluation result for fixed ctx
    assert restored.is_enabled("flag", CTX) == strategy.is_enabled("flag", CTX)


def test_rollout_to_dict_none():
    assert rollout_to_dict(None) is None


def test_rollout_from_dict_none():
    assert rollout_from_dict(None) is None


def test_rollout_from_dict_unknown_raises():
    with pytest.raises(ValueError, match="Unknown rollout strategy type"):
        rollout_from_dict({"type": "nonexistent"})
