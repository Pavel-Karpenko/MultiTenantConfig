# multitenant-config

> Feature flags and config management for B2B SaaS — with per-tenant isolation, rollout strategies, and a full audit log.

[![CI](https://github.com/your-username/multitenant-config/actions/workflows/ci.yml/badge.svg)](https://github.com/your-username/multitenant-config/actions)
[![PyPI](https://img.shields.io/pypi/v/multitenant-config)](https://pypi.org/project/multitenant-config/)
[![Python](https://img.shields.io/pypi/pyversions/multitenant-config)](https://pypi.org/project/multitenant-config/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Why this exists

If you build a B2B SaaS product, you face the same problems over and over:

- **"Show the new dashboard only to Enterprise customers"** — without a tool, you scatter `if tenant.plan == "enterprise"` all over the codebase. A year later it's a mess.
- **"Roll out the new feature to 5% of users first, then 20%, then everyone"** — you hash things manually, pray nothing breaks, and redeploy every time.
- **"Acme Corp needs a 500-seat limit, everyone else gets 5"** — you either hardcode it or build yet another config table in your database from scratch.
- **"Who turned on that flag for that customer, and when?"** — you dig through git blame and hope for the best.

`multitenant-config` is a single place to answer all of this: **a feature flag and config system for B2B products where every customer has their own truth.**

```bash
pip install multitenant-config
```

No mandatory dependencies. Pure Python 3.9+.

---

## Quick start

```python
from multitenant_config import MultiTenantConfig, TenantContext, FileStorage

mtc = MultiTenantConfig(storage=FileStorage("/var/lib/myapp/config"))

# Register your customers
mtc.register_tenant("acme",    name="Acme Corp",    plan="enterprise")
mtc.register_tenant("startup", name="Startup Inc",  plan="free")

# Define a feature flag — off for everyone by default
mtc.define_flag("new_dashboard", enabled=False)

# Turn it on just for Acme
mtc.set_tenant_flag("acme", "new_dashboard", enabled=True, actor="admin")

# Evaluate — one line, works for any tenant
ctx = TenantContext(tenant_id="acme", user_id="alice")
if mtc.is_enabled("new_dashboard", ctx):
    return render("dashboard_v2.html")
```

---

## Examples

### Gradual feature rollout

Your team is shipping a redesigned billing page. You want to roll it out carefully — internal team first, then 10% of users, then everyone — without a single redeployment.

```python
from multitenant_config import (
    MultiTenantConfig, TenantContext, FileStorage,
    PercentageRollout, UserListRollout, OrRollout,
)

mtc = MultiTenantConfig(storage=FileStorage("/var/lib/myapp/config"))

# Step 1 — internal team only
mtc.define_flag(
    "new_billing_page",
    rollout=UserListRollout(["uid_ceo", "uid_cto", "uid_qa"]),
    actor="deploy-bot",
)

# Step 2 — internal team + 10% of all users
mtc.define_flag(
    "new_billing_page",
    rollout=OrRollout([
        UserListRollout(["uid_ceo", "uid_cto", "uid_qa"]),
        PercentageRollout(10),
    ]),
    actor="deploy-bot",
)

# Step 3 — full rollout
mtc.define_flag("new_billing_page", enabled=True, actor="deploy-bot")

# In your app — this line never changes across all three steps
ctx = TenantContext(tenant_id=request.tenant_id, user_id=request.user_id)
if mtc.is_enabled("new_billing_page", ctx):
    return render("billing_v2.html")
return render("billing_v1.html")
```

Each step is recorded in the audit log automatically. No redeploy needed between steps.

---

### Per-tenant limits by pricing plan

Three tiers: Free, Pro, Enterprise. Each has different limits. VIP customers get custom deals negotiated by sales.

```python
from multitenant_config import MultiTenantConfig, TenantContext, FileStorage

mtc = MultiTenantConfig(storage=FileStorage("/var/lib/myapp/config"))

# Declare configs with Free-plan defaults
mtc.define_config("max_seats",      default=3,     value_type=int)
mtc.define_config("api_rate_limit", default=100,   value_type=int, description="req/min")
mtc.define_config("storage_gb",     default=1,     value_type=int)
mtc.define_config("sso_enabled",    default=False)

def upgrade_to_pro(tenant_id: str, actor: str):
    mtc.set_tenant_config(tenant_id, "max_seats",      20,    actor=actor)
    mtc.set_tenant_config(tenant_id, "api_rate_limit", 1000,  actor=actor)
    mtc.set_tenant_config(tenant_id, "storage_gb",     50,    actor=actor)

def upgrade_to_enterprise(tenant_id: str, actor: str):
    mtc.set_tenant_config(tenant_id, "max_seats",      500,   actor=actor)
    mtc.set_tenant_config(tenant_id, "api_rate_limit", 10000, actor=actor)
    mtc.set_tenant_config(tenant_id, "storage_gb",     1000,  actor=actor)
    mtc.set_tenant_config(tenant_id, "sso_enabled",    True,  actor=actor)

# Acme Corp negotiated a custom deal
upgrade_to_enterprise("acme_corp", actor="sales@company.com")
mtc.set_tenant_config("acme_corp", "max_seats", 2000, actor="sales@company.com")

# In your app — just read the value, no plan logic needed
ctx = TenantContext(tenant_id="acme_corp")
limit   = mtc.get_config("max_seats",      ctx)   # 2000
rate    = mtc.get_config("api_rate_limit", ctx)   # 10000
has_sso = mtc.get_config("sso_enabled",   ctx)   # True

# Who changed what, and when
for entry in mtc.get_audit_log(tenant_id="acme_corp"):
    print(f"{entry.timestamp:%Y-%m-%d}  {entry.actor:30s}  {entry.entity_id} → {entry.new_value}")
# 2025-03-12  sales@company.com              max_seats → 2000
# 2025-03-12  sales@company.com              sso_enabled → True
# ...
```

---

## Feature flags

```python
from multitenant_config import PercentageRollout, AndRollout, ScheduledRollout
from datetime import datetime, timezone

# Gradual rollout — 20% of users, consistent (same user always gets same result)
mtc.define_flag("beta_export", rollout=PercentageRollout(20))

# Time-limited campaign AND percentage
mtc.define_flag(
    "holiday_promo",
    rollout=AndRollout([
        ScheduledRollout(
            start_at=datetime(2025, 12, 1, tzinfo=timezone.utc),
            end_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        PercentageRollout(50),
    ]),
)

# Evaluate all flags for a context in one call
flags = mtc.get_all_flags(ctx)
# {"beta_export": True, "holiday_promo": False, "new_dashboard": True, ...}
```

### Rollout strategies

| Strategy | Description |
|---|---|
| `AlwaysOnRollout()` | Enabled for everyone |
| `AlwaysOffRollout()` | Disabled for everyone |
| `PercentageRollout(pct, sticky_by="user")` | Hash-based; deterministic per user or tenant |
| `UserListRollout(["uid1", ...])` | Specific user IDs |
| `TenantListRollout(["tid1", ...])` | Specific tenant IDs |
| `ScheduledRollout(start_at, end_at)` | Active within a time window |
| `AndRollout([s1, s2, ...])` | All sub-strategies must pass |
| `OrRollout([s1, s2, ...])` | Any sub-strategy must pass |

`PercentageRollout` uses a SHA-256 hash of `flag_name + tenant_id + user_id`, so the same user always lands in the same bucket — no flickering between requests.

---

## Config management

```python
# Define global keys with defaults and optional type enforcement
mtc.define_config("max_seats",    default=5,   value_type=int)
mtc.define_config("webhook_url",  default="")
mtc.define_config("stripe_key",   default="",  secret=True)  # value masked in audit log

# Override for a specific tenant
mtc.set_tenant_config("acme", "max_seats", 500, actor="admin")

# Resolution order: tenant override → global default
mtc.get_config("max_seats", TenantContext("acme"))     # 500
mtc.get_config("max_seats", TenantContext("startup"))  # 5

# Remove override — falls back to default
mtc.reset_tenant_config("acme", "max_seats", actor="admin")

# All configs at once
all_cfg = mtc.get_all_configs(ctx)
```

---

## Audit log

Every mutation is recorded automatically. No extra setup required.

```python
entries = mtc.get_audit_log(
    tenant_id="acme",
    entity_type="flag",    # "flag" | "config" | "tenant"
    action="flag.set",
    actor="admin",
    limit=50,
)

for e in entries:
    print(e.timestamp, e.actor, e.action, e.entity_id, e.old_value, "→", e.new_value)
```

### Forwarding to an external system

```python
import requests

def send_to_datadog(entry):
    requests.post("https://http-intake.logs.datadoghq.com/v1/input", json=entry.to_dict())

mtc.add_audit_handler(send_to_datadog)
# or at construction time:
mtc = MultiTenantConfig(audit_handlers=[send_to_datadog])
```

### Audit actions reference

| Action | Triggered by |
|---|---|
| `tenant.register` / `tenant.update` | `register_tenant()` |
| `tenant.deactivate` | `deactivate_tenant()` |
| `flag.define` / `flag.update` | `define_flag()` |
| `flag.set` / `flag.reset` | `set_tenant_flag()` / `reset_tenant_flag()` |
| `config.define` / `config.update` | `define_config()` |
| `config.set` / `config.reset` | `set_tenant_config()` / `reset_tenant_config()` |

---

## Implicit context

Avoid threading `ctx` through every call in a request handler:

```python
ctx = TenantContext(tenant_id=request.tenant_id, user_id=request.user_id)

with mtc.use_context(ctx):
    if mtc.is_enabled("new_dashboard"):
        seats = mtc.get_config("max_seats")
        ...
```

Uses `contextvars` under the hood — works correctly with threads and `asyncio`.

---

## Storage backends

```python
# In-memory — no persistence, perfect for tests and development
mtc = MultiTenantConfig()  # InMemoryStorage is the default

# File-based — persists to disk, survives restarts
from multitenant_config import FileStorage
mtc = MultiTenantConfig(storage=FileStorage("/var/lib/myapp/config"))
mtc = MultiTenantConfig(storage=FileStorage("/var/lib/myapp/config", fmt="yaml"))  # requires pyyaml
```

### Implementing a custom backend

Subclass `StorageBackend` and implement its 15 methods (all accept/return plain dicts):

```python
from multitenant_config import StorageBackend

class RedisStorage(StorageBackend):
    def __init__(self, client):
        self.r = client

    def get_tenant(self, tenant_id):
        raw = self.r.get(f"tenant:{tenant_id}")
        return json.loads(raw) if raw else None

    def save_tenant(self, tenant_id, data):
        self.r.set(f"tenant:{tenant_id}", json.dumps(data))

    # ... implement the remaining 13 methods
```

---

## Thread safety

All built-in components are thread-safe out of the box:

| Component | Mechanism |
|---|---|
| `InMemoryStorage` | `threading.RLock` |
| `FileStorage` | `threading.RLock` + atomic `os.replace()` writes |
| `AuditLog` | `threading.Lock` |
| `MultiTenantConfig` | `threading.RLock` |
| `use_context()` | `contextvars.ContextVar` |

---

## Development

```bash
git clone https://github.com/your-username/multitenant-config
cd multitenant-config
pip install -e ".[dev]"

pytest                           # run all tests (105 total)
pytest tests/test_rollout.py     # single file
pytest -k test_percentage        # single test by name
mypy multitenant_config          # type check
ruff check multitenant_config    # lint
```

---

## License

[MIT](LICENSE)
