"""Tests for the websocket reconnect behaviour."""

import time

from custom_components.anova_oven.api import AnovaOvenApi


def _api() -> AnovaOvenApi:
    return AnovaOvenApi(
        session=None,
        app_key="app-key",
        access_token="access-token",
        refresh_token="refresh-token",
    )


async def test_backoff_wakes_on_stop():
    api = _api()
    api._should_stop = True
    api._stop_event.set()

    started = time.monotonic()
    await api._sleep_backoff(5)
    assert time.monotonic() - started < 1


def test_backoff_is_capped():
    assert AnovaOvenApi._backoff_delay(0) == 1
    assert AnovaOvenApi._backoff_delay(3) == 8
    assert AnovaOvenApi._backoff_delay(10) == 32
    assert AnovaOvenApi._backoff_delay(100) == 32
