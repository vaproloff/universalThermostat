"""Adds support for universal thermostat units."""

import asyncio
from collections.abc import Mapping
import logging
import math
from typing import Any

import voluptuous as vol
from voluptuous import ALLOW_EXTRA

from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.climate import (
    ATTR_PRESET_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    DOMAIN as CLIMATE_DOMAIN,
    ENTITY_ID_FORMAT,
    PLATFORM_SCHEMA as CLIMATE_PLATFORM_SCHEMA,
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.input_boolean import DOMAIN as INPUT_BOOLEAN_DOMAIN
from homeassistant.components.input_number import DOMAIN as INPUT_NUMBER_DOMAIN
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_UNIQUE_ID,
    EVENT_HOMEASSISTANT_START,
    PRECISION_HALVES,
    PRECISION_TENTHS,
    PRECISION_WHOLE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import (
    Context,
    CoreState,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    split_entity_id,
)
from homeassistant.exceptions import TemplateError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.reload import async_setup_reload_service
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.template import RenderInfo, Template
from homeassistant.helpers.typing import ConfigType

from . import DOMAIN, PLATFORMS
from .const import (
    ATTR_LAST_ACTIVE_HVAC_MODE,
    ATTR_LAST_ASYNC_CONTROL_HVAC_MODE,
    ATTR_PRESET_NONE_SAVED_STATE,
    ATTR_TIMEOUT,
    CONF_AUTO_COOL_DELTA,
    CONF_AUTO_HEAT_DELTA,
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
    DEFAULT_PRESET_AUTO_TEMP_DELTA,
    PRESET_NONE_HVAC_MODE,
    PRESET_NONE_TARGET_TEMP,
    PRESET_NONE_TARGET_TEMP_HIGH,
    PRESET_NONE_TARGET_TEMP_LOW,
    REASON_CONTROLLER_TEMPLATE_ENTITY_CHANGED,
    REASON_PRESET_CHANGED,
    REASON_TEMPLATE_ENTITY_CHANGED,
    REASON_THERMOSTAT_FIRST_RUN,
    REASON_THERMOSTAT_HVAC_MODE_CHANGED,
    REASON_THERMOSTAT_SENSOR_CHANGED,
    REASON_THERMOSTAT_TARGET_TEMP_CHANGED,
    REASON_WINDOW_ENTITY_CHANGED,
)
from .controllers import (
    AbstractController,
    ClimatePidController,
    ClimateSwitchController,
    NumberPidController,
    PresetController,
    PwmSwitchPidController,
    SwitchController,
    WindowController,
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

_LOGGER = logging.getLogger(__name__)


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

    if domain in [CLIMATE_DOMAIN]:
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


def _create_controllers(
    prefix: str,
    mode: str,
    conf_list: Any,
) -> list[AbstractController]:
    if conf_list is None:
        return []
    if not isinstance(conf_list, list):
        conf_list = [conf_list]

    controllers: list[AbstractController] = []

    for controller_number, conf in enumerate(conf_list, 1):
        name = f"{prefix}_{controller_number}"

        entity_id = conf[CONF_ENTITY_ID]
        inverted = conf[CONF_INVERTED]
        keep_alive = conf[CONF_KEEP_ALIVE]
        ignore_windows = conf[CONF_IGNORE_WINDOWS]

        domain = split_entity_id(entity_id)[0]

        controller = None

        if domain in [SWITCH_DOMAIN, INPUT_BOOLEAN_DOMAIN]:
            if CONF_PID_KP in conf:
                controller = PwmSwitchPidController(
                    name,
                    mode,
                    entity_id,
                    conf[CONF_PID_KP],
                    conf[CONF_PID_KI],
                    conf[CONF_PID_KD],
                    conf[CONF_PID_SAMPLE_PERIOD],
                    inverted,
                    keep_alive,
                    ignore_windows,
                    conf[CONF_PWM_SWITCH_PERIOD],
                )
            else:
                min_duration = conf.get(CONF_MIN_DUR, None)
                cold_tolerance = conf[CONF_COLD_TOLERANCE]
                hot_tolerance = conf[CONF_HOT_TOLERANCE]

                controller = SwitchController(
                    name,
                    mode,
                    entity_id,
                    cold_tolerance,
                    hot_tolerance,
                    inverted,
                    keep_alive,
                    ignore_windows,
                    min_duration,
                )

        elif domain in [CLIMATE_DOMAIN]:
            if CONF_PID_KP in conf:
                controller = ClimatePidController(
                    name,
                    mode,
                    entity_id,
                    conf[CONF_PID_KP],
                    conf[CONF_PID_KI],
                    conf[CONF_PID_KD],
                    conf[CONF_PID_SAMPLE_PERIOD],
                    inverted,
                    keep_alive,
                    ignore_windows,
                    conf[CONF_PID_MIN],
                    conf[CONF_PID_MAX],
                )
            else:
                min_duration = conf.get(CONF_MIN_DUR, None)
                cold_tolerance = conf[CONF_COLD_TOLERANCE]
                hot_tolerance = conf[CONF_HOT_TOLERANCE]
                temp_delta = conf[CONF_CLIMATE_TEMP_DELTA]

                controller = ClimateSwitchController(
                    name,
                    mode,
                    entity_id,
                    cold_tolerance,
                    hot_tolerance,
                    temp_delta,
                    inverted,
                    keep_alive,
                    ignore_windows,
                    min_duration,
                )

        elif domain in [INPUT_NUMBER_DOMAIN, NUMBER_DOMAIN]:
            controller = NumberPidController(
                name,
                mode,
                entity_id,
                conf[CONF_PID_KP],
                conf[CONF_PID_KI],
                conf[CONF_PID_KD],
                conf[CONF_PID_SAMPLE_PERIOD],
                inverted,
                keep_alive,
                ignore_windows,
                conf[CONF_PID_MIN],
                conf[CONF_PID_MAX],
                conf[CONF_PID_SWITCH_ENTITY_ID],
                conf[CONF_PID_SWITCH_INVERTED],
            )

        else:
            _LOGGER.error(
                "Unsupported %s domain: '%s' for entity %s", name, domain, entity_id
            )

        if controller:
            controllers.append(controller)

    return controllers


async def async_setup_platform(
    hass: HomeAssistant, config: ConfigType, async_add_entities, discovery_info=None
):
    """Set up the universal thermostat platform."""

    # prevent unused variable warn
    _ = discovery_info

    await async_setup_reload_service(hass, DOMAIN, PLATFORMS)

    name = config.get(CONF_NAME)
    sensor_entity_id = config.get(CONF_SENSOR)
    min_temp = config.get(CONF_MIN_TEMP)
    max_temp = config.get(CONF_MAX_TEMP)
    target_temp = config.get(CONF_TARGET_TEMP)
    target_temp_high = config.get(CONF_TARGET_TEMP_HIGH)
    target_temp_low = config.get(CONF_TARGET_TEMP_LOW)
    heat_cool_disabled = config.get(CONF_HEAT_COOL_DISABLED)
    initial_hvac_mode = config.get(CONF_INITIAL_HVAC_MODE)
    precision = config.get(CONF_PRECISION)
    target_temp_step = config.get(CONF_TEMP_STEP)
    unit = hass.config.units.temperature_unit
    unique_id = config.get(CONF_UNIQUE_ID)
    object_id = config.get(CONF_OBJECT_ID)

    heater_config = config.get(CONF_HEATER)
    cooler_config = config.get(CONF_COOLER)

    controllers = []

    if cooler_config:
        controllers.extend(_create_controllers("cooler", HVACMode.COOL, cooler_config))

    if heater_config:
        controllers.extend(_create_controllers("heater", HVACMode.HEAT, heater_config))

    auto_cool_delta, auto_heat_delta = None, None
    if heater_config and cooler_config:
        auto_cool_delta = config.get(CONF_AUTO_COOL_DELTA)
        auto_heat_delta = config.get(CONF_AUTO_HEAT_DELTA)

    windows = config.get(CONF_WINDOWS)
    window_contoller = WindowController(hass, windows) if windows else None

    presets = config.get(CONF_PRESETS)
    preset_contoller = PresetController(presets) if presets else None

    async_add_entities(
        [
            UniversalThermostat(
                hass,
                name,
                controllers,
                sensor_entity_id,
                min_temp,
                max_temp,
                target_temp,
                target_temp_high,
                target_temp_low,
                auto_cool_delta,
                auto_heat_delta,
                heat_cool_disabled,
                initial_hvac_mode,
                precision,
                target_temp_step,
                unit,
                unique_id,
                object_id,
                window_contoller,
                preset_contoller,
            )
        ]
    )


class UniversalThermostat(ClimateEntity, RestoreEntity):
    """Representation of a Universal Thermostat device."""

    def __init__(
        self,
        hass: HomeAssistant | None,
        name: str,
        controllers: list[AbstractController],
        sensor_entity_id: str,
        min_temp: float | None,
        max_temp: float | None,
        target_temp: float | None,
        target_temp_high: float | None,
        target_temp_low: float | None,
        auto_cool_delta: Template | None,
        auto_heat_delta: Template | None,
        heat_cool_disabled: bool,
        initial_hvac_mode: HVACMode | None,
        precision: float | None,
        target_temp_step: float | None,
        unit: UnitOfTemperature,
        unique_id: str | None,
        object_id: str | None,
        window_contoller: WindowController | None,
        preset_controller: PresetController | None,
    ) -> None:
        """Initialize the thermostat."""
        self._name = name
        self._controllers = controllers
        self.sensor_entity_id = sensor_entity_id
        self._hvac_mode = initial_hvac_mode
        self._last_async_control_hvac_mode = None
        self._last_active_hvac_mode = None
        self._saved_target_temp = target_temp
        self._temp_precision = precision
        self._target_temp_step = target_temp_step
        self._hvac_list = [HVACMode.OFF]
        self._cur_temp = None
        self._temp_lock = asyncio.Lock()
        self._min_temp = min_temp
        self._max_temp = max_temp
        self._target_temp = target_temp
        self._target_temp_high = target_temp_high
        self._target_temp_low = target_temp_low
        self._auto_cool_delta_template = auto_cool_delta
        self._auto_heat_delta_template = auto_heat_delta
        self._unit = unit
        self._unique_id = unique_id
        self._hvac_action: HVACAction = HVACAction.IDLE
        self._window_ctrl = window_contoller
        self._preset_ctrl = preset_controller
        self._saved_preset_state = None

        if object_id:
            self.entity_id = async_generate_entity_id(
                ENTITY_ID_FORMAT, object_id, None, hass
            )

        for controller in self._controllers:
            controller.set_thermostat(self)
            if (
                controller.mode == HVACMode.HEAT
                and HVACMode.HEAT not in self._hvac_list
            ):
                self._hvac_list.append(HVACMode.HEAT)
            elif (
                controller.mode == HVACMode.COOL
                and HVACMode.COOL not in self._hvac_list
            ):
                self._hvac_list.append(HVACMode.COOL)

        if HVACMode.COOL in self._hvac_list and HVACMode.HEAT in self._hvac_list:
            self._hvac_list.append(HVACMode.AUTO)
            if not heat_cool_disabled:
                self._hvac_list.append(HVACMode.HEAT_COOL)

        self._set_support_flags()
        self._enable_turn_on_off_backwards_compatibility = (
            False  # To be removed after deprecation period
        )

    @property
    def should_poll(self) -> bool:
        """Return the polling state."""
        return False

    @property
    def context(self) -> Context:
        """Return context."""
        return self._context

    @property
    def name(self) -> str:
        """Return the name of the thermostat."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return the unique id of this thermostat."""
        return self._unique_id

    @property
    def precision(self) -> float:
        """Return the precision of the system."""
        if self._temp_precision is not None:
            return self._temp_precision

        return super().precision

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Provides extra attributes."""
        attrs = {
            CONF_AUTO_COOL_DELTA: self._auto_cool_delta,
            CONF_AUTO_HEAT_DELTA: self._auto_heat_delta,
        }

        for controller in self._controllers:
            extra_controller_attrs = controller.extra_state_attributes
            if extra_controller_attrs:
                attrs[controller.get_unique_id()] = extra_controller_attrs

        attrs[ATTR_LAST_ASYNC_CONTROL_HVAC_MODE] = self._last_async_control_hvac_mode
        attrs[ATTR_LAST_ACTIVE_HVAC_MODE] = self._last_active_hvac_mode

        if self._saved_preset_state is not None:
            attrs[ATTR_PRESET_NONE_SAVED_STATE] = self._saved_preset_state

        return attrs

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return the list of supported features."""
        return self._support_flags

    @property
    def target_temperature_step(self) -> float | None:
        """Return the supported step of target temperature."""
        if self._target_temp_step is not None:
            return self._target_temp_step

        return self.precision

    @property
    def temperature_unit(self) -> UnitOfTemperature:
        """Return the unit of measurement."""
        return self._unit

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        if self._min_temp is not None:
            return self._min_temp

        return super().min_temp

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        if self._max_temp is not None:
            return self._max_temp

        return super().max_temp

    @property
    def current_temperature(self) -> float | None:
        """Return the sensor temperature."""
        return self._cur_temp

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        return self._target_temp

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """List of available operation modes."""
        return self._hvac_list

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return current operation."""
        return self._hvac_mode

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current running hvac operation if supported."""
        if self._hvac_mode == HVACMode.OFF:
            return HVACAction.OFF

        for controller in self._controllers:
            if controller.is_active:
                if controller.mode == HVACMode.COOL:
                    return HVACAction.COOLING
                if controller.mode == HVACMode.HEAT:
                    return HVACAction.HEATING

        return HVACAction.IDLE

    @property
    def _default_target_temp(self) -> float:
        return self.min_temp

    @property
    def target_temperature_low(self) -> float | None:
        """Return the lower bound temperature."""
        return self._target_temp_low

    @property
    def _default_target_temp_low(self) -> float:
        return self.min_temp

    @property
    def target_temperature_high(self) -> float | None:
        """Return the upper bound temperature."""
        return self._target_temp_high

    @property
    def _default_target_temp_high(self) -> float:
        return self.max_temp

    @property
    def _auto_cool_delta(self) -> float | None:
        """Returns Temperature Delta for coolers in Auto mode."""
        if self._auto_cool_delta_template is None:
            _LOGGER.warning(
                "%s: auto_cool_delta template is none. Return default: %s",
                self.entity_id,
                DEFAULT_AUTO_HEAT_DELTA,
            )
            return float(DEFAULT_AUTO_COOL_DELTA)

        try:
            auto_cool_delta = self._auto_cool_delta_template.async_render(
                parse_result=False
            )
        except (TemplateError, TypeError) as e:
            _LOGGER.warning(
                "%s: unable to render auto_cool_delta template: %s. Return default: %s. Error: %s",
                self.entity_id,
                self._auto_cool_delta_template,
                DEFAULT_AUTO_COOL_DELTA,
                e,
            )
            return float(DEFAULT_AUTO_COOL_DELTA)

        try:
            return float(auto_cool_delta)
        except ValueError as e:
            _LOGGER.warning(
                "%s: unable to convert auto_cool_delta template value to float: %s. Return default: %s. Error: %s",
                self.entity_id,
                self._auto_cool_delta_template,
                DEFAULT_AUTO_COOL_DELTA,
                e,
            )
            return float(DEFAULT_AUTO_COOL_DELTA)

    @property
    def _auto_heat_delta(self) -> float | None:
        """Returns Temperature Delta for heaters in Auto mode."""
        if self._auto_heat_delta_template is None:
            _LOGGER.warning(
                "%s: auto_heat_delta template is none. Return default: %s",
                self.entity_id,
                DEFAULT_AUTO_HEAT_DELTA,
            )
            return float(DEFAULT_AUTO_HEAT_DELTA)

        try:
            auto_heat_delta = self._auto_heat_delta_template.async_render(
                parse_result=False
            )
        except (TemplateError, TypeError) as e:
            _LOGGER.warning(
                "%s: unable to render auto_heat_delta template: %s. Return default: %s. Error: %s",
                self.entity_id,
                self._auto_heat_delta_template,
                DEFAULT_AUTO_HEAT_DELTA,
                e,
            )
            return float(DEFAULT_AUTO_HEAT_DELTA)

        try:
            return float(auto_heat_delta)
        except ValueError as e:
            _LOGGER.warning(
                "%s: unable to convert auto_heat_delta template value to float: %s. Return default: %s. Error: %s",
                self.entity_id,
                self._auto_heat_delta_template,
                DEFAULT_AUTO_HEAT_DELTA,
                e,
            )
            return float(DEFAULT_AUTO_HEAT_DELTA)

    @property
    def _preset_auto_heat_delta(self) -> float:
        """Returns Preset temperature delta for coolers in Auto mode."""
        if self._preset_ctrl is not None and self._hvac_mode == HVACMode.AUTO:
            return self._preset_ctrl.auto_heat_delta

        return DEFAULT_PRESET_AUTO_TEMP_DELTA

    @property
    def _preset_auto_cool_delta(self) -> float:
        """Returns Preset temperature delta for heaters in Auto mode."""
        if self._preset_ctrl is not None and self._hvac_mode == HVACMode.AUTO:
            return self._preset_ctrl.auto_cool_delta

        return DEFAULT_PRESET_AUTO_TEMP_DELTA

    @property
    def _preset_auto_heat_target(self) -> float | None:
        if self._preset_ctrl is not None and self._hvac_mode == HVACMode.AUTO:
            return self._preset_ctrl.auto_heat_target
        return None

    @property
    def _preset_auto_cool_target(self) -> float | None:
        if self._preset_ctrl is not None and self._hvac_mode == HVACMode.AUTO:
            return self._preset_ctrl.auto_cool_target
        return None

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        if self._preset_ctrl is not None:
            return self._preset_ctrl.preset_mode

        return PRESET_NONE

    @property
    def preset_modes(self) -> list[str] | None:
        """Return a list of available preset modes."""
        if self._preset_ctrl is not None:
            return self._preset_ctrl.preset_modes
        return None

    async def async_added_to_hass(self):
        """Run when entity about to be added."""
        await super().async_added_to_hass()

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self.sensor_entity_id], self._async_sensor_changed
            )
        )

        if HVACMode.AUTO in self._hvac_list:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    self._get_used_template_entity_ids(),
                    self._async_template_entities_changed,
                )
            )

        old_state: State | None = await self.async_get_last_state()

        for controller in self._controllers:
            attrs = (
                old_state.attributes.get(controller.get_unique_id(), {})
                if old_state
                else {}
            )

            await controller.async_added_to_hass(self.hass, attrs)

            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    controller.get_target_entity_ids(),
                    self._async_controller_target_entities_changed,
                )
            )

            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    controller.get_used_template_entity_ids(),
                    self._async_controller_template_entities_changed,
                )
            )

        if self._window_ctrl is not None:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    self._window_ctrl.entity_ids,
                    self._async_window_entities_changed,
                )
            )
            max_windows_timeout = self._window_ctrl.max_timeout
            if max_windows_timeout:
                self.async_on_remove(
                    async_call_later(
                        self.hass,
                        max_windows_timeout,
                        self._async_window_delayed_control,
                    )
                )

        if self._preset_ctrl is not None:
            await self._preset_ctrl.async_added_to_hass(self.entity_id)

        async def _async_first_run():
            """Will called one time. Need on hot reload when HA core is running."""
            await self._async_control(reason=REASON_THERMOSTAT_FIRST_RUN)
            self.async_write_ha_state()

        async def _async_startup(*_):
            """Init on startup."""
            sensor_state: State | None = self.hass.states.get(self.sensor_entity_id)
            if sensor_state and sensor_state.state not in (
                STATE_UNAVAILABLE,
                STATE_UNKNOWN,
            ):
                await self._async_update_temp(sensor_state.state)
                self.async_write_ha_state()

            _LOGGER.info(
                "%s: thermostat ready, supported HVAC modes: %s",
                self.entity_id,
                self._hvac_list,
            )

            self.hass.create_task(_async_first_run())

        if self.hass.state == CoreState.running:
            await _async_startup()
        else:
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, _async_startup)

        # Check If we have an old state
        old_state: State | None = await self.async_get_last_state()
        if old_state is not None:
            # If we have no initial temperature, restore
            if self._target_temp_low is None:
                old_target_low = old_state.attributes.get(ATTR_TARGET_TEMP_LOW)
                if old_target_low is not None:
                    self._target_temp_low = float(old_target_low)
                else:
                    self._target_temp_low = self._default_target_temp_low
                    _LOGGER.debug(
                        "%s: no target low temperature found in old state, falling back to default: %s",
                        self.entity_id,
                        self._target_temp_low,
                    )
            if self._target_temp_high is None:
                old_target_high = old_state.attributes.get(ATTR_TARGET_TEMP_HIGH)
                if old_target_high is not None:
                    self._target_temp_high = float(old_target_high)
                else:
                    self._target_temp_high = self._default_target_temp_high
                    _LOGGER.debug(
                        "%s: no target high temperature found in old state, falling back to default: %s",
                        self.entity_id,
                        self._target_temp_high,
                    )
            if self._target_temp is None:
                old_target = old_state.attributes.get(ATTR_TEMPERATURE)
                if old_target is not None:
                    self._target_temp = float(old_target)
                else:
                    self._target_temp = self._default_target_temp
                    _LOGGER.debug(
                        "%s: no target temperature found in old state, falling back to default: %s",
                        self.entity_id,
                        self._target_temp,
                    )

            if not self._hvac_mode and old_state.state in self._hvac_list:
                self._hvac_mode = old_state.state
                self._set_support_flags()

            self._last_async_control_hvac_mode = old_state.attributes.get(
                ATTR_LAST_ASYNC_CONTROL_HVAC_MODE
            )

            saved_preset_state = old_state.attributes.get(ATTR_PRESET_NONE_SAVED_STATE)
            if saved_preset_state and self._preset_ctrl:
                self._saved_preset_state = self._preset_ctrl.get_saved(
                    saved_preset_state.get(PRESET_NONE_HVAC_MODE),
                    saved_preset_state.get(PRESET_NONE_TARGET_TEMP),
                    saved_preset_state.get(PRESET_NONE_TARGET_TEMP_LOW),
                    saved_preset_state.get(PRESET_NONE_TARGET_TEMP_HIGH),
                )

            old_preset_mode = old_state.attributes.get(ATTR_PRESET_MODE)
            if old_preset_mode and self._preset_ctrl:
                self._preset_ctrl.set_preset(old_preset_mode)

            last_mode = old_state.attributes.get(ATTR_LAST_ACTIVE_HVAC_MODE)
            if last_mode in self._hvac_list:
                self._last_active_hvac_mode = last_mode

        else:
            self._target_temp = self._default_target_temp
            self._target_temp_low = self._default_target_temp_low
            self._target_temp_high = self._default_target_temp_high
            _LOGGER.debug(
                "%s: no previously saved temperatures, setting defaults (target: %s, target_low: %s, target_high: %s)",
                self.entity_id,
                self._target_temp,
                self._target_temp_low,
                self._target_temp_high,
            )

        if not self._hvac_mode:
            _LOGGER.debug(
                "%s: no previously saved HVAC mode, setting default (%s)",
                self.entity_id,
                HVACMode.OFF,
            )
            self._hvac_mode = HVACMode.OFF
            self._last_active_hvac_mode = None

    def get_ctrl_target_temperature(self, ctrl_hvac_mode) -> float:
        """Return target temperature for controller."""
        if self._hvac_mode == HVACMode.HEAT_COOL:
            if ctrl_hvac_mode == HVACMode.HEAT:
                return self._target_temp_low

            if ctrl_hvac_mode == HVACMode.COOL:
                return self._target_temp_high
            return None

        if self._hvac_mode == HVACMode.AUTO:
            if ctrl_hvac_mode == HVACMode.HEAT:
                if self._preset_auto_heat_target is not None:
                    return self._preset_auto_heat_target

                return (
                    self._target_temp
                    - self._auto_heat_delta
                    + self._preset_auto_heat_delta
                )

            if ctrl_hvac_mode == HVACMode.COOL:
                if self._preset_auto_cool_target is not None:
                    return self._preset_auto_cool_target

                return (
                    self._target_temp
                    + self._auto_cool_delta
                    + self._preset_auto_cool_delta
                )
            return None

        return self._target_temp

    def _get_used_template_entity_ids(self) -> list[str]:
        """Add used template entities to track state change."""
        tracked_entities = []

        if self._auto_cool_delta_template is not None:
            try:
                template_info: RenderInfo = (
                    self._auto_cool_delta_template.async_render_to_info()
                )
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "%s: unable to get auto_cool_delta template info: %s. Error: %s",
                    self.entity_id,
                    self._auto_cool_delta_template,
                    e,
                )
            else:
                tracked_entities.extend(template_info.entities)

        if self._auto_heat_delta_template is not None:
            try:
                template_info: RenderInfo = (
                    self._auto_heat_delta_template.async_render_to_info()
                )
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "%s: unable to get auto_heat_delta template info: %s. Error: %s",
                    self.entity_id,
                    self._auto_heat_delta_template,
                    e,
                )
            else:
                tracked_entities.extend(template_info.entities)

        return tracked_entities

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        if self._last_active_hvac_mode is not None:
            await self.async_set_hvac_mode(self._last_active_hvac_mode)
        else:
            await super().async_turn_on()

    async def async_set_hvac_mode(self, hvac_mode) -> None:
        """Set hvac mode."""
        if hvac_mode not in self._hvac_list:
            _LOGGER.error("%s: unsupported hvac mode: %s", self.entity_id, hvac_mode)
            return

        if hvac_mode == self._hvac_mode:
            _LOGGER.info(
                "%s: no need to control. HVAC mode %s already set",
                self.entity_id,
                hvac_mode,
            )
            return

        if self._preset_ctrl is not None:
            _LOGGER.info(
                "%s: HVAC mode is to be changed. Resetting preset to None",
                self.entity_id,
            )
            self._preset_ctrl.set_preset(PRESET_NONE)
            self._preset_ctrl.reset_saved()

        self._toggle_target_temps(hvac_mode)
        self._hvac_mode = hvac_mode
        self._set_support_flags()

        await self._async_control(
            force=True, reason=REASON_THERMOSTAT_HVAC_MODE_CHANGED
        )

        self.async_write_ha_state()

    def _round_to_target_precision(self, value: float) -> float:
        if self._target_temp_step:
            try:
                step = float(self._target_temp_step)
            except ValueError as e:
                _LOGGER.warning(
                    "%s: unable to convert thermostat temp_step value to float: %s. Return default: %s. Error: %s",
                    self.entity_id,
                    step,
                    value,
                    e,
                )
            else:
                return round(value / step) * step

        return value

    def _toggle_target_temps(self, new_hvac_mode: HVACMode) -> None:
        """Sync non-ranged with ranged target temperatures if necessary."""
        if (
            new_hvac_mode == HVACMode.HEAT_COOL
            and self._last_active_hvac_mode != HVACMode.HEAT_COOL
        ):
            _LOGGER.info(
                "%s: hvac_mode changed to %s: calculating ranged target temperatures",
                self.entity_id,
                new_hvac_mode,
            )
            match self._last_active_hvac_mode:
                case HVACMode.COOL:
                    self._target_temp_high = self._target_temp
                    self._target_temp_low = self._round_to_target_precision(
                        self._target_temp - self._auto_heat_delta
                    )
                case HVACMode.HEAT:
                    self._target_temp_low = self._target_temp
                    self._target_temp_high = self._round_to_target_precision(
                        self._target_temp + self._auto_cool_delta
                    )
                case HVACMode.AUTO:
                    self._target_temp_low = self._round_to_target_precision(
                        self._target_temp - self._auto_heat_delta
                    )
                    self._target_temp_high = self._round_to_target_precision(
                        self._target_temp + self._auto_cool_delta
                    )

        elif (
            new_hvac_mode in (HVACMode.HEAT, HVACMode.COOL, HVACMode.AUTO)
            and self._last_active_hvac_mode == HVACMode.HEAT_COOL
        ):
            _LOGGER.info(
                "%s: hvac_mode changed to %s: calculating target temperature",
                self.entity_id,
                new_hvac_mode,
            )
            match new_hvac_mode:
                case HVACMode.COOL:
                    self._target_temp = self._target_temp_high
                case HVACMode.HEAT:
                    self._target_temp = self._target_temp_low
                case HVACMode.AUTO:
                    self._target_temp = self._round_to_target_precision(
                        (self._target_temp_low + self._target_temp_high) / 2
                    )

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        temp_low = kwargs.get(ATTR_TARGET_TEMP_LOW)
        temp_high = kwargs.get(ATTR_TARGET_TEMP_HIGH)

        if self._support_flags & ClimateEntityFeature.TARGET_TEMPERATURE:
            if temperature is None:
                _LOGGER.warning("%s: undefined target temperature", self.entity_id)
                return
            self._target_temp = self._round_to_target_precision(temperature)

        elif self._support_flags & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE:
            if temp_low is None and temp_high is None:
                _LOGGER.warning(
                    "%s: undefined target low/high temperatures", self.entity_id
                )
                return
            if temp_low is not None:
                self._target_temp_low = self._round_to_target_precision(temp_low)
            if temp_high is not None:
                self._target_temp_high = self._round_to_target_precision(temp_high)

        await self._async_control(
            force=True, reason=REASON_THERMOSTAT_TARGET_TEMP_CHANGED
        )
        self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if preset_mode not in (self.preset_modes or []):
            _LOGGER.warning(
                "%s: unsupported preset_mode %s. Must be one of %s",
                self.entity_id,
                preset_mode,
                self.preset_modes,
            )
            return

        if preset_mode == self.preset_mode:
            _LOGGER.info(
                "%s: no need to change preset: %s already set",
                self.entity_id,
                self.preset_mode,
            )
            return

        if self._preset_ctrl.preset_mode == PRESET_NONE:
            self._saved_preset_state = self._preset_ctrl.get_saved(
                self._hvac_mode,
                self._target_temp,
                self._target_temp_low,
                self._target_temp_high,
            )
        self._preset_ctrl.set_preset(preset_mode)

        new_hvac_mode = self._preset_ctrl.get_hvac_mode(self._hvac_mode)
        if new_hvac_mode in self._hvac_list and self._hvac_mode != new_hvac_mode:
            _LOGGER.info(
                "%s: preset %s settings needs to change hvac mode to %s",
                self.entity_id,
                preset_mode,
                new_hvac_mode,
            )
            self._hvac_mode = new_hvac_mode
            self._toggle_target_temps(new_hvac_mode)
            self._set_support_flags()

        if self._support_flags & ClimateEntityFeature.TARGET_TEMPERATURE:
            new_target_temp = self._preset_ctrl.get_target_temp(
                self._hvac_mode, self._target_temp
            )
            if (
                isinstance(new_target_temp, float)
                and self._target_temp != new_target_temp
            ):
                _LOGGER.info(
                    "%s: preset %s settings needs to change target temperature to %s",
                    self.entity_id,
                    preset_mode,
                    new_target_temp,
                )
                self._target_temp = new_target_temp

        if self._support_flags & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE:
            new_target_temp_low = self._preset_ctrl.get_target_temp_low(
                self._target_temp_low
            )
            if (
                isinstance(new_target_temp_low, float)
                and self._target_temp_low != new_target_temp_low
            ):
                _LOGGER.info(
                    "%s: preset %s settings needs to change low target temperature to %s",
                    self.entity_id,
                    preset_mode,
                    new_target_temp_low,
                )
                self._target_temp_low = new_target_temp_low

            new_target_temp_high = self._preset_ctrl.get_target_temp_high(
                self._target_temp_high
            )
            if (
                isinstance(new_target_temp_high, float)
                and self._target_temp_high != new_target_temp_high
            ):
                _LOGGER.info(
                    "%s: preset %s settings needs to change high target temperature to %s",
                    self.entity_id,
                    preset_mode,
                    new_target_temp_high,
                )
                self._target_temp_high = new_target_temp_high

        if self._preset_ctrl.preset_mode == PRESET_NONE:
            self._saved_preset_state = None

        await self._async_control(force=True, reason=REASON_PRESET_CHANGED)
        self.async_write_ha_state()

    async def _async_sensor_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle temperature changes."""
        new_state: State | None = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        old_state: State | None = event.data.get("old_state")
        if old_state is not None and old_state.state == new_state.state:
            _LOGGER.info(
                "%s: target sensor not changed (%s) - no need to control",
                self.entity_id,
                new_state.state,
            )
            return

        _LOGGER.info(
            "%s: target sensor changed (%s -> %s)",
            self.entity_id,
            old_state.state,
            new_state.state,
        )
        await self._async_update_temp(new_state.state)

        await self._async_control(reason=REASON_THERMOSTAT_SENSOR_CHANGED)
        self.async_write_ha_state()

    async def _async_controller_target_entities_changed(self, event) -> None:
        """Handle controller target entities changes."""
        _ = event
        self.async_write_ha_state()

    async def _async_template_entities_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle thermostat template entities changes."""
        new_state: State | None = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        entity_id = event.data.get("entity_id")
        old_state: State | None = event.data.get("old_state")
        if old_state is not None and old_state.state == new_state.state:
            _LOGGER.info(
                "%s: thermostat template entity %s not changed (%s) - no need to control",
                self.entity_id,
                entity_id,
                new_state.state,
            )
            return

        _LOGGER.info(
            "%s: thermostat template entity %s changed (%s -> %s)",
            self.entity_id,
            entity_id,
            old_state.state,
            new_state.state,
        )
        await self._async_control(reason=REASON_TEMPLATE_ENTITY_CHANGED)
        self.async_write_ha_state()

    async def _async_controller_template_entities_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle controller template entities changes."""
        new_state: State | None = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        entity_id = event.data.get("entity_id")
        old_state: State | None = event.data.get("old_state")
        if old_state is not None and old_state.state == new_state.state:
            _LOGGER.info(
                "%s: controller template entity %s not changed (%s) - no need to control",
                self.entity_id,
                entity_id,
                new_state.state,
            )
            return

        _LOGGER.info(
            "%s: controller template entity %s changed (%s -> %s)",
            self.entity_id,
            entity_id,
            old_state.state if old_state else None,
            new_state.state,
        )
        await self._async_control(reason=REASON_CONTROLLER_TEMPLATE_ENTITY_CHANGED)
        self.async_write_ha_state()

    async def _async_window_entities_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle windows entities changes."""
        new_state: State | None = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        entity_id = event.data.get("entity_id")
        old_state: State | None = event.data.get("old_state")
        if old_state is not None and old_state.state == new_state.state:
            _LOGGER.info(
                "%s: window entity %s not changed (%s) - no need to control",
                self.entity_id,
                entity_id,
                new_state.state,
            )
            return

        _LOGGER.info(
            "%s: window entity %s changed (%s -> %s)",
            self.entity_id,
            entity_id,
            old_state.state,
            new_state.state,
        )
        window = self._window_ctrl.find_by_entity_id(entity_id)
        if window.timeout is not None:
            self.async_on_remove(
                async_call_later(
                    self.hass,
                    window.timeout,
                    self._async_window_delayed_control,
                )
            )
        else:
            await self._async_window_delayed_control()

    async def _async_window_delayed_control(self, time=None) -> None:
        await self._async_control(reason=REASON_WINDOW_ENTITY_CHANGED)
        self.async_write_ha_state()

    async def _async_update_temp(self, temp) -> None:
        """Update thermostat with latest state from sensor."""
        if temp in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
            self._cur_temp = None
            return

        try:
            temp = float(temp)
        except TypeError as e:
            _LOGGER.error("%s: unable to update from sensor: %s", self.entity_id, e)
            self._cur_temp = None
            return

        if math.isnan(temp) or math.isinf(temp):
            _LOGGER.error("%s: sensor has illegal value %s", self.entity_id, temp)
            self._cur_temp = None
            return

        self._cur_temp = temp

    def _set_support_flags(self) -> None:
        """Set support flags based on configuration."""
        if (
            self._hvac_mode == HVACMode.OFF
            and self._last_active_hvac_mode == HVACMode.HEAT_COOL
        ) or self._hvac_mode == HVACMode.HEAT_COOL:
            self._support_flags = ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        else:
            self._support_flags = ClimateEntityFeature.TARGET_TEMPERATURE

        if self._preset_ctrl is not None:
            self._support_flags |= ClimateEntityFeature.PRESET_MODE

        self._support_flags |= ClimateEntityFeature.TURN_OFF
        self._support_flags |= ClimateEntityFeature.TURN_ON

    async def _async_control(self, time=None, force=False, reason=None) -> None:
        """Call controllers."""
        async with self._temp_lock:
            if self._last_async_control_hvac_mode != self._hvac_mode:
                _LOGGER.info(
                    "%s: HVAC mode changed: %s -> %s",
                    self.entity_id,
                    self._last_async_control_hvac_mode,
                    self._hvac_mode,
                )

                if self._hvac_mode != HVACMode.OFF:
                    self._last_active_hvac_mode = self._hvac_mode

            elif self._hvac_mode == HVACMode.OFF:
                # Skip control, last `OFF` was already processed
                return

            is_windows_opened = False
            if self._window_ctrl is not None and reason != REASON_THERMOSTAT_FIRST_RUN:
                is_windows_opened = self._window_ctrl.is_safe_opened

            for controller in self._controllers:
                controller_debug_info = (
                    f"running: {controller.running}, active: {controller.is_active}"
                )

                if controller.running:
                    if (
                        is_windows_opened
                        and not controller.ignore_windows
                        or self._hvac_mode
                        not in (HVACMode.COOL, HVACMode.HEAT_COOL, HVACMode.AUTO)
                        and controller.mode == HVACMode.COOL
                        or self._hvac_mode
                        not in (HVACMode.HEAT, HVACMode.HEAT_COOL, HVACMode.AUTO)
                        and controller.mode == HVACMode.HEAT
                    ):
                        _LOGGER.info(
                            "%s: stopping %s, %s",
                            self.entity_id,
                            controller.name,
                            controller_debug_info,
                        )
                        await controller.async_stop()
                        continue

                if (
                    not controller.running
                    and (controller.ignore_windows or not is_windows_opened)
                    and (
                        self._hvac_mode
                        in (HVACMode.COOL, HVACMode.HEAT_COOL, HVACMode.AUTO)
                        and controller.mode == HVACMode.COOL
                        or self._hvac_mode
                        in (HVACMode.HEAT, HVACMode.HEAT_COOL, HVACMode.AUTO)
                        and controller.mode == HVACMode.HEAT
                    )
                ):
                    _LOGGER.info(
                        "%s: starting %s, %s",
                        self.entity_id,
                        controller.name,
                        controller_debug_info,
                    )
                    await controller.async_start()

                await controller.async_control(time=time, force=force, reason=reason)

            self._last_async_control_hvac_mode = self._hvac_mode
