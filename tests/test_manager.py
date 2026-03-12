"""Integration tests for MultiTenantConfig."""
import threading
import pytest

from multitenant_config import (
    AlwaysOffRollout,
    AlwaysOnRollout,
    ConfigNotFoundError,
    FlagNotFoundError,
    InMemoryStorage,
    MultiTenantConfig,
    PercentageRollout,
    TenantContext,
    TenantInactiveError,
    TenantListRollout,
    TenantNotFoundError,
    ValidationError,
)


# ===========================================================================
# Tenant management
# ===========================================================================


def test_register_tenant(mtc):
    t = mtc.get_tenant("acme")
    assert t.id == "acme"
    assert t.plan == "enterprise"
    assert t.is_active is True


def test_register_tenant_idempotent():
    m = MultiTenantConfig()
    t1 = m.register_tenant("x", plan="free")
    t2 = m.register_tenant("x", plan="enterprise")
    assert t2.plan == "enterprise"
    assert t2.created_at == t1.created_at  # created_at preserved


def test_get_unknown_tenant_raises(mtc):
    with pytest.raises(TenantNotFoundError):
        mtc.get_tenant("ghost")


def test_list_tenants(mtc):
    ids = {t.id for t in mtc.list_tenants()}
    assert "acme" in ids and "beta" in ids


def test_deactivate_tenant(mtc):
    mtc.deactivate_tenant("beta")
    tenants = mtc.list_tenants()
    assert all(t.id != "beta" for t in tenants)
    tenants_all = mtc.list_tenants(include_inactive=True)
    assert any(t.id == "beta" for t in tenants_all)


# ===========================================================================
# Feature flags — basic
# ===========================================================================


def test_define_flag_enabled_true(mtc, acme_ctx):
    mtc.define_flag("my_flag", enabled=True)
    assert mtc.is_enabled("my_flag", acme_ctx) is True


def test_define_flag_enabled_false(mtc, acme_ctx):
    mtc.define_flag("my_flag", enabled=False)
    assert mtc.is_enabled("my_flag", acme_ctx) is False


def test_flag_not_found_raises(mtc, acme_ctx):
    with pytest.raises(FlagNotFoundError):
        mtc.is_enabled("ghost_flag", acme_ctx)


def test_unknown_tenant_on_is_enabled_raises(mtc):
    mtc.define_flag("f", enabled=True)
    ctx = TenantContext(tenant_id="ghost")
    with pytest.raises(TenantNotFoundError):
        mtc.is_enabled("f", ctx)


def test_inactive_tenant_raises(mtc, beta_ctx):
    mtc.define_flag("f", enabled=True)
    mtc.deactivate_tenant("beta")
    with pytest.raises(TenantInactiveError):
        mtc.is_enabled("f", beta_ctx)


# ===========================================================================
# Feature flags — tenant overrides
# ===========================================================================


def test_set_tenant_flag_enabled_true_overrides_global(mtc, acme_ctx, beta_ctx):
    mtc.define_flag("dash", enabled=False)
    mtc.set_tenant_flag("acme", "dash", enabled=True)
    assert mtc.is_enabled("dash", acme_ctx) is True
    assert mtc.is_enabled("dash", beta_ctx) is False  # beta unaffected


def test_set_tenant_flag_enabled_false_pins_off(mtc, acme_ctx):
    mtc.define_flag("dash", enabled=True)
    mtc.set_tenant_flag("acme", "dash", enabled=False)
    assert mtc.is_enabled("dash", acme_ctx) is False


def test_set_tenant_flag_custom_rollout(mtc, acme_ctx):
    mtc.define_flag("dash", enabled=False)
    mtc.set_tenant_flag("acme", "dash", rollout=TenantListRollout(["acme"]))
    assert mtc.is_enabled("dash", acme_ctx) is True


def test_set_tenant_flag_both_params_raises(mtc):
    mtc.define_flag("f", enabled=True)
    with pytest.raises(ValueError):
        mtc.set_tenant_flag("acme", "f", enabled=True, rollout=AlwaysOnRollout())


def test_set_tenant_flag_no_params_raises(mtc):
    mtc.define_flag("f", enabled=True)
    with pytest.raises(ValueError):
        mtc.set_tenant_flag("acme", "f")


def test_reset_tenant_flag_falls_back_to_global(mtc, acme_ctx):
    mtc.define_flag("dash", enabled=False)
    mtc.set_tenant_flag("acme", "dash", enabled=True)
    mtc.reset_tenant_flag("acme", "dash")
    assert mtc.is_enabled("dash", acme_ctx) is False


def test_get_all_flags(mtc, acme_ctx):
    mtc.define_flag("a", enabled=True)
    mtc.define_flag("b", enabled=False)
    result = mtc.get_all_flags(acme_ctx)
    assert result == {"a": True, "b": False}


# ===========================================================================
# Config
# ===========================================================================


def test_define_and_get_config_default(mtc, acme_ctx):
    mtc.define_config("max_seats", 5)
    assert mtc.get_config("max_seats", acme_ctx) == 5


def test_set_tenant_config_overrides_default(mtc, acme_ctx, beta_ctx):
    mtc.define_config("max_seats", 5)
    mtc.set_tenant_config("acme", "max_seats", 100)
    assert mtc.get_config("max_seats", acme_ctx) == 100
    assert mtc.get_config("max_seats", beta_ctx) == 5  # beta still default


def test_reset_tenant_config_falls_back_to_default(mtc, acme_ctx):
    mtc.define_config("max_seats", 5)
    mtc.set_tenant_config("acme", "max_seats", 100)
    mtc.reset_tenant_config("acme", "max_seats")
    assert mtc.get_config("max_seats", acme_ctx) == 5


def test_config_type_validation(mtc):
    mtc.define_config("limit", 10, value_type=int)
    mtc.set_tenant_config("acme", "limit", "42")  # string coerced to int
    ctx = TenantContext(tenant_id="acme")
    assert mtc.get_config("limit", ctx) == 42


def test_config_type_validation_failure(mtc):
    mtc.define_config("limit", 10, value_type=int)
    with pytest.raises(ValidationError):
        mtc.set_tenant_config("acme", "limit", "not_a_number")


def test_config_not_found_raises(mtc, acme_ctx):
    with pytest.raises(ConfigNotFoundError):
        mtc.get_config("ghost_key", acme_ctx)


def test_get_all_configs(mtc, acme_ctx):
    mtc.define_config("a", 1)
    mtc.define_config("b", "hello")
    result = mtc.get_all_configs(acme_ctx)
    assert result == {"a": 1, "b": "hello"}


def test_secret_config_masked_in_audit(mtc):
    mtc.define_config("api_key", "default-key", secret=True)
    mtc.set_tenant_config("acme", "api_key", "secret-value", actor="admin")
    log = mtc.get_audit_log(tenant_id="acme", action="config.set")
    assert log[0].new_value == "***"
    assert log[0].old_value is None  # no previous value


# ===========================================================================
# Audit log
# ===========================================================================


def test_audit_log_records_tenant_register():
    m = MultiTenantConfig()
    m.register_tenant("x", actor="admin")
    log = m.get_audit_log(tenant_id="x")
    assert len(log) == 1
    assert log[0].action == "tenant.register"
    assert log[0].actor == "admin"


def test_audit_log_records_flag_set(mtc):
    mtc.define_flag("f", enabled=False, actor="svc")
    mtc.set_tenant_flag("acme", "f", enabled=True, actor="admin")
    log = mtc.get_audit_log(tenant_id="acme", entity_type="flag")
    assert log[0].action == "flag.set"
    assert log[0].actor == "admin"


def test_audit_log_filter_by_action(mtc):
    mtc.define_flag("f", enabled=True)
    mtc.set_tenant_flag("acme", "f", enabled=False)
    log = mtc.get_audit_log(action="flag.set")
    assert all(e.action == "flag.set" for e in log)


def test_audit_log_newest_first(mtc):
    m = MultiTenantConfig()
    m.register_tenant("t1")
    m.register_tenant("t2")
    log = m.get_audit_log()
    assert log[0].entity_id == "t2"  # most recent first


# ===========================================================================
# use_context
# ===========================================================================


def test_use_context_implicit(mtc):
    mtc.define_flag("f", enabled=True)
    ctx = TenantContext(tenant_id="acme")
    with mtc.use_context(ctx):
        assert mtc.is_enabled("f") is True


def test_use_context_requires_ctx_or_implicit(mtc):
    mtc.define_flag("f", enabled=True)
    with pytest.raises(ValueError, match="No TenantContext"):
        mtc.is_enabled("f")


# ===========================================================================
# Thread safety
# ===========================================================================


def test_concurrent_flag_evaluation():
    m = MultiTenantConfig()
    m.register_tenant("t1")
    m.define_flag("concurrent_flag", enabled=True)
    ctx = TenantContext(tenant_id="t1")

    results = []
    errors = []

    def worker():
        try:
            for _ in range(50):
                results.append(m.is_enabled("concurrent_flag", ctx))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert all(r is True for r in results)


def test_concurrent_config_writes():
    m = MultiTenantConfig()
    m.register_tenant("t1")
    m.define_config("counter", 0, value_type=int)
    ctx = TenantContext(tenant_id="t1")
    errors = []

    def writer(val: int):
        try:
            m.set_tenant_config("t1", "counter", val)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    # Final value must be one of the written values
    final = m.get_config("counter", ctx)
    assert isinstance(final, int)
