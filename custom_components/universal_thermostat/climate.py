"""Adds support for universal thermostat units."""

import asyncio
from collections.abc import Mapping
import logging
import math
from typing import Any, Optional

import voluptuous as vol
from voluptuous import ALLOW_EXTRA

from homeassistant.components.climate import (
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    DOMAIN as CLIMATE_DOMAIN,
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
)
from homeassistant.core import (
    Context,
    CoreState,
    HomeAssistant,
    callback,
    split_entity_id,
)
from homeassistant.exceptions import TemplateError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.config_validation import PLATFORM_SCHEMA
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.reload import async_setup_reload_service
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.template import RenderInfo

from . import DOMAIN, PLATFORMS
from .const import (
    ATTR_LAST_ACTIVE_HVAC_MODE,
    ATTR_LAST_ASYNC_CONTROL_HVAC_MODE,
    ATTR_PREV_TARGET,
    ATTR_PREV_TARGET_HIGH,
    ATTR_PREV_TARGET_LOW,
    CONF_AUTO_COOL_DELTA,
    CONF_AUTO_HEAT_DELTA,
    CONF_CLIMATE_TEMP_DELTA,
    CONF_COLD_TOLERANCE,
    CONF_COOLER,
    CONF_HEAT_COOL_DISABLED,
    CONF_HEATER,
    CONF_HOT_TOLERANCE,
    CONF_INITIAL_HVAC_MODE,
    CONF_INVERTED,
    CONF_KEEP_ALIVE,
    CONF_MAX_TEMP,
    CONF_MIN_DUR,
    CONF_MIN_TEMP,
    CONF_PID_KD,
    CONF_PID_KI,
    CONF_PID_KP,
    CONF_PID_MAX,
    CONF_PID_MIN,
    CONF_PID_SAMPLE_PERIOD,
    CONF_PID_SWITCH_ENTITY_ID,
    CONF_PID_SWITCH_INVERTED,
    CONF_PRECISION,
    CONF_PWM_SWITCH_PERIOD,
    CONF_SENSOR,
    CONF_TARGET_TEMP,
    CONF_TARGET_TEMP_HIGH,
    CONF_TARGET_TEMP_LOW,
    CONF_TEMP_STEP,
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
    REASON_AUTO_COOL_DELTAS_CHANGED,
    REASON_CONTROL_ENTITY_CHANGED,
    REASON_THERMOSTAT_FIRST_RUN,
    REASON_THERMOSTAT_HVAC_MODE_CHANGED,
    REASON_THERMOSTAT_SENSOR_CHANGED,
    REASON_THERMOSTAT_TARGET_TEMP_CHANGED,
)
from .controllers import (
    AbstractController,
    ClimatePidController,
    ClimateSwitchController,
    NumberPidController,
    PwmSwitchPidController,
    SwitchController,
)

SUPPORTED_TARGET_DOMAINS = [
    SWITCH_DOMAIN,
    INPUT_BOOLEAN_DOMAIN,
    CLIMATE_DOMAIN,
    NUMBER_DOMAIN,
    INPUT_NUMBER_DOMAIN,
]

_LOGGER = logging.getLogger(__name__)


CTRL_SCHEMA_COMMON = vol.Schema(
    {
        vol.Required(CONF_ENTITY_ID): cv.entity_domain(SUPPORTED_TARGET_DOMAINS),
        vol.Optional(CONF_INVERTED, default=False): bool,
        vol.Optional(CONF_KEEP_ALIVE, default=None): vol.Any(
            None, cv.positive_time_period
        ),
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
        vol.Required(CONF_PID_SWITCH_ENTITY_ID): cv.entity_domain(
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

DATA_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_UNIQUE_ID): cv.string,
        vol.Optional(CONF_HEATER): vol.Any(
            _cv_controller_target, [_cv_controller_target]
        ),
        vol.Optional(CONF_COOLER): vol.Any(
            _cv_controller_target, [_cv_controller_target]
        ),
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
    hass: HomeAssistant, config, async_add_entities, discovery_info=None
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

    async_add_entities(
        [
            UniversalThermostat(
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
            )
        ]
    )


class UniversalThermostat(ClimateEntity, RestoreEntity):
    """Representation of a Universal Thermostat device."""

    def __init__(
        self,
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
    ) -> None:
        """Initialize the thermostat."""
        self._name = name
        self._controllers: list[AbstractController] = controllers
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
        self._hvac_action = HVACAction.IDLE

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

    async def async_added_to_hass(self):
        """Run when entity about to be added."""
        await super().async_added_to_hass()

        # Add listener
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self.sensor_entity_id], self._async_sensor_changed
            )
        )

        if HVACMode.AUTO in self._hvac_list:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    self.get_used_template_entity_ids(),
                    self._async_auto_mode_deltas_changed,
                )
            )

        old_state = await self.async_get_last_state()

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

        async def _async_first_run():
            """Will called one time. Need on hot reload when HA core is running."""
            await self._async_control(reason=REASON_THERMOSTAT_FIRST_RUN)
            self.async_write_ha_state()

        @callback
        async def _async_startup(*_):
            """Init on startup."""
            sensor_state = self.hass.states.get(self.sensor_entity_id)
            if sensor_state and sensor_state.state not in (
                STATE_UNAVAILABLE,
                STATE_UNKNOWN,
            ):
                await self._async_update_temp(sensor_state.state)
                self.async_write_ha_state()

            _LOGGER.info(
                "%s: Ready, supported HVAC modes: %s",
                self.name,
                self._hvac_list,
            )

            self.hass.create_task(_async_first_run())

        if self.hass.state == CoreState.running:
            await _async_startup()
        else:
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, _async_startup)

        # Check If we have an old state
        old_state = await self.async_get_last_state()
        if old_state is not None:
            # If we have no initial temperature, restore
            if self._target_temp_low is None:
                old_target_low = old_state.attributes.get(ATTR_PREV_TARGET_LOW)
                if old_target_low is None:
                    old_target_low = old_state.attributes.get(ATTR_TARGET_TEMP_LOW)
                if old_target_low is not None:
                    self._target_temp_low = float(old_target_low)
                else:
                    self._target_temp_low = self._get_default_target_temp_low()
                    _LOGGER.warning(
                        "%s: Undefined target low temperature, falling back to %s",
                        self.name,
                        self._target_temp_low,
                    )
            if self._target_temp_high is None:
                old_target_high = old_state.attributes.get(ATTR_PREV_TARGET_HIGH)
                if old_target_high is None:
                    old_target_high = old_state.attributes.get(ATTR_TARGET_TEMP_HIGH)
                if old_target_high is not None:
                    self._target_temp_high = float(old_target_high)
                else:
                    self._target_temp_high = self._get_default_target_temp_high()
                    _LOGGER.warning(
                        "%s: Undefined target high temperature, falling back to %s",
                        self.name,
                        self._target_temp_high,
                    )
            if self._target_temp is None:
                old_target = old_state.attributes.get(ATTR_PREV_TARGET)
                if old_target is None:
                    old_target = old_state.attributes.get(ATTR_TEMPERATURE)
                if old_target is not None:
                    self._target_temp = float(old_target)

            if (
                not self._hvac_mode
                and old_state.state
                and old_state.state in self._hvac_list
            ):
                self._hvac_mode = old_state.state
                self._set_support_flags()

            self._last_async_control_hvac_mode = old_state.attributes.get(
                ATTR_LAST_ASYNC_CONTROL_HVAC_MODE
            )

            last_mode = old_state.attributes.get(ATTR_LAST_ACTIVE_HVAC_MODE)
            if last_mode in self._hvac_list:
                self._last_active_hvac_mode = last_mode

        else:
            # No previous state, try and restore defaults
            self._target_temp = self._get_default_target_temp()
            self._target_temp_low = self._get_default_target_temp_low()
            self._target_temp_high = self._get_default_target_temp_high()
            _LOGGER.warning(
                "%s: No previously saved temperatures, setting to %s (target), %s (target low), %s (target high)",
                self.name,
                self._target_temp,
                self._target_temp_low,
                self._target_temp_high,
            )

        # Set default state to off
        if not self._hvac_mode:
            self._hvac_mode = HVACMode.OFF
            self._last_active_hvac_mode = None

    def get_hass(self) -> HomeAssistant:
        """Return Hass object."""
        return self.hass

    def get_entity_id(self) -> str:
        """Return universal thermostat entity_id."""
        return self.entity_id

    def get_context(self) -> Context:
        """Return context."""
        return self._context

    def get_hvac_mode(self):
        """Return current HVAC mode."""
        return self.hvac_mode

    def get_ctrl_target_temperature(self, ctrl_hvac_mode):
        """Return target temperature for controller."""
        if self._hvac_mode == HVACMode.HEAT_COOL:
            if ctrl_hvac_mode == HVACMode.HEAT:
                return self._target_temp_low
            if ctrl_hvac_mode == HVACMode.COOL:
                return self._target_temp_high
        elif self._hvac_mode == HVACMode.AUTO:
            if ctrl_hvac_mode == HVACMode.HEAT:
                return self._target_temp - self._auto_heat_delta
            if ctrl_hvac_mode == HVACMode.COOL:
                return self._target_temp + self._auto_cool_delta
        else:
            return self._target_temp

    def get_current_temperature(self):
        """Return current temperature from target sensor."""
        return self.current_temperature

    def _get_default_target_temp(self):
        return self.min_temp

    def _get_default_target_temp_low(self):
        return self.min_temp

    def _get_default_target_temp_high(self):
        return self.max_temp

    def get_used_template_entity_ids(self) -> list[str]:
        """Add used template entities to track state change."""
        tracked_entities = []

        if self._auto_cool_delta_template is not None:
            try:
                template_info: RenderInfo = (
                    self._auto_cool_delta_template.async_render_to_info()
                )
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "Unable to get template info: %s.\nError: %s",
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
                    "Unable to get template info: %s.\nError: %s",
                    self._auto_heat_delta_template,
                    e,
                )
            else:
                tracked_entities.extend(template_info.entities)

        return tracked_entities

    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def name(self):
        """Return the name of the thermostat."""
        return self._name

    @property
    def unique_id(self):
        """Return the unique id of this thermostat."""
        return self._unique_id

    @property
    def precision(self):
        """Return the precision of the system."""
        if self._temp_precision is not None:
            return self._temp_precision
        return super().precision

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        if self._target_temp_step is not None:
            return self._target_temp_step
        return self.precision

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._unit

    @property
    def current_temperature(self):
        """Return the sensor temperature."""
        return self._cur_temp

    @property
    def hvac_mode(self):
        """Return current operation."""
        return self._hvac_mode

    @property
    def hvac_action(self):
        """Return the current running hvac operation if supported."""
        if self._hvac_mode == HVACMode.OFF:
            return HVACAction.OFF

        action = HVACAction.IDLE

        for controller in self._controllers:
            if controller.working:
                match controller.mode:
                    case HVACMode.COOL:
                        return HVACAction.COOLING
                    case HVACMode.HEAT:
                        return HVACAction.HEATING

        return action

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._target_temp

    @property
    def target_temperature_high(self):
        """Return the upper bound temperature."""
        return self._target_temp_high

    @property
    def target_temperature_low(self):
        """Return the lower bound temperature."""
        return self._target_temp_low

    @property
    def hvac_modes(self):
        """List of available operation modes."""
        return self._hvac_list

    @property
    def extra_state_attributes(self) -> Optional[Mapping[str, Any]]:
        """Provides extra attributes."""
        attrs = {}
        for controller in self._controllers:
            extra_controller_attrs = controller.extra_state_attributes
            if extra_controller_attrs:
                attrs[controller.get_unique_id()] = extra_controller_attrs
        attrs[ATTR_LAST_ASYNC_CONTROL_HVAC_MODE] = self._last_async_control_hvac_mode
        attrs[ATTR_LAST_ACTIVE_HVAC_MODE] = self._last_active_hvac_mode

        if self._target_temp is not None:
            attrs[ATTR_PREV_TARGET] = self._target_temp
        if self._target_temp_low is not None:
            attrs[ATTR_PREV_TARGET_LOW] = self._target_temp_low
        if self._target_temp_high is not None:
            attrs[ATTR_PREV_TARGET_HIGH] = self._target_temp_high

        return attrs

    @property
    def _auto_cool_delta(self) -> float | None:
        """Returns Temperature Delta for coolers in Auto mode."""
        if self._auto_cool_delta_template is not None:
            try:
                auto_cool_delta = self._auto_cool_delta_template.async_render(
                    parse_result=False
                )
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "Unable to render template value: %s.\nError: %s",
                    self._auto_cool_delta_template,
                    e,
                )
                return float(DEFAULT_AUTO_COOL_DELTA)

            try:
                return float(auto_cool_delta)
            except ValueError as e:
                _LOGGER.warning(
                    "Unable to convert template value to float: %s.\nError: %s",
                    self._auto_cool_delta_template,
                    e,
                )

    @property
    def _auto_heat_delta(self) -> float | None:
        """Returns Temperature Delta for heaters in Auto mode."""
        if self._auto_heat_delta_template is not None:
            try:
                auto_heat_delta = self._auto_heat_delta_template.async_render(
                    parse_result=False
                )
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "Unable to render template value: %s.\nError: %s",
                    self._auto_heat_delta_template,
                    e,
                )
                return float(DEFAULT_AUTO_HEAT_DELTA)

            try:
                return float(auto_heat_delta)
            except ValueError as e:
                _LOGGER.warning(
                    "Unable to convert template value to float: %s.\nError: %s",
                    self._auto_cool_delta_template,
                    e,
                )

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        if self._last_active_hvac_mode is not None:
            await self.async_set_hvac_mode(self._last_active_hvac_mode)
        else:
            await super().async_turn_on()

    async def async_set_hvac_mode(self, hvac_mode):
        """Set hvac mode."""
        if hvac_mode not in self._hvac_list:
            _LOGGER.error("%s: Unrecognized hvac mode: %s", self.name, hvac_mode)
            return

        if HVACMode.HEAT_COOL in self._hvac_list and hvac_mode != self._hvac_mode:
            if (
                hvac_mode == HVACMode.COOL
                and self._target_temp != self._target_temp_high
            ):
                self._target_temp = self._target_temp_high
            if (
                hvac_mode == HVACMode.HEAT
                and self._target_temp != self._target_temp_low
            ):
                self._target_temp = self._target_temp_low

        self._hvac_mode = hvac_mode
        self._set_support_flags()

        await self._async_control(
            force=True, reason=REASON_THERMOSTAT_HVAC_MODE_CHANGED
        )

        # Ensure we update the current operation after changing the mode
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        temp_low = kwargs.get(ATTR_TARGET_TEMP_LOW)
        temp_high = kwargs.get(ATTR_TARGET_TEMP_HIGH)

        if self._support_flags & ClimateEntityFeature.TARGET_TEMPERATURE:
            if temperature is None:
                return
            self._target_temp = temperature
            if HVACMode.HEAT_COOL in self._hvac_list:
                if self._hvac_mode == HVACMode.HEAT:
                    self._target_temp_low = temperature
                if self._hvac_mode == HVACMode.COOL:
                    self._target_temp_high = temperature

        elif self._support_flags & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE:
            if None in (temp_low, temp_high):
                return
            self._target_temp_low = temp_low
            self._target_temp_high = temp_high

        await self._async_control(
            force=True, reason=REASON_THERMOSTAT_TARGET_TEMP_CHANGED
        )
        self.async_write_ha_state()

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        if self._min_temp is not None:
            return self._min_temp

        # get default temp from super class
        return super().min_temp

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        if self._max_temp is not None:
            return self._max_temp

        # Get default temp from super class
        return super().max_temp

    async def _async_sensor_changed(self, event):
        """Handle temperature changes."""
        new_state = event.data.get("new_state")
        _LOGGER.info("Sensor change: %s", new_state)
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        await self._async_update_temp(new_state.state)

        await self._async_control(reason=REASON_THERMOSTAT_SENSOR_CHANGED)
        self.async_write_ha_state()

    async def _async_controller_target_entities_changed(self, event):
        """Handle controller target entities changes."""
        _ = event
        await self._async_control(reason=REASON_CONTROL_ENTITY_CHANGED)
        self.async_write_ha_state()

    async def _async_controller_template_entities_changed(self, event):
        """Handle controller template entities changes."""
        _ = event
        await self._async_control(reason=REASON_CONTROL_ENTITY_CHANGED)
        self.async_write_ha_state()

    async def _async_auto_mode_deltas_changed(self, event):
        """Handle Auto Mode deltas changes."""
        _ = event
        await self._async_control(reason=REASON_AUTO_COOL_DELTAS_CHANGED)
        self.async_write_ha_state()

    @callback
    async def _async_update_temp(self, temp):
        """Update thermostat with latest state from sensor."""
        if temp in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
            self._cur_temp = None
            return

        try:
            self._cur_temp = float(temp)
            if math.isnan(self._cur_temp) or math.isinf(self._cur_temp):
                raise ValueError(f"Sensor has illegal value {temp}")

        except (ValueError, TypeError) as ex:
            self._cur_temp = None
            _LOGGER.error("%s: Unable to update from sensor: %s", self.name, ex)

    async def _async_control(self, time=None, force=False, reason=None):
        """Call controllers."""
        async with self._temp_lock:
            if self._last_async_control_hvac_mode != self._hvac_mode:
                _LOGGER.debug(
                    "%s: mode changed: %s -> %s",
                    self.entity_id,
                    self._last_async_control_hvac_mode,
                    self._hvac_mode,
                )

                if self._hvac_mode != HVACMode.OFF:
                    self._last_active_hvac_mode = self._hvac_mode
            elif self._hvac_mode == HVACMode.OFF:
                # Skip control, last `OFF` was already processed
                return

            for controller in self._controllers:
                controller_debug_info = f"{controller.name}, running: {controller.running}, working: {controller.working}"

                if controller.running:
                    if (
                        self._hvac_mode
                        not in (HVACMode.COOL, HVACMode.HEAT_COOL, HVACMode.AUTO)
                        and controller.mode == HVACMode.COOL
                        or self._hvac_mode
                        not in (HVACMode.HEAT, HVACMode.HEAT_COOL, HVACMode.AUTO)
                        and controller.mode == HVACMode.HEAT
                    ):
                        _LOGGER.debug(
                            "%s: Stopping %s, %s",
                            self.entity_id,
                            controller.name,
                            controller_debug_info,
                        )
                        await controller.async_stop()
                        continue

                if not controller.running and (
                    self._hvac_mode
                    in (HVACMode.COOL, HVACMode.HEAT_COOL, HVACMode.AUTO)
                    and controller.mode == HVACMode.COOL
                    or self._hvac_mode
                    in (HVACMode.HEAT, HVACMode.HEAT_COOL, HVACMode.AUTO)
                    and controller.mode == HVACMode.HEAT
                ):
                    _LOGGER.debug(
                        "%s: Starting %s, %s",
                        self.entity_id,
                        controller.name,
                        controller_debug_info,
                    )
                    await controller.async_start()

                await controller.async_control(time=time, force=force, reason=reason)

            self._last_async_control_hvac_mode = self._hvac_mode

    def _set_support_flags(self) -> None:
        """Set support flags based on configuration."""
        if (
            self._hvac_mode == HVACMode.OFF
            and self._last_active_hvac_mode == HVACMode.HEAT_COOL
        ) or self._hvac_mode == HVACMode.HEAT_COOL:
            self._support_flags = ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        else:
            self._support_flags = ClimateEntityFeature.TARGET_TEMPERATURE

        self._support_flags |= ClimateEntityFeature.TURN_OFF
        self._support_flags |= ClimateEntityFeature.TURN_ON

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return self._support_flags
