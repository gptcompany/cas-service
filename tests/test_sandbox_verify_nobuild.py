"""Dopo il build e il down l'avvio non ricostruisce: il servizio precedente non dipende da un secondo build."""

from tests.test_sandbox_verify import _steps


def test_up_starts_the_image_already_built():
    run = next(s["run"] for s in _steps() if "docker compose up" in s.get("run", ""))
    assert "docker compose up -d --no-build" in run
