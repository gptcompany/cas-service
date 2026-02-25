"""Process executor with isolation, timeout, and output caps.

Provides a reusable subprocess runner that any compute engine can use.
Designed so SageEngine (or any future long-running engine) plugs in
without reinventing process management.

Usage:
    executor = SubprocessExecutor(timeout=30, max_output=64*1024)
    result = executor.run(["sage", "-c", code])
    # or async:
    job_id = executor.submit(["sage", "-c", code])
    result = executor.wait(job_id)
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Lifecycle states for a compute job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class ExecResult:
    """Result from a subprocess execution."""

    returncode: int
    stdout: str
    stderr: str
    time_ms: int
    timed_out: bool = False
    truncated: bool = False


@dataclass
class Job:
    """Tracked compute job with lifecycle."""

    id: str
    command: list[str]
    status: JobStatus = JobStatus.PENDING
    result: ExecResult | None = None
    input_data: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    timeout_s: int = 30
    max_output: int = 64 * 1024


class SubprocessExecutor:
    """Execute subprocesses with isolation, timeout, and output caps.

    Sync usage:
        result = executor.run(["gap", "-q", "-b"], input_data=code, timeout_s=10)

    Async usage (submit + poll):
        job_id = executor.submit(["sage", "-c", code], timeout_s=60)
        job = executor.get_job(job_id)
        result = executor.wait(job_id)
    """

    def __init__(
        self,
        default_timeout: int = 30,
        max_output: int = 64 * 1024,
        max_jobs: int = 100,
    ) -> None:
        self.default_timeout = default_timeout
        self.max_output = max_output
        self.max_jobs = max_jobs
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def run(
        self,
        command: list[str],
        input_data: str | None = None,
        timeout_s: int | None = None,
        max_output: int | None = None,
    ) -> ExecResult:
        """Execute a subprocess synchronously. Returns ExecResult."""
        timeout = timeout_s or self.default_timeout
        cap = max_output or self.max_output
        start = time.time()

        try:
            proc = subprocess.run(
                command,
                input=input_data,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            elapsed = int((time.time() - start) * 1000)
            was_truncated = len(proc.stdout) > cap or len(proc.stderr) > cap
            return ExecResult(
                returncode=proc.returncode,
                stdout=proc.stdout[:cap],
                stderr=proc.stderr[:cap],
                time_ms=elapsed,
                truncated=was_truncated,
            )
        except subprocess.TimeoutExpired:
            elapsed = int((time.time() - start) * 1000)
            return ExecResult(
                returncode=-1,
                stdout="",
                stderr=f"Process timed out after {timeout}s",
                time_ms=elapsed,
                timed_out=True,
            )
        except FileNotFoundError:
            elapsed = int((time.time() - start) * 1000)
            return ExecResult(
                returncode=-1,
                stdout="",
                stderr=f"Command not found: {command[0]}",
                time_ms=elapsed,
            )

    def submit(
        self,
        command: list[str],
        input_data: str | None = None,
        timeout_s: int | None = None,
    ) -> str:
        """Submit a job for background execution. Returns job ID."""
        job_id = uuid.uuid4().hex[:12]
        job = Job(
            id=job_id,
            command=command,
            input_data=input_data,
            timeout_s=timeout_s or self.default_timeout,
            max_output=self.max_output,
        )

        with self._lock:
            self._evict_old_jobs()
            self._jobs[job_id] = job

        thread = threading.Thread(
            target=self._execute_job,
            args=(job,),
            daemon=True,
        )
        thread.start()
        return job_id

    def get_job(self, job_id: str) -> Job | None:
        """Get job by ID."""
        with self._lock:
            return self._jobs.get(job_id)

    def wait(self, job_id: str, poll_interval: float = 0.1) -> ExecResult | None:
        """Block until a job completes. Returns ExecResult or None if not found."""
        while True:
            job = self.get_job(job_id)
            if job is None:
                return None
            if job.status in (
                JobStatus.COMPLETED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
                JobStatus.TIMEOUT,
            ):
                return job.result
            time.sleep(poll_interval)

    def cancel(self, job_id: str) -> bool:
        """Cancel a pending job. Returns True if cancelled."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.status == JobStatus.PENDING:
                job.status = JobStatus.CANCELLED
                return True
        return False

    def list_jobs(self) -> list[dict[str, Any]]:
        """Return summary of all tracked jobs."""
        with self._lock:
            return [
                {
                    "id": j.id,
                    "status": j.status.value,
                    "command": j.command[0] if j.command else "",
                    "created_at": j.created_at,
                    "time_ms": j.result.time_ms if j.result else None,
                }
                for j in self._jobs.values()
            ]

    def _execute_job(self, job: Job) -> None:
        """Run a job in a background thread."""
        with self._lock:
            if job.status == JobStatus.CANCELLED:
                return
            job.status = JobStatus.RUNNING
            job.started_at = time.time()

        result = self.run(
            job.command,
            input_data=job.input_data,
            timeout_s=job.timeout_s,
            max_output=job.max_output,
        )

        with self._lock:
            job.result = result
            job.completed_at = time.time()
            if result.timed_out:
                job.status = JobStatus.TIMEOUT
            elif result.returncode == 0:
                job.status = JobStatus.COMPLETED
            else:
                job.status = JobStatus.FAILED

    def _evict_old_jobs(self) -> None:
        """Remove oldest completed jobs if over max_jobs."""
        if len(self._jobs) < self.max_jobs:
            return
        completed = sorted(
            (
                j
                for j in self._jobs.values()
                if j.status
                in (
                    JobStatus.COMPLETED,
                    JobStatus.FAILED,
                    JobStatus.CANCELLED,
                    JobStatus.TIMEOUT,
                )
            ),
            key=lambda j: j.created_at,
        )
        for job in completed[: len(self._jobs) - self.max_jobs + 1]:
            del self._jobs[job.id]
