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


def _jwt(exp: int) -> str:
    import base64
    import json

    def _part(value: dict) -> str:
        raw = json.dumps(value).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{_part({'alg': 'none'})}.{_part({'exp': exp})}.signature"


def test_app_token_expiry_is_detected():
    import time

    expired = AnovaOvenApi(
        session=None,
        app_key="app-key",
        access_token=_jwt(int(time.time()) - 60),
        refresh_token="refresh-token",
    )
    valid = AnovaOvenApi(
        session=None,
        app_key="app-key",
        access_token=_jwt(int(time.time()) + 3600),
        refresh_token="refresh-token",
    )
    assert expired._token_expired() is True
    assert valid._token_expired() is False


def test_pat_has_no_expiry():
    api = _api(AUTH_METHOD_PAT)
    assert api._token_expires_at() is None
    assert api._token_expired() is False
