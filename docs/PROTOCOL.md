# Anova Precision Oven cloud protocol

Unofficial notes, recovered from the Android app (version 1.2.11) and Anova's developer
documentation. Anova can change any of this without notice.

## Bottom line

The oven has no local/LAN API exposed to third parties. Every path is cloud:

1. Firebase authentication with the Anova app's own credentials, or an Anova Personal Access
   Token (`anova-…`).
2. WebSocket to `wss://devices.anovaculinary.io`.
3. Commands are JSON envelopes; oven state arrives as periodic events.

Anova also ships an **official developer API** (developer.anovaculinary.com, announced 2025-07-29)
that uses the same WebSocket. PATs are created in the app: More → Developer section → Personal
Access Tokens (max 10, names ≤32 chars). The APK has the matching token-management commands
(`CMD_CREATE_TOKEN`, `CMD_LIST_TOKENS`, `CMD_RENAME_TOKEN`, `CMD_DELETE_TOKEN`).

## Endpoints seen in the app (decompiled JavaScript bundle)

| Purpose | Value |
|---|---|
| Device WebSocket | `wss://devices.anovaculinary.io?token=<token>&supportedAccessories=APO&platform=android` |
| WebSocket subprotocol (APO) | `ANOVA_V2` |
| Token query param the app builds | `token=<Firebase ID token>&` |
| IoT REST API | `https://iot-api-prod.anovaculinary.io` (e.g. `/ai_assistant`) |
| OTA / firmware metadata | `https://anovaculinary.io/devices-ota/?device-type=oven`, `/devices-ota-current` |
| Deep links | `oven.anovaculinary.com`, `anovaculinary.io` |
| Firestore collections | `devices`, `users`, `cooks`, `recipes`, `user-profiles`, `owners`, `favorite-oven-recipes` |

## Message envelope

App/legacy V2 shape (`IOvenCommand` schema in the bundle):

```json
{
  "command": "CMD_APO_START",
  "requestId": "<uuid>",
  "payload": {
    "id": "<cookerId>",
    "type": "CMD_APO_START",
    "payload": { }
  }
}
```

Responses: `RESPONSE` with `{status: "ok"}` for the same `requestId`; command timeout in the app is 10 s.

Events received after connect:

- `EVENT_APO_WIFI_LIST` — device inventory: `cookerId`, `name`, `pairedAt`, `type` (`oven_v1` / `oven_v2`)
- `EVENT_APO_STATE` — full oven state; cadence ~30 s idle, ~2 s while cooking
- `EVENT_APO_WIFI_ADDED` / `EVENT_APO_WIFI_REMOVED` / `EVENT_APO_WIFI_FIRMWARE_UPDATE`
- `EVENT_USER_STATE`

Legacy v1 command names still present in the bundle: `AUTH_TOKEN`, `SEND_OVEN_COMMAND`,
`OVEN_STATE`, `OVEN_COMMAND_RESPONSE`, `AUTH_TOKEN_RESPONSE`.

## Command set

App (full set, 37 APO commands): `CMD_APO_START`, `CMD_APO_STOP`, `CMD_APO_START_STAGE`,
`CMD_APO_UPDATE_COOK_STAGE(S)`, `CMD_APO_SET_TIMER`, `CMD_APO_SET_PROBE`, `CMD_APO_SET_FAN`,
`CMD_APO_SET_VENT`, `CMD_APO_SET_LAMP`, `CMD_APO_SET_HEATING_ELEMENTS`,
`CMD_APO_SET_STEAM_GENERATORS`, `CMD_APO_SET_TEMPERATURE_BULBS`, `CMD_APO_SET_TEMPERATURE_UNIT`,
`CMD_APO_SET_TIME_ZONE`, `CMD_APO_SET_METADATA`, `CMD_APO_SET_CONFIGURATION`,
`CMD_APO_SET_SUBSCRIPTION`, `CMD_APO_SET_REPORT_STATE_RATE(_DEFAULT)`, `CMD_APO_SET_BOILER_TIME`,
`CMD_APO_SET_IMAGE_ANALYSIS`, `CMD_APO_SET_LAMP_PREFERENCE`, `CMD_APO_START_DESCALE`,
`CMD_APO_ABORT_DESCALE`, `CMD_APO_OTA`, `CMD_APO_HEALTHCHECK`, `CMD_APO_GET_CONFIGURATION`,
`CMD_APO_REQUEST_DIAGNOSTIC`, `CMD_APO_REPORT_LOGS`, `CMD_APO_REGISTER_PUSH_TOKEN`,
`CMD_APO_NAME_WIFI_DEVICE`, `CMD_APO_DISCONNECT`, `CMD_APO_START/STOP_LIVE_STREAM`.

PATs are limited by Anova's docs to `CMD_APO_START`, `CMD_APO_STOP`, `CMD_APO_SET_TEMPERATURE_UNIT`.
A Firebase ID token (app-style connection) reaches the full set.

Cook payload (v1): `stages[]` with `temperatureBulbs` (dry/wet setpoints in °C and °F),
`heatingElements`, `fan.speed`, `vent.open`, `steamGenerators`, `timer.initial`,
`probe.setpoint`, `rackPosition`, `stageTransitionType`, plus `cookId`.
v2 (`type: "oven_v2"`): stages with `do` / `entry` / `exit` condition trees, `cookerId`, `cookId`,
`originSource` (`api`/`android`/`ios`/`hardware`).

Temperature limits: wet 25–100 °C, dry 25–250 °C (bottom-only 180 °C v1 / 230 °C v2),
probe 1–100 °C. Timer values in seconds; all IDs UUID v4.

## Existing clients

- `wrongdoug/ha-anova-precision-oven` — HA integration on the official PAT API: 22 telemetry entities,
  on/off, target temp, lamp; complex cooks still need the app.
- `andr83/hacs-anova-oven` — HA integration on the reverse-engineered WS API: start/stop/custom
  cooks, mode sensor with `raw_stages`, cook-target events.
- `agentcipher/anova-precision-oven-sdk` — Python SDK on the official API.
- `bogd/anova-oven-api` — protocol notes for the older v1 API (deprecated Aug 2022).

## Open questions

- Oven generation detection: the integration keys off `payload.type` (`oven_v1` /
  `oven_v2`) and builds the matching stage shape. State payload differences for v2 are
  `doorLamp` instead of `lamp`, enum `fan.speed` instead of 0–100, celsius-only
  temperature values, and `usageHours` on the heating elements and steam generators.
- The integration supports both auth methods: app credentials for the full command
  set, personal access tokens for start/stop/unit only. PAT entries omit the lamp
  switch.
- The 30-minute inactivity timeout and rate limiting mean any integration must keep the socket warm
  or reconnect on demand.
