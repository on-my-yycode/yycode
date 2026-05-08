"""Persistence for canonical session message history."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from langchain_core.messages import BaseMessage, messages_from_dict, messages_to_dict


SESSION_VERSION = 1


class SessionStoreError(RuntimeError):
    """Raised when persisted session data cannot be safely used."""


@dataclass(frozen=True)
class SessionRecord:
    """Small listing record for a persisted session."""

    session_id: str
    path: Path
    updated_at: str
    workdir: str


class SessionStore:
    """Abstract session message store."""

    def load(self, session_id: str) -> list[BaseMessage]:
        raise NotImplementedError

    def save(
        self,
        session_id: str,
        messages: list[BaseMessage],
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        raise NotImplementedError

    def delete(self, session_id: str) -> None:
        raise NotImplementedError

    def list_sessions(self) -> list[SessionRecord]:
        raise NotImplementedError


class FileSessionStore(SessionStore):
    """File-backed message store grouped by workspace hash."""

    def __init__(
        self,
        app_root: Path,
        workdir: Path,
        root: Path | str | None = None,
    ) -> None:
        self.app_root = app_root.expanduser().resolve()
        self.workdir = workdir.expanduser().resolve()
        raw_root = root or os.environ.get("YOYO_SESSION_DIR")
        self.root = Path(raw_root).expanduser().resolve() if raw_root else self.app_root / "sessions"
        self.workspace_hash = workspace_hash(self.workdir)

    @property
    def workspace_dir(self) -> Path:
        return self.root / self.workspace_hash

    def load(self, session_id: str) -> list[BaseMessage]:
        path = self._session_path(session_id)
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SessionStoreError(f"Session file is not valid JSON: {path}") from exc

        if payload.get("version") != SESSION_VERSION:
            raise SessionStoreError(f"Unsupported session file version: {payload.get('version')}")

        saved_workdir = Path(str(payload.get("workdir", ""))).expanduser().resolve()
        if saved_workdir != self.workdir:
            raise SessionStoreError(
                f"Session workdir mismatch: saved {saved_workdir}, current {self.workdir}"
            )

        try:
            return list(messages_from_dict(payload.get("messages", [])))
        except Exception as exc:
            raise SessionStoreError(f"Could not deserialize session messages: {path}") from exc

    def save(
        self,
        session_id: str,
        messages: list[BaseMessage],
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        path = self._session_path(session_id)
        now = _utc_now()
        existing = self._read_existing(path)
        payload = {
            "version": SESSION_VERSION,
            "session_id": session_id,
            "created_at": existing.get("created_at") or now,
            "updated_at": now,
            "workdir": str(self.workdir),
            "workspace_hash": self.workspace_hash,
            "app_root": str(self.app_root),
            "model": (metadata or {}).get("model"),
            "messages": messages_to_dict(messages),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(path, payload)

    def delete(self, session_id: str) -> None:
        path = self._session_path(session_id)
        if path.exists():
            path.unlink()

    def list_sessions(self) -> list[SessionRecord]:
        if not self.workspace_dir.exists():
            return []
        records: list[SessionRecord] = []
        for path in sorted(self.workspace_dir.glob("*.json")):
            payload = self._read_existing(path)
            records.append(
                SessionRecord(
                    session_id=str(payload.get("session_id") or path.stem),
                    path=path,
                    updated_at=str(payload.get("updated_at") or ""),
                    workdir=str(payload.get("workdir") or ""),
                )
            )
        return records

    def _session_path(self, session_id: str) -> Path:
        safe_id = _safe_session_id(session_id)
        return self.workspace_dir / f"{safe_id}.json"

    def _read_existing(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}


def workspace_hash(workdir: Path) -> str:
    """Return a short stable hash for a resolved workspace path."""
    normalized = str(workdir.expanduser().resolve())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _safe_session_id(session_id: str) -> str:
    if not session_id or session_id in {".", ".."}:
        raise SessionStoreError("Session id must not be empty")
    if any(separator in session_id for separator in ("/", "\\")):
        raise SessionStoreError("Session id must not contain path separators")
    return session_id


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write(data)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)
