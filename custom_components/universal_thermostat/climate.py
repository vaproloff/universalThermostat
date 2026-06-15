"""Adds support for universal thermostat units."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import datetime
import logging
import math
from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_PRESET_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ENTITY_ID_FORMAT,
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    CONF_NAME,
    CONF_UNIQUE_ID,
    EVENT_HOMEASSISTANT_START,
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
)
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.reload import async_setup_reload_service
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import ConfigType

from . import DOMAIN, PLATFORMS
from .config_schema import PLATFORM_SCHEMA  # noqa: F401
from .const import (
    ATTR_LAST_ACTIVE_HVAC_MODE,
    ATTR_LAST_ASYNC_CONTROL_HVAC_MODE,
    ATTR_PRESET_NONE_SAVED_STATE,
    CONF_AUTO_COOL_DELTA,
    CONF_AUTO_HEAT_DELTA,
    CONF_AUTO_MODE_DISABLED,
    CONF_COOLER,
    CONF_HEAT_COOL_DISABLED,
    CONF_HEATER,
    CONF_INITIAL_HVAC_MODE,
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_OBJECT_ID,
    CONF_PRECISION,
    CONF_PRESETS,
    CONF_SENSOR,
    CONF_TARGET_TEMP,
    CONF_TARGET_TEMP_HIGH,
    CONF_TARGET_TEMP_LOW,
    CONF_TEMP_STEP,
    CONF_WINDOWS,
    DEFAULT_AUTO_COOL_DELTA,
    DEFAULT_AUTO_HEAT_DELTA,
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
from .controller_factory import create_controllers
from .controllers.abstract_controller import AbstractController
from .controllers.preset_controller import PresetController
from .controllers.window_controller import WindowController
from .template_utils import get_template_entities, render_float

_LOGGER = logging.getLogger(__name__)


def _create_thermostat_entity(
    hass: HomeAssistant,
    config: dict[str, Any],
) -> UniversalThermostat:
    """Create thermostat entity from config-like mapping."""
    name = config.get(CONF_NAME)
    sensor_entity_id = config.get(CONF_SENSOR)
    min_temp = config.get(CONF_MIN_TEMP)
    max_temp = config.get(CONF_MAX_TEMP)
    target_temp = config.get(CONF_TARGET_TEMP)
    target_temp_high = config.get(CONF_TARGET_TEMP_HIGH)
    target_temp_low = config.get(CONF_TARGET_TEMP_LOW)
    heat_cool_disabled = config.get(CONF_HEAT_COOL_DISABLED)
    auto_mode_disabled = config.get(CONF_AUTO_MODE_DISABLED)
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
        controllers.extend(create_controllers("cooler", HVACMode.COOL, cooler_config))

    if heater_config:
        controllers.extend(create_controllers("heater", HVACMode.HEAT, heater_config))

    auto_cool_delta, auto_heat_delta = None, None
    if heater_config and cooler_config:
        auto_cool_delta = config.get(CONF_AUTO_COOL_DELTA)
        auto_heat_delta = config.get(CONF_AUTO_HEAT_DELTA)

    windows = config.get(CONF_WINDOWS)
    window_controller = WindowController(hass, windows) if windows else None

    presets = config.get(CONF_PRESETS)
    preset_controller = PresetController(presets) if presets else None

    return UniversalThermostat(
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
        auto_mode_disabled,
        initial_hvac_mode,
        precision,
        target_temp_step,
        unit,
        unique_id,
        object_id,
        window_controller,
        preset_controller,
    )


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities,
    discovery_info=None,
) -> None:
    """Set up the universal thermostat platform from YAML."""
    _ = discovery_info

    await async_setup_reload_service(hass, DOMAIN, PLATFORMS)

    entity = _create_thermostat_entity(hass, config)
    async_add_entities([entity])


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up the universal thermostat platform from a config entry."""
    config = {**entry.data, **entry.options}

    if entry.unique_id and CONF_UNIQUE_ID not in config:
        config[CONF_UNIQUE_ID] = entry.unique_id

    entity = _create_thermostat_entity(hass, config)
    async_add_entities([entity])


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
        auto_cool_delta: Template | float | None,
        auto_heat_delta: Template | float | None,
        heat_cool_disabled: bool,
        auto_mode_disabled: bool,
        initial_hvac_mode: HVACMode | None,
        precision: float | None,
        target_temp_step: float | None,
        unit: UnitOfTemperature,
        unique_id: str | None,
        object_id: str | None,
        window_controller: WindowController | None,
        preset_controller: PresetController | None,
    ) -> None:
        """Initialize the thermostat."""
        self._name = name
        self._controllers = controllers
        self.sensor_entity_id = sensor_entity_id
        self._hvac_mode = initial_hvac_mode
        self._last_async_control_hvac_mode = None
        self._last_active_hvac_mode = None
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
        self._window_ctrl = window_controller
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
            if not auto_mode_disabled:
                self._hvac_list.append(HVACMode.AUTO)
            if not heat_cool_disabled:
                self._hvac_list.append(HVACMode.HEAT_COOL)

        self._set_support_flags()

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
        """Return temperature delta for coolers in Auto mode."""
        return render_float(
            self._auto_cool_delta_template,
            DEFAULT_AUTO_COOL_DELTA,
            owner=self.entity_id,
            field=CONF_AUTO_COOL_DELTA,
            logger=_LOGGER,
        )

    @property
    def _auto_heat_delta(self) -> float | None:
        """Return temperature delta for heaters in Auto mode."""
        return render_float(
            self._auto_heat_delta_template,
            DEFAULT_AUTO_HEAT_DELTA,
            owner=self.entity_id,
            field=CONF_AUTO_HEAT_DELTA,
            logger=_LOGGER,
        )

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

    def _setup_thermostat_event_listeners(self) -> None:
        """Set up thermostat-level state listeners."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self.sensor_entity_id], self._async_sensor_changed
            )
        )

        template_entity_ids = self._get_used_template_entity_ids()
        if template_entity_ids:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    template_entity_ids,
                    self._async_template_entities_changed,
                )
            )

    def _get_restored_controller_attrs(
        self, old_state: State | None, controller: AbstractController
    ) -> Mapping[str, Any]:
        """Return controller attrs from current or legacy storage keys."""
        if old_state is None:
            return {}

        attrs = old_state.attributes.get(controller.get_unique_id())
        if attrs is not None:
            return attrs

        legacy_attrs = old_state.attributes.get(controller.get_legacy_unique_id(), {})
        legacy_mode = legacy_attrs.get(ATTR_HVAC_MODE)
        if legacy_mode is not None and legacy_mode != controller.mode:
            return {}

        return legacy_attrs

    async def _setup_climate_controllers(self, old_state: State | None) -> None:
        """Initialize climate controllers and subscribe to their entities."""
        for controller in self._controllers:
            attrs = self._get_restored_controller_attrs(old_state, controller)
            await controller.async_added_to_hass(self.hass, attrs)

            target_entity_ids = controller.get_target_entity_ids()
            if target_entity_ids:
                self.async_on_remove(
                    async_track_state_change_event(
                        self.hass,
                        target_entity_ids,
                        self._async_controller_target_entities_changed,
                    )
                )

            template_entity_ids = controller.get_used_template_entity_ids()
            if template_entity_ids:
                self.async_on_remove(
                    async_track_state_change_event(
                        self.hass,
                        template_entity_ids,
                        self._async_controller_template_entities_changed,
                    )
                )

    def _setup_window_controller(self) -> None:
        """Set up window entities listeners."""
        if self._window_ctrl is None:
            return

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

    async def _setup_preset_controller(self) -> None:
        """Initialize preset controller."""
        if self._preset_ctrl is not None:
            await self._preset_ctrl.async_added_to_hass(self.entity_id)

    async def _async_first_run(self):
        """Will called one time. Need on hot reload when HA core is running."""
        await self._async_control(reason=REASON_THERMOSTAT_FIRST_RUN)
        self.async_write_ha_state()

    async def _async_startup(self, *_: Any):
        """Init on startup."""
        sensor_state: State | None = self.hass.states.get(self.sensor_entity_id)
        if sensor_state and sensor_state.state not in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        ):
            await self._async_update_temp(sensor_state.state)
            self.async_write_ha_state()
        else:
            sensor_value = sensor_state.state if sensor_state else None
            _LOGGER.debug(
                "%s: skipping initial sensor update for %s because state is %s",
                self.entity_id,
                self.sensor_entity_id,
                sensor_value,
            )

        _LOGGER.info(
            "%s: thermostat ready, sensor: %s, supported HVAC modes: %s, controllers: %s",
            self.entity_id,
            self.sensor_entity_id,
            self._hvac_list,
            [controller.name for controller in self._controllers],
        )

        self.hass.create_task(self._async_first_run())

    async def _schedule_startup(self) -> None:
        """Run startup immediately or wait until Home Assistant starts."""
        if self.hass.state == CoreState.running:
            await self._async_startup()
        else:
            _LOGGER.debug(
                "%s: Home Assistant is not running yet; startup delayed until %s",
                self.entity_id,
                EVENT_HOMEASSISTANT_START,
            )
            self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_START,
                self._async_startup,
            )

    def _restore_target_temperatures(self, old_state: State) -> None:
        """Restore saved target temperatures."""
        if self._target_temp_low is None:
            old_target_low = old_state.attributes.get(ATTR_TARGET_TEMP_LOW)
            if old_target_low is not None:
                self._target_temp_low = float(old_target_low)
            else:
                self._target_temp_low = self._default_target_temp_low
                _LOGGER.debug(
                    "%s: no target low temperature found in old state, "
                    "falling back to default: %s",
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
                    "%s: no target high temperature found in old state, "
                    "falling back to default: %s",
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
                    "%s: no target temperature found in old state, "
                    "falling back to default: %s",
                    self.entity_id,
                    self._target_temp,
                )

    def _restore_hvac_mode(self, old_state: State) -> None:
        """Restore HVAC mode."""
        if not self._hvac_mode and old_state.state in self._hvac_list:
            self._hvac_mode = old_state.state
            self._set_support_flags()

    def _restore_runtime_state(self, old_state: State) -> None:
        """Restore runtime state attributes."""
        last_control_mode = old_state.attributes.get(ATTR_LAST_ASYNC_CONTROL_HVAC_MODE)
        if last_control_mode in self._hvac_list and last_control_mode != HVACMode.OFF:
            self._last_async_control_hvac_mode = last_control_mode

        last_mode = old_state.attributes.get(ATTR_LAST_ACTIVE_HVAC_MODE)
        if last_mode in self._hvac_list:
            self._last_active_hvac_mode = last_mode

    def _restore_preset_state(self, old_state: State) -> None:
        """Restore preset-related state."""
        if self._preset_ctrl is None:
            return

        saved_preset_state = old_state.attributes.get(ATTR_PRESET_NONE_SAVED_STATE)
        if saved_preset_state:
            self._saved_preset_state = self._preset_ctrl.get_saved(
                saved_preset_state.get(PRESET_NONE_HVAC_MODE),
                saved_preset_state.get(PRESET_NONE_TARGET_TEMP),
                saved_preset_state.get(PRESET_NONE_TARGET_TEMP_LOW),
                saved_preset_state.get(PRESET_NONE_TARGET_TEMP_HIGH),
            )

        old_preset_mode = old_state.attributes.get(ATTR_PRESET_MODE)
        if old_preset_mode:
            self._preset_ctrl.set_preset(old_preset_mode)

    async def _restore_state(self, old_state: State | None) -> None:
        """Restore thermostat state."""
        if old_state is None:
            self._target_temp = self._default_target_temp
            self._target_temp_low = self._default_target_temp_low
            self._target_temp_high = self._default_target_temp_high
            _LOGGER.debug(
                "%s: no previously saved temperatures, setting defaults "
                "(target: %s, target_low: %s, target_high: %s)",
                self.entity_id,
                self._target_temp,
                self._target_temp_low,
                self._target_temp_high,
            )
        else:
            self._restore_target_temperatures(old_state)
            self._restore_hvac_mode(old_state)
            self._restore_runtime_state(old_state)
            self._restore_preset_state(old_state)

        if not self._hvac_mode:
            _LOGGER.debug(
                "%s: no previously saved HVAC mode, setting default (%s)",
                self.entity_id,
                HVACMode.OFF,
            )
            self._hvac_mode = HVACMode.OFF
            self._last_active_hvac_mode = None

    async def async_added_to_hass(self):
        """Run when entity about to be added."""
        await super().async_added_to_hass()

        old_state: State | None = await self.async_get_last_state()

        self._setup_thermostat_event_listeners()
        await self._setup_climate_controllers(old_state)
        self._setup_window_controller()
        await self._setup_preset_controller()
        await self._restore_state(old_state)
        await self._schedule_startup()

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
        tracked_entities.extend(
            get_template_entities(
                self._auto_cool_delta_template,
                owner=self.entity_id,
                field=CONF_AUTO_COOL_DELTA,
                logger=_LOGGER,
            )
        )
        tracked_entities.extend(
            get_template_entities(
                self._auto_heat_delta_template,
                owner=self.entity_id,
                field=CONF_AUTO_HEAT_DELTA,
                logger=_LOGGER,
            )
        )
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
            _LOGGER.warning("%s: unsupported hvac mode: %s", self.entity_id, hvac_mode)
            return

        if hvac_mode == self._hvac_mode:
            _LOGGER.debug(
                "%s: no need to control. HVAC mode %s already set",
                self.entity_id,
                hvac_mode,
            )
            return

        if self._preset_ctrl is not None:
            _LOGGER.debug(
                "%s: HVAC mode is to be changed. Resetting preset to None",
                self.entity_id,
            )
            self._preset_ctrl.set_preset(PRESET_NONE)
            self._preset_ctrl.reset_saved()

        old_hvac_mode = self._hvac_mode
        self._toggle_target_temps(old_hvac_mode, hvac_mode)
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
                    "%s: unable to convert thermostat temp_step value to float: %s. "
                    "Return default: %s. Error: %s",
                    self.entity_id,
                    self._target_temp_step,
                    value,
                    e,
                )
            else:
                return round(value / step) * step

        return value

    def _toggle_target_temps(
        self, old_hvac_mode: HVACMode | None, new_hvac_mode: HVACMode
    ) -> None:
        """Sync non-ranged with ranged target temperatures if necessary."""
        source_hvac_mode = old_hvac_mode
        if source_hvac_mode in (None, HVACMode.OFF):
            source_hvac_mode = self._last_active_hvac_mode

        target_temp = self._target_temp
        if target_temp is None:
            target_temp = self._default_target_temp

        if (
            new_hvac_mode == HVACMode.HEAT_COOL
            and source_hvac_mode != HVACMode.HEAT_COOL
        ):
            _LOGGER.debug(
                "%s: hvac_mode changed from %s to %s: calculating ranged target temperatures",
                self.entity_id,
                source_hvac_mode,
                new_hvac_mode,
            )
            if source_hvac_mode == HVACMode.COOL:
                self._target_temp_high = target_temp
                self._target_temp_low = self._round_to_target_precision(
                    target_temp - self._auto_heat_delta
                )
            elif source_hvac_mode == HVACMode.HEAT:
                self._target_temp_low = target_temp
                self._target_temp_high = self._round_to_target_precision(
                    target_temp + self._auto_cool_delta
                )
            else:
                self._target_temp_low = self._round_to_target_precision(
                    target_temp - self._auto_heat_delta
                )
                self._target_temp_high = self._round_to_target_precision(
                    target_temp + self._auto_cool_delta
                )

        elif (
            new_hvac_mode in (HVACMode.HEAT, HVACMode.COOL, HVACMode.AUTO)
            and source_hvac_mode == HVACMode.HEAT_COOL
        ):
            _LOGGER.debug(
                "%s: hvac_mode changed from %s to %s: calculating target temperature",
                self.entity_id,
                source_hvac_mode,
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

        elif new_hvac_mode == HVACMode.AUTO and source_hvac_mode in (
            HVACMode.HEAT,
            HVACMode.COOL,
        ):
            _LOGGER.debug(
                "%s: hvac_mode changed from %s to %s: calculating auto target temperature",
                self.entity_id,
                source_hvac_mode,
                new_hvac_mode,
            )
            if source_hvac_mode == HVACMode.HEAT:
                self._target_temp = self._round_to_target_precision(
                    target_temp + self._auto_heat_delta
                )
            else:
                self._target_temp = self._round_to_target_precision(
                    target_temp - self._auto_cool_delta
                )

        elif source_hvac_mode == HVACMode.AUTO and new_hvac_mode in (
            HVACMode.HEAT,
            HVACMode.COOL,
        ):
            _LOGGER.debug(
                "%s: hvac_mode changed from %s to %s: calculating target temperature",
                self.entity_id,
                source_hvac_mode,
                new_hvac_mode,
            )
            if new_hvac_mode == HVACMode.HEAT:
                self._target_temp = self._round_to_target_precision(
                    target_temp - self._auto_heat_delta
                )
            else:
                self._target_temp = self._round_to_target_precision(
                    target_temp + self._auto_cool_delta
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
            _LOGGER.debug(
                "%s: no need to change preset: %s already set",
                self.entity_id,
                self.preset_mode,
            )
            return

        # While off, a preset is only remembered as a label and is not applied
        # to the target temperatures. It is reset to None on the next turn-on.
        if self._hvac_mode == HVACMode.OFF:
            _LOGGER.debug(
                "%s: thermostat is off, storing preset %s without applying it",
                self.entity_id,
                preset_mode,
            )
            self._preset_ctrl.set_preset(preset_mode)
            self.async_write_ha_state()
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
            _LOGGER.debug(
                "%s: preset %s settings needs to change hvac mode to %s",
                self.entity_id,
                preset_mode,
                new_hvac_mode,
            )
            old_hvac_mode = self._hvac_mode
            self._toggle_target_temps(old_hvac_mode, new_hvac_mode)
            self._hvac_mode = new_hvac_mode
            self._set_support_flags()

        if self._support_flags & ClimateEntityFeature.TARGET_TEMPERATURE:
            new_target_temp = self._preset_ctrl.get_target_temp(
                self._hvac_mode, self._target_temp
            )
            if (
                isinstance(new_target_temp, float)
                and self._target_temp != new_target_temp
            ):
                _LOGGER.debug(
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
                _LOGGER.debug(
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
                _LOGGER.debug(
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
        if new_state is None:
            _LOGGER.debug(
                "%s: target sensor state change event has no new state",
                self.entity_id,
            )
            return

        if new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            _LOGGER.debug(
                "%s: target sensor %s is %s; skipping control",
                self.entity_id,
                new_state.entity_id,
                new_state.state,
            )
            return

        old_state: State | None = event.data.get("old_state", None)
        if old_state is not None and old_state.state == new_state.state:
            _LOGGER.debug(
                "%s: target sensor not changed (%s) - no need to control",
                self.entity_id,
                new_state.state,
            )
            return

        old_state_value = old_state.state if old_state is not None else None
        _LOGGER.debug(
            "%s: target sensor changed (%s -> %s)",
            self.entity_id,
            old_state_value,
            new_state.state,
        )
        await self._async_update_temp(new_state.state)

        await self._async_control(reason=REASON_THERMOSTAT_SENSOR_CHANGED)
        self.async_write_ha_state()

    async def _async_controller_target_entities_changed(self, event) -> None:
        """Handle controller target entities changes."""
        entity_id = event.data.get("entity_id")
        old_state: State | None = event.data.get("old_state", None)
        new_state: State | None = event.data.get("new_state", None)
        old_state_value = old_state.state if old_state is not None else None
        new_state_value = new_state.state if new_state is not None else None
        _LOGGER.debug(
            "%s: controller target entity %s changed (%s -> %s); writing state",
            self.entity_id,
            entity_id,
            old_state_value,
            new_state_value,
        )
        self.async_write_ha_state()

    async def _async_template_entities_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle thermostat template entities changes."""
        new_state: State | None = event.data.get("new_state")
        entity_id = event.data.get("entity_id")

        if new_state is None:
            _LOGGER.debug(
                "%s: thermostat template entity %s event has no new state",
                self.entity_id,
                entity_id,
            )
            return

        if new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            _LOGGER.debug(
                "%s: thermostat template entity %s is %s; skipping control",
                self.entity_id,
                entity_id,
                new_state.state,
            )
            return

        old_state: State | None = event.data.get("old_state", None)
        if old_state is not None and old_state.state == new_state.state:
            _LOGGER.debug(
                "%s: thermostat template entity %s not changed (%s) - no need to control",
                self.entity_id,
                entity_id,
                new_state.state,
            )
            return

        old_state_value = old_state.state if old_state is not None else None
        _LOGGER.debug(
            "%s: thermostat template entity %s changed (%s -> %s)",
            self.entity_id,
            entity_id,
            old_state_value,
            new_state.state,
        )

        await self._async_control(reason=REASON_TEMPLATE_ENTITY_CHANGED)
        self.async_write_ha_state()

    async def _async_controller_template_entities_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle controller template entities changes."""
        new_state: State | None = event.data.get("new_state")
        entity_id = event.data.get("entity_id")

        if new_state is None:
            _LOGGER.debug(
                "%s: controller template entity %s event has no new state",
                self.entity_id,
                entity_id,
            )
            return

        if new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            _LOGGER.debug(
                "%s: controller template entity %s is %s; skipping control",
                self.entity_id,
                entity_id,
                new_state.state,
            )
            return

        old_state: State | None = event.data.get("old_state", None)
        if old_state is not None and old_state.state == new_state.state:
            _LOGGER.debug(
                "%s: controller template entity %s not changed (%s) - no need to control",
                self.entity_id,
                entity_id,
                new_state.state,
            )
            return

        old_state_value = old_state.state if old_state is not None else None
        _LOGGER.debug(
            "%s: controller template entity %s changed (%s -> %s)",
            self.entity_id,
            entity_id,
            old_state_value,
            new_state.state,
        )

        await self._async_control(reason=REASON_CONTROLLER_TEMPLATE_ENTITY_CHANGED)
        self.async_write_ha_state()

    async def _async_window_entities_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle windows entities changes."""
        new_state: State | None = event.data.get("new_state")
        entity_id = event.data.get("entity_id")

        if new_state is None:
            _LOGGER.debug(
                "%s: window entity %s event has no new state",
                self.entity_id,
                entity_id,
            )
            return

        if new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            _LOGGER.debug(
                "%s: window entity %s is %s; skipping control",
                self.entity_id,
                entity_id,
                new_state.state,
            )
            return

        old_state: State | None = event.data.get("old_state", None)
        if old_state is not None and old_state.state == new_state.state:
            _LOGGER.debug(
                "%s: window entity %s not changed (%s) - no need to control",
                self.entity_id,
                entity_id,
                new_state.state,
            )
            return

        old_state_value = old_state.state if old_state is not None else None
        _LOGGER.debug(
            "%s: window entity %s changed (%s -> %s)",
            self.entity_id,
            entity_id,
            old_state_value,
            new_state.state,
        )

        window = self._window_ctrl.find_by_entity_id(entity_id)
        if window is None:
            _LOGGER.debug(
                "%s: window entity %s is no longer configured; skipping control",
                self.entity_id,
                entity_id,
            )
            return

        window_timeout = window.timeout
        if window_timeout is not None:
            _LOGGER.debug(
                "%s: scheduling delayed control for window entity %s after %s",
                self.entity_id,
                entity_id,
                window_timeout,
            )
            self.async_on_remove(
                async_call_later(
                    self.hass,
                    window_timeout,
                    self._async_window_delayed_control,
                )
            )
        else:
            await self._async_window_delayed_control()

    async def _async_window_delayed_control(self, _now: datetime | None = None) -> None:
        _LOGGER.debug("%s: running delayed window control", self.entity_id)
        await self._async_control(reason=REASON_WINDOW_ENTITY_CHANGED)
        self.async_write_ha_state()

    async def _async_update_temp(self, temp) -> None:
        """Update thermostat with latest state from sensor."""
        if temp in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
            _LOGGER.debug(
                "%s: sensor value is %s; current temperature cleared",
                self.entity_id,
                temp,
            )
            self._cur_temp = None
            return

        try:
            temp = float(temp)
        except (TypeError, ValueError) as e:
            _LOGGER.warning("%s: unable to update from sensor: %s", self.entity_id, e)
            self._cur_temp = None
            return

        if math.isnan(temp) or math.isinf(temp):
            _LOGGER.warning("%s: sensor has illegal value %s", self.entity_id, temp)
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

    def _is_controller_allowed_in_mode(self, controller: AbstractController) -> bool:
        if controller.mode == HVACMode.COOL:
            return self._hvac_mode in (HVACMode.COOL, HVACMode.HEAT_COOL, HVACMode.AUTO)

        if controller.mode == HVACMode.HEAT:
            return self._hvac_mode in (HVACMode.HEAT, HVACMode.HEAT_COOL, HVACMode.AUTO)

        return False

    def _should_start_controller(
        self,
        controller: AbstractController,
        is_windows_opened: bool,
    ) -> bool:
        if controller.running:
            return False

        if is_windows_opened and not controller.ignore_windows:
            return False

        return self._is_controller_allowed_in_mode(controller)

    def _should_stop_controller(
        self,
        controller: AbstractController,
        is_windows_opened: bool,
    ) -> bool:
        if not controller.running:
            return False

        if is_windows_opened and not controller.ignore_windows:
            return True

        if not self._is_controller_allowed_in_mode(controller):
            return True

        return False

    async def _async_control(self, time=None, force=False, reason=None) -> None:
        """Call controllers."""
        async with self._temp_lock:
            if self._last_async_control_hvac_mode != self._hvac_mode:
                _LOGGER.debug(
                    "%s: HVAC mode changed: %s -> %s",
                    self.entity_id,
                    self._last_async_control_hvac_mode,
                    self._hvac_mode,
                )

                if self._hvac_mode != HVACMode.OFF:
                    self._last_active_hvac_mode = self._hvac_mode

            elif self._hvac_mode == HVACMode.OFF:
                # Skip control, last `OFF` was already processed
                _LOGGER.debug(
                    "%s: skipping control because HVAC mode %s is already processed",
                    self.entity_id,
                    self._hvac_mode,
                )
                return

            is_windows_opened = False
            if self._window_ctrl is not None:
                is_windows_opened = (
                    self._window_ctrl.is_opened
                    if reason == REASON_THERMOSTAT_FIRST_RUN
                    else self._window_ctrl.is_safe_opened
                )

            for controller in self._controllers:
                controller_debug_info = (
                    f"running: {controller.running}, active: {controller.is_active}"
                )

                if self._should_stop_controller(controller, is_windows_opened):
                    _LOGGER.debug(
                        "%s: stopping %s, %s",
                        self.entity_id,
                        controller.name,
                        controller_debug_info,
                    )
                    await controller.async_stop()
                    continue

                if self._should_start_controller(controller, is_windows_opened):
                    _LOGGER.debug(
                        "%s: starting %s, %s",
                        self.entity_id,
                        controller.name,
                        controller_debug_info,
                    )
                    await controller.async_start()

                await controller.async_control(time=time, force=force, reason=reason)

            self._last_async_control_hvac_mode = self._hvac_mode
