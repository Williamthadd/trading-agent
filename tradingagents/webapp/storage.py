"""Persistence adapters for TradingAgents web runs.

The web application prefers Cloud Firestore when server-side credentials are
configured.  A small JSON store is always available as a zero-configuration
fallback, which keeps the UI usable for local development.

Firebase imports intentionally live inside :func:`build_run_store` so the core
TradingAgents package can still be imported without ``firebase-admin``.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import math
import os
import tempfile
import threading
import time
import uuid
from collections.abc import Mapping
from contextlib import suppress
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)
RUNS_COLLECTION = "trading_runs"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _datetime_to_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_safe(value: Any) -> Any:
    """Return a recursively JSON/Firestore-safe copy of ``value``."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, datetime):
        return _datetime_to_iso(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, Path):
        return str(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _json_safe(dataclasses.asdict(value))
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return _json_safe(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_json_safe(item) for item in value), key=str)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _as_document(value: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return dict(_json_safe(value))


def _validate_id(value: Any, *, label: str) -> str:
    identifier = str(value or "").strip()
    if not identifier:
        raise ValueError(f"{label} cannot be empty")
    # Firestore document IDs are a single path segment.  Applying the same
    # validation to the local backend keeps behavior consistent on failover.
    if "/" in identifier or identifier in {".", ".."}:
        raise ValueError(f"{label} must be a single path segment")
    if len(identifier.encode("utf-8")) > 1_500:
        raise ValueError(f"{label} is too long")
    return identifier


def _timestamp(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except ValueError:
            return 0.0
    return 0.0


def _sort_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        runs,
        key=lambda run: (
            _timestamp(run.get("created_at") or run.get("updated_at")),
            str(run.get("run_id", "")),
        ),
        reverse=True,
    )


def _sort_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(event: dict[str, Any]) -> tuple[float, float, str]:
        sequence = event.get("sequence")
        try:
            sequence_value = float(sequence)
        except (TypeError, ValueError):
            sequence_value = float("inf")
        return (
            sequence_value,
            _timestamp(event.get("created_at")),
            str(event.get("event_id", "")),
        )

    return sorted(events, key=key)


def _prepare_run(document: Mapping[str, Any]) -> dict[str, Any]:
    payload = _as_document(document, label="run document")
    run_id = _validate_id(
        payload.get("run_id") or payload.get("id") or uuid.uuid4().hex,
        label="run_id",
    )
    created_at = payload.get("created_at") or _utc_now()
    payload["run_id"] = run_id
    payload["created_at"] = created_at
    payload.setdefault("updated_at", created_at)
    payload.setdefault("date_key", str(created_at)[:10])
    return payload


def _prepare_event(
    run_id: str,
    event: Mapping[str, Any],
    *,
    default_sequence: int | None = None,
) -> dict[str, Any]:
    payload = _as_document(event, label="event")
    payload["run_id"] = _validate_id(run_id, label="run_id")
    payload["event_id"] = _validate_id(
        payload.get("event_id") or payload.get("id") or uuid.uuid4().hex,
        label="event_id",
    )
    payload.setdefault("created_at", _utc_now())
    if payload.get("sequence") is None:
        payload["sequence"] = default_sequence if default_sequence is not None else time.time_ns()
    return payload


class LocalJsonRunStore:
    """Thread-safe, atomic JSON persistence for local development."""

    configured = False
    backend_name = "local-json"

    def __init__(self, data_dir: str | os.PathLike[str]) -> None:
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.events_dir = self.data_dir / "events"
        self.runs_path = self.data_dir / "runs.json"
        self._lock = threading.RLock()
        self.events_dir.mkdir(parents=True, exist_ok=True)

    def _read(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            LOGGER.warning("Ignoring unreadable local history file %s: %s", path, exc)
            return default

    def _write(self, path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_name = handle.name
                json.dump(
                    _json_safe(value),
                    handle,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        finally:
            if temporary_name and os.path.exists(temporary_name):
                with suppress(OSError):
                    os.unlink(temporary_name)

    def _runs(self) -> dict[str, dict[str, Any]]:
        content = self._read(self.runs_path, {"version": 1, "runs": {}})
        if not isinstance(content, dict) or not isinstance(content.get("runs"), dict):
            return {}
        return content["runs"]

    def _event_path(self, run_id: str) -> Path:
        digest = hashlib.sha256(run_id.encode("utf-8")).hexdigest()
        return self.events_dir / f"{digest}.json"

    def create_run(self, document: Mapping[str, Any]) -> dict[str, Any]:
        payload = _prepare_run(document)
        with self._lock:
            runs = self._runs()
            runs[payload["run_id"]] = payload
            self._write(self.runs_path, {"version": 1, "runs": runs})
        return dict(payload)

    def append_event(self, run_id: str, event: Mapping[str, Any]) -> dict[str, Any]:
        run_id = _validate_id(run_id, label="run_id")
        path = self._event_path(run_id)
        with self._lock:
            content = self._read(path, {"version": 1, "run_id": run_id, "events": []})
            events = content.get("events", []) if isinstance(content, dict) else []
            if not isinstance(events, list):
                events = []
            supplied_sequence = event.get("sequence")
            if supplied_sequence is None:
                numeric_sequences = [
                    item.get("sequence")
                    for item in events
                    if isinstance(item, dict) and isinstance(item.get("sequence"), int)
                ]
                default_sequence = max(numeric_sequences, default=0) + 1
            else:
                default_sequence = None
            payload = _prepare_event(
                run_id,
                event,
                default_sequence=default_sequence,
            )
            events.append(payload)
            self._write(
                path,
                {"version": 1, "run_id": run_id, "events": events},
            )
        return dict(payload)

    def update_run(self, run_id: str, updates: Mapping[str, Any]) -> dict[str, Any]:
        run_id = _validate_id(run_id, label="run_id")
        changes = _as_document(updates, label="run updates")
        changes.pop("run_id", None)
        with self._lock:
            runs = self._runs()
            current = runs.get(run_id)
            if not isinstance(current, dict):
                current = _prepare_run({"run_id": run_id})
            current.update(changes)
            current["run_id"] = run_id
            current["updated_at"] = changes.get("updated_at") or _utc_now()
            runs[run_id] = current
            self._write(self.runs_path, {"version": 1, "runs": runs})
        return dict(current)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        run_id = _validate_id(run_id, label="run_id")
        with self._lock:
            document = self._runs().get(run_id)
        return dict(document) if isinstance(document, dict) else None

    def list_runs(self, date_key: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            documents = [
                dict(document) for document in self._runs().values() if isinstance(document, dict)
            ]
        if date_key:
            documents = [
                document
                for document in documents
                if str(document.get("date_key", "")) == str(date_key)
            ]
        return _sort_runs(documents)

    def list_runs_by_statuses(self, statuses: set[str]) -> list[dict[str, Any]]:
        """Return only runs whose normalized status is in ``statuses``."""
        wanted = {str(status).strip().lower() for status in statuses if str(status).strip()}
        if not wanted:
            return []
        with self._lock:
            documents = [
                dict(document)
                for document in self._runs().values()
                if isinstance(document, dict)
                and str(document.get("status", "")).strip().lower() in wanted
            ]
        return _sort_runs(documents)

    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        run_id = _validate_id(run_id, label="run_id")
        with self._lock:
            content = self._read(
                self._event_path(run_id),
                {"version": 1, "run_id": run_id, "events": []},
            )
            events = content.get("events", []) if isinstance(content, dict) else []
            documents = [dict(event) for event in events if isinstance(event, dict)]
        return _sort_events(documents)


class FirestoreRunStore:
    """Firestore store with a mirrored local store for transparent failover."""

    def __init__(
        self,
        client: Any,
        local_fallback: LocalJsonRunStore,
        collection_name: str = RUNS_COLLECTION,
    ) -> None:
        self._client = client
        self._local = local_fallback
        self._collection_name = _validate_id(collection_name, label="FIREBASE_COLLECTION")
        self._active = True
        self._state_lock = threading.RLock()

    @property
    def configured(self) -> bool:
        return self._active

    @property
    def backend_name(self) -> str:
        return "firestore" if self._active else self._local.backend_name

    def _disable(self, operation: str, exc: Exception) -> None:
        with self._state_lock:
            self._active = False
        LOGGER.warning(
            "Firestore %s failed (%s); continuing with local JSON history.",
            operation,
            exc,
        )

    def _mirror(self, method: str, *args: Any) -> None:
        try:
            getattr(self._local, method)(*args)
        except Exception as exc:  # pragma: no cover - defensive; Firebase succeeded
            LOGGER.warning("Could not mirror Firestore data locally: %s", exc)

    def create_run(self, document: Mapping[str, Any]) -> dict[str, Any]:
        payload = _prepare_run(document)
        if not self._active:
            return self._local.create_run(payload)
        try:
            self._client.collection(self._collection_name).document(payload["run_id"]).set(payload)
            self._mirror("create_run", payload)
            return dict(payload)
        except Exception as exc:
            self._disable("create_run", exc)
            return self._local.create_run(payload)

    def append_event(self, run_id: str, event: Mapping[str, Any]) -> dict[str, Any]:
        payload = _prepare_event(run_id, event)
        if not self._active:
            return self._local.append_event(run_id, payload)
        try:
            run_ref = self._client.collection(self._collection_name).document(payload["run_id"])
            run_ref.collection("events").document(payload["event_id"]).set(payload)
            self._mirror("append_event", run_id, payload)
            return dict(payload)
        except Exception as exc:
            self._disable("append_event", exc)
            return self._local.append_event(run_id, payload)

    def update_run(self, run_id: str, updates: Mapping[str, Any]) -> dict[str, Any]:
        run_id = _validate_id(run_id, label="run_id")
        changes = _as_document(updates, label="run updates")
        changes.pop("run_id", None)
        changes["updated_at"] = changes.get("updated_at") or _utc_now()
        if not self._active:
            return self._local.update_run(run_id, changes)
        try:
            reference = self._client.collection(self._collection_name).document(run_id)
            reference.set(changes, merge=True)
            snapshot = reference.get()
            payload = dict(_json_safe(snapshot.to_dict() or changes))
            payload["run_id"] = run_id
            self._mirror("update_run", run_id, changes)
            return payload
        except Exception as exc:
            self._disable("update_run", exc)
            return self._local.update_run(run_id, changes)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        run_id = _validate_id(run_id, label="run_id")
        if not self._active:
            return self._local.get_run(run_id)
        try:
            snapshot = self._client.collection(self._collection_name).document(run_id).get()
            if not snapshot.exists:
                return None
            payload = dict(_json_safe(snapshot.to_dict() or {}))
            payload["run_id"] = run_id
            return payload
        except Exception as exc:
            self._disable("get_run", exc)
            return self._local.get_run(run_id)

    def list_runs(self, date_key: str | None = None) -> list[dict[str, Any]]:
        if not self._active:
            return self._local.list_runs(date_key)
        try:
            query = self._client.collection(self._collection_name)
            if date_key:
                try:
                    # Current google-cloud-firestore versions prefer the
                    # keyword filter API. Keep the positional call as a
                    # compatibility fallback for older SDKs/test doubles.
                    from google.cloud.firestore_v1.base_query import FieldFilter

                    query = query.where(filter=FieldFilter("date_key", "==", str(date_key)))
                except (ImportError, TypeError):
                    query = query.where("date_key", "==", str(date_key))
            documents: list[dict[str, Any]] = []
            for snapshot in query.stream():
                payload = dict(_json_safe(snapshot.to_dict() or {}))
                payload["run_id"] = payload.get("run_id") or snapshot.id
                documents.append(payload)
            return _sort_runs(documents)
        except Exception as exc:
            self._disable("list_runs", exc)
            return self._local.list_runs(date_key)

    def list_runs_by_statuses(self, statuses: set[str]) -> list[dict[str, Any]]:
        """Query active-status documents without scanning the full history."""
        wanted = sorted({str(status).strip().lower() for status in statuses if str(status).strip()})
        if not wanted:
            return []
        if not self._active:
            return self._local.list_runs_by_statuses(set(wanted))
        try:
            query = self._client.collection(self._collection_name)
            try:
                from google.cloud.firestore_v1.base_query import FieldFilter

                query = query.where(filter=FieldFilter("status", "in", wanted))
            except (ImportError, TypeError):
                query = query.where("status", "in", wanted)
            documents: list[dict[str, Any]] = []
            for snapshot in query.stream():
                payload = dict(_json_safe(snapshot.to_dict() or {}))
                payload["run_id"] = payload.get("run_id") or snapshot.id
                documents.append(payload)
            return _sort_runs(documents)
        except Exception as exc:
            self._disable("list_runs_by_statuses", exc)
            return self._local.list_runs_by_statuses(set(wanted))

    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        run_id = _validate_id(run_id, label="run_id")
        if not self._active:
            return self._local.get_events(run_id)
        try:
            snapshots = (
                self._client.collection(self._collection_name)
                .document(run_id)
                .collection("events")
                .stream()
            )
            documents: list[dict[str, Any]] = []
            for snapshot in snapshots:
                payload = dict(_json_safe(snapshot.to_dict() or {}))
                payload["event_id"] = payload.get("event_id") or snapshot.id
                payload["run_id"] = run_id
                documents.append(payload)
            return _sort_events(documents)
        except Exception as exc:
            self._disable("get_events", exc)
            return self._local.get_events(run_id)


def _local_data_dir() -> Path:
    configured = os.getenv("WEB_LOCAL_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".tradingagents" / "web_history"


def _firebase_requested() -> bool:
    enabled = os.getenv("FIREBASE_ENABLED", "").strip().lower()
    return enabled not in {"0", "false", "no", "off", "disabled"}


def build_run_store() -> LocalJsonRunStore | FirestoreRunStore:
    """Build the best available history store.

    Firestore is selected only when a service-account path is explicitly
    supplied. Missing dependencies, invalid credentials, and initialization
    errors are non-fatal and result in the local JSON backend.
    """

    local = LocalJsonRunStore(_local_data_dir())
    if not _firebase_requested():
        return local

    credential_value = (
        os.getenv("FIREBASE_CREDENTIALS_PATH", "").strip()
        or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    )
    if not credential_value:
        return local

    credential_path = Path(credential_value).expanduser().resolve()
    if not credential_path.is_file():
        LOGGER.warning("Firebase credentials file was not found; using local JSON history.")
        return local

    try:
        # Lazy imports keep Firebase an optional dependency for core/CLI users.
        import firebase_admin
        from firebase_admin import credentials, firestore

        project_id = os.getenv("FIREBASE_PROJECT_ID", "").strip()
        database_id = os.getenv("FIREBASE_DATABASE_ID", "").strip()
        collection_name = os.getenv("FIREBASE_COLLECTION", "").strip() or RUNS_COLLECTION
        collection_name = _validate_id(collection_name, label="FIREBASE_COLLECTION")
        identity = f"{credential_path}|{project_id}|{database_id}"
        app_name = "tradingagents-web-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
        try:
            app = firebase_admin.get_app(app_name)
        except ValueError:
            options = {"projectId": project_id} if project_id else None
            app = firebase_admin.initialize_app(
                credentials.Certificate(str(credential_path)),
                options=options,
                name=app_name,
            )

        if database_id and database_id != "(default)":
            client = firestore.client(app=app, database_id=database_id)
        else:
            client = firestore.client(app=app)
        return FirestoreRunStore(client, local, collection_name)
    except Exception as exc:
        LOGGER.warning(
            "Firebase could not be initialized (%s); using local JSON history.",
            exc,
        )
        return local


__all__ = [
    "FirestoreRunStore",
    "LocalJsonRunStore",
    "RUNS_COLLECTION",
    "build_run_store",
]
