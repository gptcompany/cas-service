"""Tests for setup .env config helpers."""

from __future__ import annotations

import pytest

import cas_service.setup._config as setup_config


@pytest.fixture()
def temp_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env.test"
    monkeypatch.setattr(setup_config, "_ENV_FILE", env_file)
    return env_file


class TestSetupConfig:
    def test_env_path_returns_patched_file(self, temp_env_file):
        assert setup_config.env_path() == temp_env_file

    def test_read_config_missing_file(self, temp_env_file):
        assert setup_config.read_config() == {}

    def test_read_config_parses_and_strips_quotes(self, temp_env_file):
        temp_env_file.write_text(
            "\n".join(
                [
                    "# comment",
                    "CAS_PORT='9999'",
                    'CAS_LOG_LEVEL="DEBUG"',
                    "INVALID-LINE",
                    "lowercase_key=value",
                ]
            )
            + "\n"
        )

        assert setup_config.read_config() == {
            "CAS_PORT": "9999",
            "CAS_LOG_LEVEL": "DEBUG",
        }

    def test_write_key_creates_and_updates(self, temp_env_file):
        setup_config.write_key("CAS_PORT", "9000")
        setup_config.write_key("CAS_PORT", "9001")
        setup_config.write_key("CAS_LOG_LEVEL", "INFO")

        assert temp_env_file.read_text().splitlines() == [
            "CAS_PORT=9001",
            "CAS_LOG_LEVEL=INFO",
        ]

    def test_get_key_falls_back_to_os_environ(self, temp_env_file, monkeypatch):
        monkeypatch.setenv("CAS_PORT", "7777")
        assert setup_config.get_key("CAS_PORT") == "7777"

    def test_get_key_prefers_dotenv_even_when_empty(self, temp_env_file, monkeypatch):
        temp_env_file.write_text("CAS_WOLFRAMALPHA_APPID=\n")
        monkeypatch.setenv("CAS_WOLFRAMALPHA_APPID", "ENV-SET")
        assert setup_config.get_key("CAS_WOLFRAMALPHA_APPID") == ""

    def test_get_cas_port_uses_configured_value(self, temp_env_file):
        temp_env_file.write_text("CAS_PORT=9012\n")
        assert setup_config.get_cas_port() == 9012

    @pytest.mark.parametrize("raw_value", ["abc", "0", "65536", "-1"])
    def test_get_cas_port_invalid_values_fallback(self, temp_env_file, raw_value):
        temp_env_file.write_text(f"CAS_PORT={raw_value}\n")
        assert setup_config.get_cas_port(default=8765) == 8765

    def test_get_service_url_uses_host_and_configured_port(self, temp_env_file):
        temp_env_file.write_text("CAS_PORT=9123\n")
        assert setup_config.get_service_url() == "http://localhost:9123"
        assert setup_config.get_service_url(host="127.0.0.1") == "http://127.0.0.1:9123"
