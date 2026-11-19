"""Regressioni M1/M2 e porta unica per il workflow sandbox-validate (F-775, cas-service#24)."""

import importlib.util
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "sandbox-validate.yml"
SCRIPT = REPO_ROOT / "scripts" / "sandbox_verify.py"

PORT = 8769
INODE = 4242


def _load():
    spec = importlib.util.spec_from_file_location("sandbox_verify", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ss(addr: str, inode: int = INODE) -> str:
    return f"LISTEN 0 5 {addr}:{PORT} 0.0.0.0:* uid:1000 ino:{inode} sk:1 <->\n"


def _steps() -> list[dict]:
    wf = yaml.safe_load(WORKFLOW.read_text())
    return wf["jobs"]["sandbox-validate"]["steps"]


def _index(steps: list[dict], needle: str) -> int:
    for i, step in enumerate(steps):
        if needle in step.get("run", ""):
            return i
    raise AssertionError(f"nessuno step esegue {needle!r}")


def _wait(sv, listing, *, inodes=None, health=lambda: True, timeout_s=180, step=3):
    clock = iter(range(0, 100000, step))
    return sv.wait_ready(
        PORT,
        list_listeners=listing,
        container_inodes=lambda: {INODE} if inodes is None else inodes,
        health=health,
        sleep=lambda s: None,
        now=lambda: next(clock),
        timeout_s=timeout_s,
    )


# --- M1: il listener si verifica dentro l'attesa, dopo la disponibilita' ---


def test_listener_absent_while_cas_initialises_is_pending_not_failure():
    sv = _load()
    assert sv.listener_state([], {INODE}, PORT) == "pending"


def test_wait_ready_retries_until_listener_and_health_appear():
    sv = _load()
    outputs = iter(["", "", _ss("127.0.0.1")])
    assert _wait(sv, lambda: next(outputs)) == "ready"


def test_wait_ready_times_out_when_listener_never_appears():
    sv = _load()
    with pytest.raises(sv.SandboxError, match="timeout"):
        _wait(sv, lambda: "", step=60)


def test_wildcard_bind_is_rejected():
    sv = _load()
    for addr in ("0.0.0.0", "*", "[::]"):
        listeners = sv.parse_ss(_ss(addr))
        with pytest.raises(sv.SandboxError, match="loopback"):
            sv.listener_state(listeners, {INODE}, PORT)


def test_workflow_probes_listener_only_inside_the_readiness_wait():
    steps = _steps()
    allowed = {_index(steps, "sandbox_verify.py wait"), _index(steps, "sandbox_verify.py preflight")}
    for i, step in enumerate(steps):
        if i not in allowed:
            assert not re.search(r"\bss\b", step.get("run", "")), step.get("name")
    assert _index(steps, "sandbox_verify.py wait") > _index(steps, "docker compose up")


# --- M2: listener e risposta legati al container corrente ---


def test_listener_owned_by_another_process_is_rejected():
    sv = _load()
    listeners = sv.parse_ss(_ss("127.0.0.1", inode=999))
    with pytest.raises(sv.SandboxError, match="non appartiene"):
        sv.listener_state(listeners, {INODE}, PORT)


def test_previous_cas_answering_health_never_certifies_new_deploy():
    sv = _load()
    with pytest.raises(sv.SandboxError, match="non appartiene"):
        _wait(sv, lambda: _ss("127.0.0.1", inode=999))


def test_health_is_checked_only_after_ownership_is_proven():
    sv = _load()
    calls = []
    _wait(sv, lambda: _ss("127.0.0.1"), health=lambda: calls.append("health") or True)
    assert calls == ["health"]


def test_preflight_fails_when_port_already_occupied():
    sv = _load()
    with pytest.raises(sv.SandboxError, match="gia' occupata"):
        sv.check_preflight(sv.parse_ss(_ss("127.0.0.1", inode=999)), PORT)


def test_preflight_passes_when_port_is_free():
    sv = _load()
    sv.check_preflight(sv.parse_ss(""), PORT)


def test_workflow_runs_preflight_before_compose_up():
    steps = _steps()
    assert _index(steps, "sandbox_verify.py preflight") < _index(steps, "docker compose up")


# --- porta da un'unica fonte ---


def test_workflow_uses_single_port_variable():
    text = WORKFLOW.read_text()
    assert re.search(r"\bCAS_PORT\b", text) is None
    assert "CAS_DOCKER_PORT" in text


def test_workflow_resolves_port_once_for_compose_and_checks():
    steps = _steps()
    resolve = next(i for i, s in enumerate(steps) if "GITHUB_ENV" in s.get("run", ""))
    assert "CAS_DOCKER_PORT" in steps[resolve]["run"]
    assert resolve < _index(steps, "sandbox_verify.py preflight")


def test_health_url_is_loopback_on_the_same_port():
    sv = _load()
    assert sv.health_url(PORT) == f"http://127.0.0.1:{PORT}/health"
