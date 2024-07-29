"""Support for climate switch controllers."""

from datetime import timedelta
import logging

from homeassistant.components.climate import (
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_TARGET_TEMP_STEP,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE, SERVICE_TURN_OFF
from homeassistant.core import State
from homeassistant.exceptions import TemplateError
from homeassistant.helpers import condition
from homeassistant.helpers.template import RenderInfo, Template

from ..const import DEFAULT_CLIMATE_TEMP_DELTA
from . import SwitchController

_LOGGER = logging.getLogger(__name__)


class ClimateSwitchController(SwitchController):
    """Climate switch controller class."""

    def __init__(
        self,
        name: str,
        mode,
        target_entity_id: str,
        cold_tolerance_template: Template,
        hot_tolerance_template: Template,
        temp_delta_template: Template | None,
        inverted: bool,
        keep_alive: timedelta | None,
        min_cycle_duration,
    ) -> None:
        """Initialize the controller."""
        super().__init__(
            name,
            mode,
            target_entity_id,
            cold_tolerance_template,
            hot_tolerance_template,
            inverted,
            keep_alive,
            min_cycle_duration,
        )
        self._temp_delta_template = temp_delta_template

    @property
    def temp_delta(self) -> float | None:
        """Returns Temperature Delta."""
        if self._temp_delta_template is None:
            _LOGGER.warning(
                "%s - %s: temp_delta template is none. Return default: %s",
                self._thermostat_entity_id,
                self.name,
                DEFAULT_CLIMATE_TEMP_DELTA,
            )
            return float(DEFAULT_CLIMATE_TEMP_DELTA)

        try:
            temp_delta = self._temp_delta_template.async_render(parse_result=False)
        except (TemplateError, TypeError) as e:
            _LOGGER.warning(
                "%s - %s: unable to render temp_delta template: %s. Return default: %s. Error: %s",
                self._thermostat_entity_id,
                self.name,
                self._temp_delta_template,
                DEFAULT_CLIMATE_TEMP_DELTA,
                e,
            )
            return float(DEFAULT_CLIMATE_TEMP_DELTA)

        try:
            return float(temp_delta)
        except ValueError as e:
            _LOGGER.warning(
                "%s - %s: unable to convert temp_delta template value to float: %s. Return default: %s. Error: %s",
                self._thermostat_entity_id,
                self.name,
                self._temp_delta_template,
                DEFAULT_CLIMATE_TEMP_DELTA,
                e,
            )
            return float(DEFAULT_CLIMATE_TEMP_DELTA)

    @property
    def _is_on(self) -> bool:
        if not self._inverted:
            return self._hass.states.is_state(self._target_entity_id, self._mode)
        if self._mode == HVACMode.COOL:
            return self._hass.states.is_state(self._target_entity_id, HVACMode.HEAT)
        if self._mode == HVACMode.HEAT:
            return self._hass.states.is_state(self._target_entity_id, HVACMode.COOL)

    @property
    def is_active(self) -> bool:
        """Is controller entity HVAC active."""
        state: State | None = self._hass.states.get(self._target_entity_id)
        if state is not None:
            hvac_action = state.attributes.get(ATTR_HVAC_ACTION)
            if hvac_action is not None:
                return (
                    hvac_action == HVACAction.COOLING
                    if self._mode
                    == (HVACMode.COOL if not self._inverted else HVACMode.HEAT)
                    else hvac_action == HVACAction.HEATING
                )

        return super().is_active

    @property
    def _target_entity_min_temp(self) -> float:
        """Return target entity minimum temperature."""
        state: State = self._hass.states.get(self._target_entity_id)
        if state:
            return state.attributes.get(ATTR_MIN_TEMP)

    @property
    def _target_entity_max_temp(self) -> float:
        """Return target entity maximum temperature."""
        state: State = self._hass.states.get(self._target_entity_id)
        if state:
            return state.attributes.get(ATTR_MAX_TEMP)

    def get_used_template_entity_ids(self) -> list[str]:
        """Add used template entities to track state change."""
        tracked_entities = super().get_used_template_entity_ids()

        if self._temp_delta_template is not None:
            try:
                template_info: RenderInfo = (
                    self._temp_delta_template.async_render_to_info()
                )
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "%s - %s: unable to get temp_delta template info: %s. Error: %s",
                    self._thermostat_entity_id,
                    self.name,
                    self._temp_delta_template,
                    e,
                )
            else:
                tracked_entities.extend(template_info.entities)

        return tracked_entities

    async def _async_turn_on(self, reason):
        _LOGGER.debug(
            "%s - %s: turning on %s (%s)",
            self._thermostat_entity_id,
            self.name,
            self._target_entity_id,
            reason,
        )

        await self._async_set_temperature(
            target_temp=self._thermostat.get_ctrl_target_temperature(self.mode),
            reason=reason,
        )

        if (
            self._mode == HVACMode.COOL
            and not self._inverted
            or self._mode == HVACMode.HEAT
            and self._inverted
        ):
            hvac_mode = HVACMode.COOL
        else:
            hvac_mode = HVACMode.HEAT

        service_data = {
            ATTR_ENTITY_ID: self._target_entity_id,
            ATTR_HVAC_MODE: hvac_mode,
        }
        await self._hass.services.async_call(
            domain=CLIMATE_DOMAIN,
            service=SERVICE_SET_HVAC_MODE,
            service_data=service_data,
            blocking=True,
            context=self._context,
        )

    async def _async_turn_off(self, reason):
        _LOGGER.debug(
            "%s - %s: turning off %s (%s)",
            self._thermostat_entity_id,
            self.name,
            self._target_entity_id,
            reason,
        )

        service_data = {ATTR_ENTITY_ID: self._target_entity_id}
        await self._hass.services.async_call(
            domain=CLIMATE_DOMAIN,
            service=SERVICE_TURN_OFF,
            service_data=service_data,
            blocking=True,
            context=self._context,
        )

    def _round_to_target_precision(self, value: float) -> float:
        state: State | None = self._hass.states.get(self._target_entity_id)
        if state:
            step = state.attributes.get(ATTR_TARGET_TEMP_STEP)
            if step:
                try:
                    step = float(step)
                except ValueError as e:
                    _LOGGER.warning(
                        "%s - %s: unable to convert climate temp_step value to float: %s. Return default: %s. Error: %s",
                        self._thermostat_entity_id,
                        self.name,
                        step,
                        value,
                        e,
                    )
                else:
                    return round(value / step) * step

        return value

    async def _async_control(
        self,
        cur_temp,
        target_temp,
        time=None,
        force=False,
        reason=None,
    ):
        await super()._async_control(
            cur_temp,
            target_temp,
            time,
            force,
            reason,
        )

        if self._is_on:
            await self._async_set_temperature(target_temp=target_temp, reason=reason)

    async def _async_set_temperature(self, target_temp: float, reason):
        if self.mode == HVACMode.COOL:
            target_temp -= self.temp_delta
        else:
            target_temp += self.temp_delta

        if None not in (self._target_entity_min_temp, self._target_entity_max_temp):
            target_temp = min(
                max(target_temp, self._target_entity_min_temp),
                self._target_entity_max_temp,
            )

        target_temp = self._round_to_target_precision(target_temp)

        if condition.state(
            self._hass,
            entity=self._target_entity_id,
            attribute=ATTR_TEMPERATURE,
            req_state=target_temp,
        ):
            _LOGGER.debug(
                "%s - %s: no need to change target_temp for %s - %s already set",
                self._thermostat_entity_id,
                self.name,
                self._target_entity_id,
                target_temp,
            )
            return

        _LOGGER.debug(
            "%s - %s: changing target_temp for %s to %s (%s)",
            self._thermostat_entity_id,
            self.name,
            target_temp,
            self._target_entity_id,
            reason,
        )

        service_data = {
            ATTR_ENTITY_ID: self._target_entity_id,
            ATTR_TEMPERATURE: target_temp,
        }
        await self._hass.services.async_call(
            domain=CLIMATE_DOMAIN,
            service=SERVICE_SET_TEMPERATURE,
            service_data=service_data,
            context=self._context,
        )
