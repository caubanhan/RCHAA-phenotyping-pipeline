from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Optional, Tuple


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _safe_load_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _atomic_write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.write("\n")
    os.replace(temp_path, path)


def _acquire_lock(lock_path: str, timeout_seconds: float = 30.0) -> None:
    deadline = time.time() + timeout_seconds
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(str(os.getpid()))
            return
        except FileExistsError:
            if time.time() >= deadline:
                raise TimeoutError(f"Timed out waiting for tracker lock: {lock_path}")
            time.sleep(0.05)


def _release_lock(lock_path: str) -> None:
    try:
        os.remove(lock_path)
    except FileNotFoundError:
        pass


def _experiment_root(project_dir: str) -> str:
    return os.path.join(os.path.abspath(project_dir), "analysis")


def _state_path(project_dir: str) -> str:
    return os.path.join(_experiment_root(project_dir), ".experiment_tracker_state.json")


def _resolve_run_path(project_dir: str, run_id: str) -> str:
    return os.path.join(_experiment_root(project_dir), run_id)


def _load_state(project_dir: str) -> Dict[str, Any]:
    state = _safe_load_json(_state_path(project_dir), {"next_index": 1})
    if not isinstance(state, dict):
        return {"next_index": 1}
    if not isinstance(state.get("next_index"), int) or state["next_index"] < 1:
        state["next_index"] = 1
    return state


def _store_state(project_dir: str, state: Dict[str, Any]) -> None:
    _atomic_write_json(_state_path(project_dir), state)


def _coerce_jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(key): _coerce_jsonable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_coerce_jsonable(item) for item in value]
        return str(value)


def start_run(config: Dict[str, Any]) -> Tuple[str, str]:
    project_dir = os.path.abspath(str(config.get("project_dir", os.getcwd())))
    experiment_root = _experiment_root(project_dir)
    os.makedirs(experiment_root, exist_ok=True)

    lock_path = os.path.join(experiment_root, ".experiment_tracker.lock")
    _acquire_lock(lock_path)
    try:
        state = _load_state(project_dir)
        run_index = state["next_index"]

        while True:
            run_id = f"exp_{run_index:03d}"
            run_path = _resolve_run_path(project_dir, run_id)
            if not os.path.exists(run_path):
                break
            run_index += 1

        state["next_index"] = run_index + 1
        _store_state(project_dir, state)
    finally:
        _release_lock(lock_path)

    os.makedirs(run_path, exist_ok=False)

    config_snapshot = _coerce_jsonable(copy.deepcopy(config))
    config_path = os.path.join(run_path, "config.json")
    metadata_path = os.path.join(run_path, "metadata.json")
    metrics_path = os.path.join(run_path, "metrics.json")
    logs_path = os.path.join(run_path, "logs.txt")

    config_hash = hashlib.sha256(_canonical_json(config_snapshot).encode("utf-8")).hexdigest()
    start_time = _now_iso()

    _atomic_write_json(config_path, config_snapshot)
    with open(logs_path, "a", encoding="utf-8"):
        pass
    _atomic_write_json(metrics_path, {})
    _atomic_write_json(
        metadata_path,
        {
            "run_id": run_id,
            "project_dir": project_dir,
            "requested_analysis_id": config_snapshot.get("analysis_id"),
            "timestamp": start_time,
            "start_time": start_time,
            "end_time": None,
            "duration_seconds": None,
            "status": "running",
            "config_hash": config_hash,
        },
    )

    return run_id, run_path


def log_metrics(run_id: str, metrics: Dict[str, Any], project_dir: Optional[str] = None, run_path: Optional[str] = None) -> None:
    if run_path is None:
        if project_dir is None:
            raise ValueError("project_dir or run_path is required to log metrics")
        run_path = _resolve_run_path(project_dir, run_id)

    metrics_path = os.path.join(run_path, "metrics.json")
    existing_metrics = _safe_load_json(metrics_path, {})
    if not isinstance(existing_metrics, dict):
        existing_metrics = {}

    existing_metrics.update(_coerce_jsonable(metrics))
    _atomic_write_json(metrics_path, existing_metrics)


def end_run(
    run_id: str,
    status: str,
    project_dir: Optional[str] = None,
    run_path: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    if run_path is None:
        if project_dir is None:
            raise ValueError("project_dir or run_path is required to end a run")
        run_path = _resolve_run_path(project_dir, run_id)

    metadata_path = os.path.join(run_path, "metadata.json")
    metadata = _safe_load_json(metadata_path, {})
    if not isinstance(metadata, dict):
        metadata = {}

    end_time = _now_iso()
    start_time = metadata.get("start_time") or metadata.get("timestamp")
    duration_seconds = None
    if isinstance(start_time, str):
        try:
            started = datetime.fromisoformat(start_time)
            finished = datetime.fromisoformat(end_time)
            duration_seconds = max(0.0, (finished - started).total_seconds())
        except ValueError:
            duration_seconds = None

    metadata.update(
        {
            "run_id": run_id,
            "status": status,
            "end_time": end_time,
            "duration_seconds": duration_seconds,
        }
    )
    if error:
        metadata["error"] = str(error)

    _atomic_write_json(metadata_path, metadata)


class _Tee:
    def __init__(self, *streams: Any) -> None:
        self._streams = streams

    def write(self, data: str) -> None:
        for stream in self._streams:
            stream.write(data)
            stream.flush()

    def flush(self) -> None:
        for stream in self._streams:
            stream.flush()


@contextmanager
def capture_run_logs(log_path: str) -> Iterator[None]:
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    with open(log_path, "a", encoding="utf-8") as log_handle:
        sys.stdout = _Tee(original_stdout, log_handle)
        sys.stderr = _Tee(original_stderr, log_handle)
        try:
            yield
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr
