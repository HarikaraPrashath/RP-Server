from __future__ import annotations

import concurrent.futures
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable


class JobQueue:
    def __init__(self) -> None:
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="rp-worker")
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}

    def submit(self, fn: Callable[..., dict[str, Any]], *args, **kwargs) -> str:
        job_id = uuid.uuid4().hex
        with self._lock:
            self._jobs[job_id] = {
                "status": "queued",
                "createdAt": datetime.now(timezone.utc).isoformat(),
                "result": None,
                "error": None,
            }

        def _runner() -> dict[str, Any]:
            with self._lock:
                self._jobs[job_id]["status"] = "running"
            try:
                result = fn(*args, **kwargs)
                with self._lock:
                    self._jobs[job_id]["status"] = "succeeded"
                    self._jobs[job_id]["result"] = result
                return result
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    self._jobs[job_id]["status"] = "failed"
                    self._jobs[job_id]["error"] = str(exc)
                raise

        self._executor.submit(_runner)
        return job_id

    def status(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            data = self._jobs.get(job_id)
            if data is None:
                return None
            return dict(data)


queue = JobQueue()
