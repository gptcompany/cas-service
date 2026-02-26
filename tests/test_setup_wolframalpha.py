"""Tests for WolframAlpha setup step."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from rich.console import Console


def _console() -> Console:
    return Console(file=MagicMock(), highlight=False)


class TestWolframAlphaStep:
    def _make(self):
        from cas_service.setup._wolframalpha import WolframAlphaStep

        return WolframAlphaStep()

    # -- check ---------------------------------------------------------------

    @patch("cas_service.setup._wolframalpha.get_key", return_value="FAKE-KEY")
    def test_check_configured(self, mock_get_key):
        """check() returns True if AppID is in config."""
        step = self._make()
        assert step.check() is True

    @patch("cas_service.setup._wolframalpha.get_key", return_value=None)
    def test_check_not_configured(self, mock_get_key):
        """check() returns False if AppID is missing."""
        step = self._make()
        assert step.check() is False

    # -- install -------------------------------------------------------------

    @patch("cas_service.setup._wolframalpha.write_key")
    @patch("cas_service.setup._wolframalpha.get_key", return_value=None)
    def test_install_new_key(self, mock_get_key, mock_write_key):
        """install() prompts for key and saves it."""
        mock_q = MagicMock()
        mock_q.password.return_value.ask.return_value = "NEW-KEY"
        step = self._make()
        with patch.dict("sys.modules", {"questionary": mock_q}):
            assert step.install(_console()) is True
        mock_write_key.assert_called_once_with("CAS_WOLFRAMALPHA_APPID", "NEW-KEY")

    @patch("cas_service.setup._wolframalpha.write_key")
    @patch("cas_service.setup._wolframalpha.get_key", return_value="OLD-KEY")
    def test_install_keep_existing(self, mock_get_key, mock_write_key):
        """install() keeps existing key if user enters empty string."""
        mock_q = MagicMock()
        mock_q.password.return_value.ask.return_value = ""
        step = self._make()
        with patch.dict("sys.modules", {"questionary": mock_q}):
            assert step.install(_console()) is True
        mock_write_key.assert_not_called()

    @patch("cas_service.setup._wolframalpha.write_key")
    @patch("cas_service.setup._wolframalpha.get_key", return_value=None)
    def test_install_skip_new(self, mock_get_key, mock_write_key):
        """install() returns True even if user skips (optional engine)."""
        mock_q = MagicMock()
        mock_q.password.return_value.ask.return_value = None
        step = self._make()
        with patch.dict("sys.modules", {"questionary": mock_q}):
            assert step.install(_console()) is True
        mock_write_key.assert_not_called()

    @patch("cas_service.setup._wolframalpha.get_key", return_value="VERY-LONG-KEY-THAT-NEEDS-MASKING")
    def test_install_shows_masked_key(self, mock_get_key):
        """install() masks long existing keys in the console output."""
        mock_q = MagicMock()
        mock_q.password.return_value.ask.return_value = ""
        step = self._make()
        with patch.dict("sys.modules", {"questionary": mock_q}):
            # Should not crash
            assert step.install(_console()) is True

    @patch("cas_service.setup._wolframalpha.get_key", return_value="SHORT")
    def test_install_shows_short_masked_key(self, mock_get_key):
        """install() masks short existing keys with stars."""
        mock_q = MagicMock()
        mock_q.password.return_value.ask.return_value = ""
        step = self._make()
        with patch.dict("sys.modules", {"questionary": mock_q}):
            assert step.install(_console()) is True

    def test_install_graceful_import_error(self):
        """install() handles questionary import error gracefully."""
        step = self._make()
        with patch.dict("sys.modules", {"questionary": None}):
            assert step.install(_console()) is True

    # -- verify --------------------------------------------------------------

    def test_verify_always_true(self):
        """verify() for WolframAlpha is always True as it is optional/remote."""
        step = self._make()
        assert step.verify() is True
