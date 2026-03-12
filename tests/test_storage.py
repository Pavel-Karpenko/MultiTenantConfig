"""Tests for storage backends — shared contract via parametrize."""
import tempfile

import pytest

from multitenant_config import FileStorage, InMemoryStorage
from multitenant_config.storage.base import StorageBackend


def make_backends():
    tmp = tempfile.mkdtemp()
    return [InMemoryStorage(), FileStorage(tmp)]


@pytest.fixture(params=["memory", "file"])
def backend(request, tmp_path) -> StorageBackend:
    if request.param == "memory":
        return InMemoryStorage()
    return FileStorage(tmp_path / "data")


# ---------------------------------------------------------------------------
# Tenant
# ---------------------------------------------------------------------------


def test_tenant_save_get(backend):
    backend.save_tenant("t1", {"id": "t1", "name": "Acme"})
    result = backend.get_tenant("t1")
    assert result is not None
    assert result["name"] == "Acme"


def test_tenant_get_missing(backend):
    assert backend.get_tenant("ghost") is None


def test_tenant_list(backend):
    backend.save_tenant("t1", {"id": "t1"})
    backend.save_tenant("t2", {"id": "t2"})
    assert set(backend.list_tenant_ids()) >= {"t1", "t2"}


def test_tenant_delete(backend):
    backend.save_tenant("t1", {"id": "t1"})
    backend.delete_tenant("t1")
    assert backend.get_tenant("t1") is None


# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------


def test_flag_save_get(backend):
    backend.save_flag("my_flag", {"name": "my_flag"})
    assert backend.get_flag("my_flag") == {"name": "my_flag"}


def test_flag_delete(backend):
    backend.save_flag("f", {"name": "f"})
    backend.delete_flag("f")
    assert backend.get_flag("f") is None


def test_tenant_flag_override(backend):
    backend.save_tenant_flag("t1", "f1", {"enabled": True})
    assert backend.get_tenant_flag("t1", "f1") == {"enabled": True}
    assert backend.get_tenant_flag("t2", "f1") is None


def test_tenant_flag_list(backend):
    backend.save_tenant_flag("t1", "a", {})
    backend.save_tenant_flag("t1", "b", {})
    assert set(backend.list_tenant_flag_names("t1")) == {"a", "b"}


def test_tenant_flag_delete(backend):
    backend.save_tenant_flag("t1", "f", {"x": 1})
    backend.delete_tenant_flag("t1", "f")
    assert backend.get_tenant_flag("t1", "f") is None


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_config_save_get(backend):
    backend.save_config("key", {"key": "key", "default": 5})
    result = backend.get_config("key")
    assert result is not None
    assert result["default"] == 5


def test_tenant_config_override(backend):
    backend.save_tenant_config("t1", "key", {"value": 99})
    assert backend.get_tenant_config("t1", "key") == {"value": 99}
    assert backend.get_tenant_config("t2", "key") is None


def test_tenant_config_delete(backend):
    backend.save_tenant_config("t1", "k", {"value": 1})
    backend.delete_tenant_config("t1", "k")
    assert backend.get_tenant_config("t1", "k") is None


# ---------------------------------------------------------------------------
# FileStorage — isolation between write calls
# ---------------------------------------------------------------------------


def test_file_storage_deep_copy(tmp_path):
    """Writes to the returned dict must not mutate stored data."""
    fs = FileStorage(tmp_path / "data")
    data = {"key": "k", "value": [1, 2, 3]}
    fs.save_config("k", data)
    retrieved = fs.get_config("k")
    assert retrieved is not None
    retrieved["value"].append(99)
    assert fs.get_config("k")["value"] == [1, 2, 3]  # type: ignore[index]


def test_file_storage_yaml(tmp_path):
    pytest.importorskip("yaml")
    fs = FileStorage(tmp_path / "data", fmt="yaml")
    fs.save_tenant("t", {"id": "t", "plan": "pro"})
    assert fs.get_tenant("t")["plan"] == "pro"  # type: ignore[index]
