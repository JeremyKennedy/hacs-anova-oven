"""Tests for auth-method-specific API behaviour."""

from unittest.mock import AsyncMock, MagicMock

from custom_components.anova_oven.api import AnovaOvenApi
from custom_components.anova_oven.const import AUTH_METHOD_APP, AUTH_METHOD_PAT
from custom_components.anova_oven.precision_oven import APOCommand


def _api(auth_method: str) -> AnovaOvenApi:
    return AnovaOvenApi(
        session=None,
        app_key="app-key",
        access_token="anova-token" if auth_method == AUTH_METHOD_PAT else "id-token",
        refresh_token="refresh-token",
        auth_method=auth_method,
    )


def test_app_websocket_url_keeps_platform():
    url = _api(AUTH_METHOD_APP)._websocket_url()
    assert url == (
        "https://devices.anovaculinary.io/"
        "?token=id-token&supportedAccessories=APO&platform=android"
    )


def test_pat_websocket_url_omits_platform():
    url = _api(AUTH_METHOD_PAT)._websocket_url()
    assert url == (
        "https://devices.anovaculinary.io/?token=anova-token&supportedAccessories=APO"
    )


def _command(name: str) -> APOCommand:
    return APOCommand(
        command=name,
        request_id="request-id",
        payload=APOCommand.Payload(payload={"on": True}, type=name, id="01234"),
    )


async def test_pat_skips_commands_outside_its_allowlist():
    api = _api(AUTH_METHOD_PAT)
    api._ws = MagicMock()
    api._ws.send_json = AsyncMock()

    await api.send_command(_command("CMD_APO_SET_LAMP"))

    api._ws.send_json.assert_not_called()


async def test_pat_sends_allowed_commands():
    api = _api(AUTH_METHOD_PAT)
    api._ws = MagicMock()

    async def _resolve(_data):
        api._response_fut.set_result({"status": "ok"})

    api._ws.send_json = AsyncMock(side_effect=_resolve)

    await api.send_command(_command("CMD_APO_STOP"))

    api._ws.send_json.assert_called_once()
