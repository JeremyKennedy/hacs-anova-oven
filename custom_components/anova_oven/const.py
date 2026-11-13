"""Constants for the Anova Precision Oven integration."""

from enum import IntFlag, StrEnum

DOMAIN = "anova_oven"

PLATFORM = "android"
CONF_APP_KEY = "app_key"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_AUTH_METHOD = "auth_method"

AUTH_METHOD_APP = "app"
AUTH_METHOD_PAT = "pat"

# Anova limits personal access tokens to this command set.
PAT_ALLOWED_COMMANDS = frozenset(
    {
        "CMD_APO_START",
        "CMD_APO_STOP",
        "CMD_APO_SET_TEMPERATURE_UNIT",
    }
)

EVENT_COOK_TARGET_REACHED = f"{DOMAIN}.cook_target_reached"


class AnovaUnitOfTemperature(StrEnum):
    """Temperature units."""

    CELSIUS = "°C"
    FAHRENHEIT = "°F"


class TemperatureEntityFeature(IntFlag):
    """Supported features of the climate entity."""

    CELSIUS = 1
    FAHRENHEIT = 2
