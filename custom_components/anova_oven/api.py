import asyncio
import json
import logging
import time
from abc import ABC
from contextlib import suppress

import aiohttp
from aiohttp.client_ws import ClientWebSocketResponse

from .const import PLATFORM, AnovaUnitOfTemperature
from .exceptions import CommandError, InvalidAuth, NoDevicesFound
from .precision_oven import (
    AnovaPrecisionOven,
    APOCommand,
    APOState,
    ProbeTarget,
    Target,
    TimerTarget,
)
from .state_parser import apply_state, parse_event_state
from .util import dict_keys_to_camel_case, to_dict

_LOGGER = logging.getLogger(__name__)


class AnovaOvenApi:
    """A class to handle communicating with the anova api to get devices"""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        app_key: str,
        access_token: str,
        refresh_token: str,
        existing_devices: list[AnovaPrecisionOven] | None = None,
        unit_of_temperature: AnovaUnitOfTemperature = AnovaUnitOfTemperature.CELSIUS,
    ) -> None:
        """Creates an anova api class"""
        self.devices = {d.cooker_id: d for d in existing_devices or []}
        self.session: aiohttp.ClientSession = session
        self.app_key: str = app_key
        self.access_token: str = access_token
        self.refresh_token: str = refresh_token
        self._should_stop = False
        self._stop_event = asyncio.Event()
        self._listeners: list[AnovaOvenUpdateListener] = []
        self._ws: ClientWebSocketResponse | None = None
        self._response_fut: asyncio.Future | None
        self.unit_of_temperature = unit_of_temperature

    def add_listener(self, listener: "AnovaOvenUpdateListener"):
        self._listeners.append(listener)

    async def run(self):
        self._should_stop = False
        self._stop_event.clear()

        attempt = 0

        while not self._should_stop:
            url = f"https://devices.anovaculinary.io/?token={self.access_token}&supportedAccessories=APO&platform={PLATFORM}"
            headers = {
                "Sec-WebSocket-Protocol": "ANOVA_V2",
                "Sec-WebSocket-Version": "13",
            }
            try:
                ws = await self.session.ws_connect(url, headers=headers)
            except aiohttp.WSServerHandshakeError as err:
                if err.status in (401, 403):
                    await self.renew_token()
                else:
                    _LOGGER.warning("Websocket handshake failed: %s", err)
                    await self._sleep_backoff(attempt)
                attempt += 1
                continue
            except aiohttp.ClientError as err:
                _LOGGER.warning("Websocket connection failed: %s", err)
                await self._sleep_backoff(attempt)
                attempt += 1
                continue

            try:
                self._ws = ws
                target: Target = None
                async for msg in ws:
                    attempt = 0
                    if self._should_stop:
                        break
                    try:
                        _LOGGER.debug("Found message %s", msg)
                        match msg.type:
                            case aiohttp.WSMsgType.TEXT:
                                data = json.loads(msg.data)
                                match data.get("command"):
                                    case "EVENT_APO_STATE":
                                        parsed = parse_event_state(data["payload"])
                                        device = self.devices.get(parsed.cooker_id)
                                        if device is None:
                                            device = AnovaPrecisionOven(
                                                cooker_id=parsed.cooker_id,
                                                type=parsed.oven_type,
                                            )
                                            self.devices[parsed.cooker_id] = device
                                            for listener in self._listeners:
                                                await listener.on_new_device(device)
                                        apply_state(device, parsed)
                                        state = parsed.state
                                        for listener in self._listeners:
                                            await listener.on_state(device, state)

                                        current_target: Target | None = None
                                        if (
                                            state.sensor.nodes.temperature_probe
                                            and state.sensor.nodes.temperature_probe.target_temperature
                                        ):
                                            current_target = ProbeTarget(
                                                temperature=state.sensor.nodes.temperature_probe.temperature,
                                                target_temperature=state.sensor.nodes.temperature_probe.target_temperature,
                                            )
                                        elif (
                                            state.sensor.nodes.timer
                                            and state.sensor.nodes.timer.initial
                                        ):
                                            current_target = TimerTarget(
                                                current=state.sensor.nodes.timer.current,
                                                initial=state.sensor.nodes.timer.initial,
                                            )
                                        if target != current_target and (
                                            (current_target and current_target.reached)
                                            or current_target is None
                                        ):
                                            for listener in self._listeners:
                                                await listener.on_target_reached(
                                                    device, target
                                                )
                                        target = current_target

                                    case "EVENT_APO_WIFI_LIST":
                                        payload = data.get("payload")
                                        new_devices: list[tuple[str, str]] = [
                                            (d["cookerId"], d["type"])
                                            for d in payload
                                            if d["cookerId"] not in self.devices
                                        ]
                                        for device in new_devices:
                                            _LOGGER.debug("Found device %s", device[0])
                                            oven = AnovaPrecisionOven(
                                                cooker_id=device[0],
                                                type=device[1],
                                            )
                                            self.devices[device[0]] = oven
                                            for listener in self._listeners:
                                                await listener.on_new_device(oven)

                                    case "RESPONSE":
                                        if self._response_fut:
                                            payload = data.get("payload")
                                            self._response_fut.set_result(payload)
                                    case _:
                                        pass
                            case aiohttp.WSMsgType.CLOSE:
                                break
                            case aiohttp.WSMsgType.ERROR:
                                break
                            case _:
                                _LOGGER.debug(f"Unknown message type: {msg}")
                        await asyncio.sleep(0)
                    except Exception as err:
                        _LOGGER.exception("Failed processing message: %s", err)
                        self._ws = None
                        raise err
            finally:
                self._ws = None
                await ws.close()

            _LOGGER.info("WS stream closed.")
            if self._should_stop:
                break
            await self._sleep_backoff(attempt)
            attempt += 1
        self._ws = None

    @staticmethod
    def _backoff_delay(attempt: int) -> float:
        """Return the reconnect delay, capped at one minute."""
        return min(2 ** min(attempt, 5), 60)

    async def _sleep_backoff(self, attempt: int) -> None:
        """Wait before reconnecting, waking early when stop is requested."""
        delay = self._backoff_delay(attempt)
        with suppress(TimeoutError):
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)

    async def stop(self):
        self._should_stop = True
        self._stop_event.set()
        if self._ws:
            await self._ws.close()

    async def renew_token(self):
        url = f"https://securetoken.googleapis.com/v1/token?key={self.app_key}"
        data = {"grant_type": "refresh_token", "refresh_token": self.refresh_token}
        try:
            async with self.session.post(url, data=data) as resp:
                res = await resp.json()
                if "error" in res:
                    raise InvalidAuth(res)
                self.access_token = res["access_token"]
                self.refresh_token = res["refresh_token"]

                _LOGGER.info("Token refreshed.")

                for listener in self._listeners:
                    await listener.on_new_token(self.access_token, self.refresh_token)
        except Exception as err:
            _LOGGER.exception(f"Failed renew token: {err}")
            raise InvalidAuth("Access Token invalid")

    async def get_devices(self) -> list[AnovaPrecisionOven]:
        timeout = time.time() + 5.5  # 5 seconds from now
        while time.time() < timeout:
            if self.devices:
                return list(self.devices.values())
            await asyncio.sleep(1)
        raise NoDevicesFound("Found no devices on the websocket")

    async def send_command(self, command: APOCommand):
        if self._ws:
            data = dict_keys_to_camel_case(to_dict(command))
            _LOGGER.info(json.dumps(data))
            self._response_fut = asyncio.Future()
            await self._ws.send_json(data)
            try:
                res = await asyncio.wait_for(self._response_fut, timeout=10)
            finally:
                self._response_fut = None
            if res and res.get("status") == "error":
                raise CommandError(res.get("error", "Unknown error"))


class AnovaOvenUpdateListener(ABC):
    async def on_state(self, device: AnovaPrecisionOven, state: APOState):
        pass

    async def on_new_device(self, device: AnovaPrecisionOven):
        pass

    async def on_new_token(self, access_token: str, refresh_token: str):
        pass

    async def on_target_reached(self, device: AnovaPrecisionOven, target: Target):
        pass
