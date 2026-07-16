from unittest.mock import MagicMock, patch

from nanodeer.cli import api, repl


def _config():
    config = MagicMock()
    config.agents.defaults.capabilities = ["coding", "research", "office", "daily"]
    return config


def test_api_cli_capabilities_override_config(monkeypatch):
    monkeypatch.setattr(api, "_engine", None)
    monkeypatch.setattr(api, "get_config", _config)

    with patch("uvicorn.run") as run:
        api.main(["--capabilities", "research,office"])

    assert api._engine.capabilities == ("research", "office")
    run.assert_called_once()


def test_repl_cli_passes_capabilities_to_async_entry(monkeypatch):
    captured = {}

    async def fake_repl(capabilities=None):
        captured["capabilities"] = capabilities

    monkeypatch.setattr(repl, "repl", fake_repl)
    repl.main(["--capabilities", "daily"])

    assert captured == {"capabilities": "daily"}
