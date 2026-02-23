"""Tests for runtime executor (Slice E) — subprocess isolation, jobs, timeout."""

from __future__ import annotations

import time

import pytest

from cas_service.runtime.executor import (
    ExecResult,
    Job,
    JobStatus,
    SubprocessExecutor,
)


class TestSubprocessExecutorSync:

    def test_run_echo(self):
        executor = SubprocessExecutor()
        result = executor.run(["echo", "hello"])
        assert result.returncode == 0
        assert result.stdout.strip() == "hello"
        assert result.timed_out is False
        assert result.time_ms >= 0

    def test_run_with_input(self):
        executor = SubprocessExecutor()
        result = executor.run(["cat"], input_data="test input")
        assert result.returncode == 0
        assert result.stdout.strip() == "test input"

    def test_run_nonexistent_command(self):
        executor = SubprocessExecutor()
        result = executor.run(["/nonexistent/binary"])
        assert result.returncode == -1
        assert "not found" in result.stderr.lower()

    def test_run_timeout(self):
        executor = SubprocessExecutor()
        result = executor.run(["sleep", "10"], timeout_s=1)
        assert result.timed_out is True
        assert result.returncode == -1

    def test_run_output_cap(self):
        executor = SubprocessExecutor(max_output=10)
        # Generate more than 10 chars of output
        result = executor.run(
            ["python3", "-c", "print('A' * 100)"],
        )
        assert len(result.stdout) <= 10

    def test_run_nonzero_exit(self):
        executor = SubprocessExecutor()
        result = executor.run(["python3", "-c", "raise SystemExit(42)"])
        assert result.returncode == 42

    def test_run_stderr(self):
        executor = SubprocessExecutor()
        result = executor.run(
            ["python3", "-c", "import sys; sys.stderr.write('err\\n')"],
        )
        assert "err" in result.stderr


class TestSubprocessExecutorAsync:

    def test_submit_and_wait(self):
        executor = SubprocessExecutor()
        job_id = executor.submit(["echo", "async hello"])
        result = executor.wait(job_id)
        assert result is not None
        assert result.returncode == 0
        assert "async hello" in result.stdout

    def test_submit_with_input(self):
        executor = SubprocessExecutor()
        job_id = executor.submit(["cat"], input_data="async input")
        result = executor.wait(job_id)
        assert result is not None
        assert "async input" in result.stdout

    def test_get_job(self):
        executor = SubprocessExecutor()
        job_id = executor.submit(["echo", "test"])
        executor.wait(job_id)
        job = executor.get_job(job_id)
        assert job is not None
        assert job.id == job_id
        assert job.status == JobStatus.COMPLETED

    def test_get_nonexistent_job(self):
        executor = SubprocessExecutor()
        assert executor.get_job("nonexistent") is None

    def test_wait_nonexistent_job(self):
        executor = SubprocessExecutor()
        assert executor.wait("nonexistent") is None

    def test_job_timeout(self):
        executor = SubprocessExecutor()
        job_id = executor.submit(["sleep", "10"], timeout_s=1)
        result = executor.wait(job_id)
        assert result is not None
        assert result.timed_out is True
        job = executor.get_job(job_id)
        assert job.status == JobStatus.TIMEOUT

    def test_job_failure(self):
        executor = SubprocessExecutor()
        job_id = executor.submit(
            ["python3", "-c", "raise SystemExit(1)"],
        )
        result = executor.wait(job_id)
        assert result is not None
        assert result.returncode == 1
        job = executor.get_job(job_id)
        assert job.status == JobStatus.FAILED

    def test_list_jobs(self):
        executor = SubprocessExecutor()
        job_id = executor.submit(["echo", "test"])
        executor.wait(job_id)
        jobs = executor.list_jobs()
        assert len(jobs) >= 1
        found = [j for j in jobs if j["id"] == job_id]
        assert len(found) == 1
        assert found[0]["status"] == "completed"

    def test_cancel_pending_job(self):
        """Cancel works on pending jobs (timing-dependent, best-effort)."""
        executor = SubprocessExecutor()
        # We can't easily guarantee a job stays pending, so just
        # verify the API contract
        cancelled = executor.cancel("nonexistent")
        assert cancelled is False


class TestJobEviction:

    def test_evict_old_completed_jobs(self):
        executor = SubprocessExecutor(max_jobs=3)
        ids = []
        for i in range(5):
            jid = executor.submit(["echo", str(i)])
            ids.append(jid)
            executor.wait(jid)

        # Should have at most max_jobs
        jobs = executor.list_jobs()
        assert len(jobs) <= 3


class TestJobDataclass:

    def test_job_defaults(self):
        job = Job(id="test", command=["echo"])
        assert job.status == JobStatus.PENDING
        assert job.result is None
        assert job.timeout_s == 30

    def test_exec_result_defaults(self):
        result = ExecResult(returncode=0, stdout="ok", stderr="", time_ms=10)
        assert result.timed_out is False
