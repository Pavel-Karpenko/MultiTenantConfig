"""File-based storage backend.

Layout under *root_dir*::

    root_dir/
        tenants/<tenant_id>.json
        flags/<flag_name>.json
        tenant_flags/<tenant_id>/<flag_name>.json
        configs/<config_key>.json
        tenant_configs/<tenant_id>/<config_key>.json

Each file is a JSON object.  Atomic writes are done via a temp-file rename
so a crash mid-write never corrupts data.

YAML is supported when ``pyyaml`` is installed — pass ``fmt="yaml"``.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from .base import StorageBackend


def _load_yaml_or_raise() -> Any:
    try:
        import yaml  # type: ignore[import]

        return yaml
    except ImportError as exc:
        raise ImportError(
            "pyyaml is required for YAML storage: pip install multitenant-config[yaml]"
        ) from exc


class FileStorage(StorageBackend):
    """Persistent file-based storage backend.

    Parameters
    ----------
    root_dir:
        Directory where all data files are stored.  Created automatically.
    fmt:
        ``"json"`` (default) or ``"yaml"`` (requires pyyaml).
    """

    def __init__(self, root_dir: str | Path, fmt: str = "json") -> None:
        if fmt not in ("json", "yaml"):
            raise ValueError(f"fmt must be 'json' or 'yaml', got {fmt!r}")
        self._root = Path(root_dir)
        self._fmt = fmt
        self._ext = f".{fmt}"
        self._lock = threading.RLock()
        self._root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _path(self, *parts: str) -> Path:
        return self._root.joinpath(*parts).with_suffix(self._ext)

    def _read(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as fh:
            if self._fmt == "yaml":
                yaml = _load_yaml_or_raise()
                return yaml.safe_load(fh)  # type: ignore[no-any-return]
            return json.load(fh)  # type: ignore[no-any-return]

    def _write(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                if self._fmt == "yaml":
                    yaml = _load_yaml_or_raise()
                    yaml.safe_dump(data, fh, allow_unicode=True)
                else:
                    json.dump(data, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _delete(self, path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def _list_names(self, directory: Path) -> list[str]:
        if not directory.exists():
            return []
        return [
            p.stem
            for p in directory.iterdir()
            if p.suffix == self._ext and p.is_file()
        ]

    # ------------------------------------------------------------------
    # Tenant
    # ------------------------------------------------------------------

    def get_tenant(self, tenant_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._read(self._path("tenants", tenant_id))

    def save_tenant(self, tenant_id: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._write(self._path("tenants", tenant_id), data)

    def list_tenant_ids(self) -> list[str]:
        with self._lock:
            return self._list_names(self._root / "tenants")

    def delete_tenant(self, tenant_id: str) -> None:
        with self._lock:
            self._delete(self._path("tenants", tenant_id))

    # ------------------------------------------------------------------
    # Flag definitions
    # ------------------------------------------------------------------

    def get_flag(self, flag_name: str) -> dict[str, Any] | None:
        with self._lock:
            return self._read(self._path("flags", flag_name))

    def save_flag(self, flag_name: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._write(self._path("flags", flag_name), data)

    def list_flag_names(self) -> list[str]:
        with self._lock:
            return self._list_names(self._root / "flags")

    def delete_flag(self, flag_name: str) -> None:
        with self._lock:
            self._delete(self._path("flags", flag_name))

    # ------------------------------------------------------------------
    # Tenant flag overrides
    # ------------------------------------------------------------------

    def get_tenant_flag(self, tenant_id: str, flag_name: str) -> dict[str, Any] | None:
        with self._lock:
            return self._read(self._path("tenant_flags", tenant_id, flag_name))

    def save_tenant_flag(self, tenant_id: str, flag_name: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._write(self._path("tenant_flags", tenant_id, flag_name), data)

    def list_tenant_flag_names(self, tenant_id: str) -> list[str]:
        with self._lock:
            return self._list_names(self._root / "tenant_flags" / tenant_id)

    def delete_tenant_flag(self, tenant_id: str, flag_name: str) -> None:
        with self._lock:
            self._delete(self._path("tenant_flags", tenant_id, flag_name))

    # ------------------------------------------------------------------
    # Config definitions
    # ------------------------------------------------------------------

    def get_config(self, config_key: str) -> dict[str, Any] | None:
        with self._lock:
            return self._read(self._path("configs", config_key))

    def save_config(self, config_key: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._write(self._path("configs", config_key), data)

    def list_config_keys(self) -> list[str]:
        with self._lock:
            return self._list_names(self._root / "configs")

    def delete_config(self, config_key: str) -> None:
        with self._lock:
            self._delete(self._path("configs", config_key))

    # ------------------------------------------------------------------
    # Tenant config overrides
    # ------------------------------------------------------------------

    def get_tenant_config(self, tenant_id: str, config_key: str) -> dict[str, Any] | None:
        with self._lock:
            return self._read(self._path("tenant_configs", tenant_id, config_key))

    def save_tenant_config(self, tenant_id: str, config_key: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._write(self._path("tenant_configs", tenant_id, config_key), data)

    def list_tenant_config_keys(self, tenant_id: str) -> list[str]:
        with self._lock:
            return self._list_names(self._root / "tenant_configs" / tenant_id)

    def delete_tenant_config(self, tenant_id: str, config_key: str) -> None:
        with self._lock:
            self._delete(self._path("tenant_configs", tenant_id, config_key))
