#!/usr/bin/env python3
"""Verifica del listener CAS nel workflow sandbox-validate (F-775).

`preflight`: la porta deve essere libera prima dell'avvio, altrimenti un CAS
precedente potrebbe rispondere al posto di quello nuovo.
`wait`: attende che il socket sia aperto da un processo del container corrente,
solo su 127.0.0.1, e solo dopo interroga /health.
"""

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from typing import Callable, NamedTuple

LOOPBACK = "127.0.0.1"
# Esegue nel container: i socket tenuti dai processi del suo PID namespace.
_INODE_SNIPPET = (
    "import glob,os\n"
    "for f in glob.glob('/proc/[0-9]*/fd/*'):\n"
    "    try: t=os.readlink(f)\n"
    "    except OSError: continue\n"
    "    if t.startswith('socket:['): print(t[8:-1])\n"
)
# Limite di risorsa: tetto all'attesa dell'inizializzazione dei motori (Sage/MATLAB).
DEFAULT_TIMEOUT_S = 180
POLL_S = 3


class SandboxError(Exception):
    pass


class Listener(NamedTuple):
    host: str
    port: int
    inode: int | None


def log(msg: str) -> None:
    print(f"[sandbox-verify] {msg}", flush=True)


def parse_ss(text: str) -> list[Listener]:
    """Righe di `ss -ltnHe`: il campo 3 e' l'indirizzo locale, `ino:N` il socket."""
    out = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 4:
            continue
        host, _, port = fields[3].rpartition(":")
        ino = re.search(r"\bino:(\d+)", line)
        out.append(Listener(host, int(port), int(ino.group(1)) if ino else None))
    return out


def check_preflight(listeners: list[Listener], port: int) -> None:
    if listeners:
        raise SandboxError(f"porta {port} gia' occupata prima dell'avvio: {listeners}")


def listener_state(listeners: list[Listener], inodes: set[int], port: int) -> str:
    if not listeners:
        return "pending"
    for lst in listeners:
        if lst.host != LOOPBACK:
            raise SandboxError(f"listener non solo su loopback: {lst.host}:{port}")
        if lst.inode not in inodes:
            raise SandboxError(f"il listener su {port} non appartiene al container corrente (ino {lst.inode})")
    return "owned"


def port_from_compose(config_json: str) -> int:
    """Porta effettiva risolta da Compose: unica fonte per listener e salute."""
    return int(json.loads(config_json)["services"]["cas-service"]["environment"]["CAS_PORT"])


def health_url(port: int) -> str:
    return f"http://{LOOPBACK}:{port}/health"


def wait_ready(
    port: int,
    *,
    list_listeners: Callable[[], str],
    container_inodes: Callable[[], set[int]],
    health: Callable[[], bool],
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> str:
    start = now()
    while True:
        state = listener_state(parse_ss(list_listeners()), container_inodes(), port)
        if state == "owned":
            if health():
                log(f"ready: listener del container su {LOOPBACK}:{port} e /health ok")
                return "ready"
            log("listener del container aperto, /health non ancora ok")
        else:
            log("listener non ancora aperto (inizializzazione in corso)")
        if now() - start >= timeout_s:
            raise SandboxError(f"timeout dopo {timeout_s}s in attesa di listener e /health su {port}")
        sleep(POLL_S)


def _ss(port: int) -> str:
    res = subprocess.run(["ss", "-ltnHe", f"sport = :{port}"], capture_output=True, text=True, check=True)
    return res.stdout


def _container_inodes(container: str) -> set[int]:
    res = subprocess.run(
        ["docker", "exec", container, "/app/.venv/bin/python", "-c", _INODE_SNIPPET],
        capture_output=True,
        text=True,
        check=True,
    )
    return {int(x) for x in res.stdout.split()}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def direct_opener() -> urllib.request.OpenerDirector:
    """Niente proxy ne' redirect: conta solo la risposta del socket verificato."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)


def _health(port: int) -> bool:
    try:
        with direct_opener().open(health_url(port), timeout=5) as resp:
            return resp.status == 200
    except OSError as exc:
        log(f"health: {exc}")
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("port")
    for name in ("preflight", "wait"):
        p = sub.add_parser(name)
        p.add_argument("--port", type=int, required=True)
        if name == "wait":
            p.add_argument("--container", required=True)
            p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "port":
            cfg = subprocess.run(
                ["docker", "compose", "config", "--format", "json"], capture_output=True, text=True, check=True
            )
            print(port_from_compose(cfg.stdout))
        elif args.cmd == "preflight":
            check_preflight(parse_ss(_ss(args.port)), args.port)
            log(f"porta {args.port} libera")
        else:
            wait_ready(
                args.port,
                list_listeners=lambda: _ss(args.port),
                container_inodes=lambda: _container_inodes(args.container),
                health=lambda: _health(args.port),
                timeout_s=args.timeout,
            )
    except (SandboxError, subprocess.CalledProcessError) as exc:
        log(f"FAIL: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
