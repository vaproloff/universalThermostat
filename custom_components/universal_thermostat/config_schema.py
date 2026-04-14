"""Platform schema."""

from typing import Any

import voluptuous as vol
from voluptuous import ALLOW_EXTRA

from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
    PLATFORM_SCHEMA as CLIMATE_PLATFORM_SCHEMA,
    HVACMode,
)
from homeassistant.components.input_boolean import DOMAIN as INPUT_BOOLEAN_DOMAIN
from homeassistant.components.input_number import DOMAIN as INPUT_NUMBER_DOMAIN
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_UNIQUE_ID,
    PRECISION_HALVES,
    PRECISION_TENTHS,
    PRECISION_WHOLE,
)
from homeassistant.core import split_entity_id
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_TIMEOUT,
    CONF_AUTO_COOL_DELTA,
    CONF_AUTO_HEAT_DELTA,
    CONF_AUTO_MODE_DISABLED,
    CONF_CLIMATE_TEMP_DELTA,
    CONF_COLD_TOLERANCE,
    CONF_COOLER,
    CONF_HEAT_COOL_DISABLED,
    CONF_HEATER,
    CONF_HOT_TOLERANCE,
    CONF_IGNORE_WINDOWS,
    CONF_INITIAL_HVAC_MODE,
    CONF_INVERTED,
    CONF_KEEP_ALIVE,
    CONF_MAX_TEMP,
    CONF_MIN_DUR,
    CONF_MIN_TEMP,
    CONF_OBJECT_ID,
    CONF_PID_KD,
    CONF_PID_KI,
    CONF_PID_KP,
    CONF_PID_MAX,
    CONF_PID_MIN,
    CONF_PID_SAMPLE_PERIOD,
    CONF_PID_SWITCH_ENTITY_ID,
    CONF_PID_SWITCH_INVERTED,
    CONF_PRECISION,
    CONF_PRESET_COOL_DELTA,
    CONF_PRESET_COOL_TARGET_TEMP,
    CONF_PRESET_HEAT_DELTA,
    CONF_PRESET_HEAT_TARGET_TEMP,
    CONF_PRESET_TARGET_TEMP,
    CONF_PRESET_TEMP_DELTA,
    CONF_PRESETS,
    CONF_PWM_SWITCH_PERIOD,
    CONF_SENSOR,
    CONF_TARGET_TEMP,
    CONF_TARGET_TEMP_HIGH,
    CONF_TARGET_TEMP_LOW,
    CONF_TEMP_STEP,
    CONF_WINDOWS,
    DEFAULT_AUTO_COOL_DELTA,
    DEFAULT_AUTO_HEAT_DELTA,
    DEFAULT_COLD_TOLERANCE,
    DEFAULT_HOT_TOLERANCE,
    DEFAULT_NAME,
    DEFAULT_PID_KD,
    DEFAULT_PID_KI,
    DEFAULT_PID_KP,
    DEFAULT_PID_MAX,
    DEFAULT_PID_MIN,
)

SUPPORTED_TARGET_DOMAINS = [
    SWITCH_DOMAIN,
    INPUT_BOOLEAN_DOMAIN,
    CLIMATE_DOMAIN,
    NUMBER_DOMAIN,
    INPUT_NUMBER_DOMAIN,
]

SUPPORTED_WINDOW_DOMAINS = [
    BINARY_SENSOR_DOMAIN,
    INPUT_BOOLEAN_DOMAIN,
    SWITCH_DOMAIN,
]

CTRL_SCHEMA_COMMON = vol.Schema(
    {
        vol.Required(CONF_ENTITY_ID): cv.entity_domain(SUPPORTED_TARGET_DOMAINS),
        vol.Optional(CONF_INVERTED, default=False): bool,
        vol.Optional(CONF_KEEP_ALIVE, default=None): vol.Any(
            None, cv.positive_time_period
        ),
        vol.Optional(CONF_IGNORE_WINDOWS, default=False): bool,
    }
)

CTRL_SCHEMA_SWITCH = CTRL_SCHEMA_COMMON.extend(
    {
        vol.Optional(CONF_MIN_DUR): cv.positive_time_period,
        vol.Optional(CONF_COLD_TOLERANCE, default=DEFAULT_COLD_TOLERANCE): cv.template,
        vol.Optional(CONF_HOT_TOLERANCE, default=DEFAULT_HOT_TOLERANCE): cv.template,
    }
)

CTRL_SCHEMA_CLIMATE_SWITCH = CTRL_SCHEMA_SWITCH.extend(
    {
        vol.Optional(CONF_CLIMATE_TEMP_DELTA, default=None): vol.Any(None, cv.template),
    }
)

CTRL_SCHEMA_PID_COMMON = CTRL_SCHEMA_COMMON.extend(
    {
        vol.Required(CONF_PID_KP, default=DEFAULT_PID_KP): cv.template,
        vol.Required(CONF_PID_KI, default=DEFAULT_PID_KI): cv.template,
        vol.Required(CONF_PID_KD, default=DEFAULT_PID_KD): cv.template,
        vol.Optional(CONF_PID_SAMPLE_PERIOD, default=None): vol.Any(
            None, cv.positive_time_period
        ),
    }
)

CTRL_SCHEMA_PWM_SWITCH = CTRL_SCHEMA_PID_COMMON.extend(
    {
        vol.Required(CONF_PWM_SWITCH_PERIOD): cv.positive_time_period,
    }
)

CTRL_SCHEMA_PID_CLIMATE = CTRL_SCHEMA_PID_COMMON.extend(
    {
        vol.Optional(CONF_PID_MIN, default=DEFAULT_PID_MIN): cv.template,
        vol.Optional(CONF_PID_MAX, default=DEFAULT_PID_MAX): cv.template,
    }
)

CTRL_SCHEMA_PID_NUMBER = CTRL_SCHEMA_PID_CLIMATE.extend(
    {
        vol.Optional(CONF_PID_SWITCH_ENTITY_ID): cv.entity_domain(
            [SWITCH_DOMAIN, INPUT_BOOLEAN_DOMAIN]
        ),
        vol.Optional(CONF_PID_SWITCH_INVERTED, default=False): vol.Coerce(bool),
    }
)


def _cv_controller_target(cfg: Any) -> Any:
    entity_id: str

    if isinstance(cfg, str):
        entity_id = cfg
        cfg = {CONF_ENTITY_ID: entity_id}

    if CONF_ENTITY_ID not in cfg:
        raise vol.Invalid(f"{CONF_ENTITY_ID} should be specified")

    entity_id = cfg[CONF_ENTITY_ID]

    domain = split_entity_id(entity_id)[0]

    if domain in [SWITCH_DOMAIN, INPUT_BOOLEAN_DOMAIN]:
        if CONF_PID_KP in cfg:
            return CTRL_SCHEMA_PWM_SWITCH(cfg)
        return CTRL_SCHEMA_SWITCH(cfg)

    if domain == CLIMATE_DOMAIN:
        if CONF_PID_KP in cfg:
            return CTRL_SCHEMA_PID_CLIMATE(cfg)
        return CTRL_SCHEMA_CLIMATE_SWITCH(cfg)

    if domain in [INPUT_NUMBER_DOMAIN, NUMBER_DOMAIN]:
        return CTRL_SCHEMA_PID_NUMBER(cfg)

    raise vol.Invalid(f"{entity_id}: Unsupported domain: {domain}")


KEY_SCHEMA = vol.Schema(
    {
        vol.Required(
            vol.Any(CONF_HEATER, CONF_COOLER),
            msg=f"Must specify at least one: '{CONF_HEATER}' or '{CONF_COOLER}'",
        ): object
    },
    extra=ALLOW_EXTRA,
)

PRESET_SCHEMA_TEMP_DELTA = vol.Schema(
    {
        vol.Required(CONF_PRESET_TEMP_DELTA): cv.template,
    }
)

PRESET_SCHEMA_HEAT_COOL_DELTA = vol.Schema(
    {
        vol.Required(CONF_PRESET_HEAT_DELTA): cv.template,
        vol.Required(CONF_PRESET_COOL_DELTA): cv.template,
    }
)

PRESET_SCHEMA_TARGET_TEMP = vol.All(
    vol.Schema(
        {
            vol.Required(
                vol.Any(
                    CONF_PRESET_TARGET_TEMP,
                    CONF_PRESET_HEAT_TARGET_TEMP,
                    CONF_PRESET_COOL_TARGET_TEMP,
                )
            ): object,
        },
        extra=ALLOW_EXTRA,
    ),
    vol.Schema(
        {
            vol.Optional(CONF_PRESET_TARGET_TEMP): cv.template,
            vol.Optional(CONF_PRESET_HEAT_TARGET_TEMP): cv.template,
            vol.Optional(CONF_PRESET_COOL_TARGET_TEMP): cv.template,
        },
    ),
)

WINDOWS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_domain(SUPPORTED_WINDOW_DOMAINS),
        vol.Optional(ATTR_TIMEOUT): vol.Any(cv.positive_time_period, cv.template),
        vol.Optional(CONF_INVERTED, default=False): bool,
    }
)

PRESET_SCHEMA = vol.Schema(
    {
        cv.string: vol.Any(
            PRESET_SCHEMA_TEMP_DELTA,
            PRESET_SCHEMA_HEAT_COOL_DELTA,
            PRESET_SCHEMA_TARGET_TEMP,
        )
    }
)

DATA_SCHEMA = CLIMATE_PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_UNIQUE_ID): cv.string,
        vol.Optional(CONF_OBJECT_ID): cv.string,
        vol.Optional(CONF_HEATER): vol.Any(
            _cv_controller_target, [_cv_controller_target]
        ),
        vol.Optional(CONF_COOLER): vol.Any(
            _cv_controller_target, [_cv_controller_target]
        ),
        vol.Optional(CONF_WINDOWS): vol.Any(
            cv.entity_domain(SUPPORTED_WINDOW_DOMAINS),
            [vol.Any(cv.entity_domain(SUPPORTED_WINDOW_DOMAINS), WINDOWS_SCHEMA)],
        ),
        vol.Optional(CONF_PRESETS): PRESET_SCHEMA,
        vol.Required(CONF_SENSOR): cv.entity_id,
        vol.Optional(CONF_MIN_TEMP): vol.Coerce(float),
        vol.Optional(CONF_MAX_TEMP): vol.Coerce(float),
        vol.Optional(CONF_TARGET_TEMP): vol.Coerce(float),
        vol.Optional(CONF_TARGET_TEMP_HIGH): vol.Coerce(float),
        vol.Optional(CONF_TARGET_TEMP_LOW): vol.Coerce(float),
        vol.Optional(
            CONF_AUTO_COOL_DELTA, default=DEFAULT_AUTO_COOL_DELTA
        ): cv.template,
        vol.Optional(
            CONF_AUTO_HEAT_DELTA, default=DEFAULT_AUTO_HEAT_DELTA
        ): cv.template,
        vol.Optional(CONF_HEAT_COOL_DISABLED, default=False): vol.Coerce(bool),
        vol.Optional(CONF_AUTO_MODE_DISABLED, default=False): vol.Coerce(bool),
        vol.Optional(CONF_INITIAL_HVAC_MODE): vol.In(
            [HVACMode.HEAT_COOL, HVACMode.COOL, HVACMode.HEAT, HVACMode.OFF]
        ),
        vol.Optional(CONF_PRECISION): vol.In(
            [PRECISION_TENTHS, PRECISION_HALVES, PRECISION_WHOLE]
        ),
        vol.Optional(CONF_TEMP_STEP): vol.In(
            [PRECISION_TENTHS, PRECISION_HALVES, PRECISION_WHOLE]
        ),
    }
)

PLATFORM_SCHEMA = vol.All(KEY_SCHEMA, DATA_SCHEMA)
