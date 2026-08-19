"""Local-only storage for credentials and private knowledge assets.

The storage root is intentionally excluded from version control. Secrets are never
returned by API responses and can be relocated with ``AI_TEST_LOCAL_DATA_PATH``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock


LOCAL_DATA_ROOT = Path(
    os.environ.get(
        "AI_TEST_LOCAL_DATA_PATH",
        str(Path(__file__).resolve().parents[1] / ".local"),
    )
).resolve()
SECRETS_PATH = LOCAL_DATA_ROOT / "secrets.json"
_LOCK = RLock()


def _read_secrets() -> dict[str, str]:
    """Read the local secret map without exposing it outside this module."""

    if not SECRETS_PATH.exists():
        return {}
    try:
        payload = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {
        str(key): str(value)
        for key, value in payload.items()
        if isinstance(key, str) and isinstance(value, str)
    }


def _write_secrets(secrets: dict[str, str]) -> None:
    """Atomically persist secrets in the ignored local data directory."""

    LOCAL_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    temporary = SECRETS_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(secrets, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    temporary.replace(SECRETS_PATH)


def set_secret(secret_id: str, value: str) -> None:
    """Create or replace one local-only secret."""

    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Secret 不能为空")
    with _LOCK:
        secrets = _read_secrets()
        secrets[secret_id] = cleaned
        _write_secrets(secrets)


def get_secret(secret_id: str) -> str | None:
    """Resolve a secret for an outbound request without serializing it."""

    with _LOCK:
        return _read_secrets().get(secret_id)


def has_secret(secret_id: str) -> bool:
    """Return whether a non-empty local secret exists."""

    return bool(get_secret(secret_id))


def delete_secret(secret_id: str) -> None:
    """Remove a secret while preserving unrelated local credentials."""

    with _LOCK:
        secrets = _read_secrets()
        if secret_id not in secrets:
            return
        secrets.pop(secret_id)
        _write_secrets(secrets)


def mask_secret(secret_id: str) -> str:
    """Return a non-reversible display mask for configured credentials."""

    secret = get_secret(secret_id)
    if not secret:
        return ""
    suffix = secret[-4:] if len(secret) >= 4 else "••••"
    return f"••••••••{suffix}"


def store_knowledge_file(
    project_id: str,
    knowledge_base_id: str,
    document_id: str,
    filename: str,
    content: bytes,
) -> str:
    """Persist a private knowledge file and return a root-relative path."""

    safe_name = Path(filename).name or "document.txt"
    target_dir = LOCAL_DATA_ROOT / "knowledge" / project_id / knowledge_base_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{document_id}-{safe_name}"
    target.write_bytes(content)
    relative = target.relative_to(LOCAL_DATA_ROOT)
    return relative.as_posix()
