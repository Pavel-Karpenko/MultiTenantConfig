"""Shared fixtures."""
import pytest

from multitenant_config import InMemoryStorage, MultiTenantConfig, TenantContext


@pytest.fixture
def mtc() -> MultiTenantConfig:
    m = MultiTenantConfig(storage=InMemoryStorage())
    m.register_tenant("acme", name="Acme Corp", plan="enterprise")
    m.register_tenant("beta", name="Beta Inc", plan="free")
    return m


@pytest.fixture
def acme_ctx() -> TenantContext:
    return TenantContext(tenant_id="acme", user_id="user_1")


@pytest.fixture
def beta_ctx() -> TenantContext:
    return TenantContext(tenant_id="beta", user_id="user_2")
