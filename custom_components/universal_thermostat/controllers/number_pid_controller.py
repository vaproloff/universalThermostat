"""Support for switch+number controllers with PID."""

from collections.abc import Mapping
from datetime import timedelta
import logging
from typing import Any

from custom_components.universal_thermostat.const import (
    CONF_PID_MAX,
    CONF_PID_MIN,
    REASON_KEEP_ALIVE,
    REASON_THERMOSTAT_NOT_RUNNING,
    REASON_THERMOSTAT_STOP,
)
from custom_components.universal_thermostat.template_utils import (
    get_template_entities,
    render_float,
)

from homeassistant.components.climate import HVACMode
from homeassistant.components.input_number import (
    ATTR_MAX,
    ATTR_MIN,
    ATTR_STEP,
    ATTR_VALUE,
    SERVICE_SET_VALUE,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN, State, split_entity_id
from homeassistant.helpers.template import Template

from .abstract_pid_controller import AbstractPidController

_LOGGER = logging.getLogger(__name__)


class NumberPidController(AbstractPidController):
    """PID Number + Switch controller class."""

    def __init__(
        self,
        name: str,
        mode,
        target_entity_id: str,
        pid_kp_template: Template,
        pid_ki_template: Template,
        pid_kd_template: Template,
        pid_sample_period: timedelta,
        inverted: bool,
        keep_alive: timedelta | None,
        ignore_windows: bool,
        output_min_template: Template,
        output_max_template: Template,
        switch_entity_id: str,
        switch_inverted: bool,
    ) -> None:
        """Initialize the controller."""
        super().__init__(
            name,
            mode,
            target_entity_id,
            pid_kp_template,
            pid_ki_template,
            pid_kd_template,
            pid_sample_period,
            inverted,
            keep_alive,
            ignore_windows,
        )
        self._min_output_template = output_min_template
        self._max_output_template = output_max_template
        self._switch_entity_id = switch_entity_id
        self._switch_inverted = switch_inverted

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return controller's extra attributes for thermostat entity."""
        attrs = super().extra_state_attributes or {}
        attrs.update(
            {
                CONF_PID_MAX: self._max_output,
                CONF_PID_MIN: self._min_output,
            }
        )

        return attrs

    @property
    def _min_output(self) -> float | None:
        """Returns PID Output minimum value."""
        min_output = render_float(
            self._min_output_template,
            self._default_min_output,
        )

        return max(min_output, self._default_min_output)

    @property
    def _default_min_output(self) -> float | None:
        """Returns Default PID Output minimum value."""
        state: State | None = self._hass.states.get(self._target_entity_id)
        if state:
            try:
                return float(state.attributes.get(ATTR_MIN))
            except ValueError as e:
                _LOGGER.warning(
                    "%s - %s: unable to convert target entity minimum value to float: %s. Error: %s",
                    self._thermostat.entity_id,
                    self.name,
                    state.attributes.get(ATTR_MIN),
                    e,
                )

        _LOGGER.warning(
            "%s - %s: unable to get target entity minimum. Return default: %s",
            self._thermostat.entity_id,
            self.name,
            self._thermostat.min_temp,
        )
        return self._thermostat.min_temp

    @property
    def _max_output(self) -> float | None:
        max_output = render_float(
            self._max_output_template,
            self._default_max_output,
        )

        return min(max_output, self._default_max_output)

    @property
    def _default_max_output(self) -> float | None:
        """Returns Default PID Output maximum value."""
        state: State | None = self._hass.states.get(self._target_entity_id)
        if state:
            try:
                return float(state.attributes.get(ATTR_MAX))
            except ValueError as e:
                _LOGGER.warning(
                    "%s - %s: unable to convert target entity maximum value to float: %s. Error: %s",
                    self._thermostat.entity_id,
                    self.name,
                    state.attributes.get(ATTR_MAX),
                    e,
                )

        _LOGGER.warning(
            "%s - %s: unable to get target entity maximum. Return default: %s",
            self._thermostat.entity_id,
            self.name,
            self._thermostat.max_temp,
        )
        return self._thermostat.max_temp

    @property
    def _is_on(self) -> bool:
        if self._switch_entity_id is None:
            return self.__running
        return self._hass.states.is_state(
            self._switch_entity_id, STATE_ON if not self._switch_inverted else STATE_OFF
        )

    def get_target_entity_ids(self) -> list[str]:
        """Add target entities to subscribe state change on them."""
        tracked_entities = super().get_target_entity_ids()
        if self._switch_entity_id is not None:
            tracked_entities.append(self._switch_entity_id)
        return tracked_entities

    def get_used_template_entity_ids(self) -> list[str]:
        """Add used template entities to track state change."""
        tracked_entities = super().get_used_template_entity_ids()
        tracked_entities.extend(get_template_entities(self._min_output_template))
        tracked_entities.extend(get_template_entities(self._max_output_template))
        return tracked_entities

    def _adapt_pid_output(self, value: float) -> float:
        min_output, max_output = self._get_output_limits()
        return min_output + (value * (max_output - min_output) / 100)

    def _round_to_target_precision(self, value: float) -> float:
        state: State | None = self._hass.states.get(self._target_entity_id)
        if state:
            step = state.attributes.get(ATTR_STEP)
            if step:
                try:
                    step = float(step)
                except ValueError as e:
                    _LOGGER.warning(
                        "%s - %s: unable to convert number step value to float: %s. Return default: %s. Error: %s",
                        self._thermostat.entity_id,
                        self.name,
                        step,
                        value,
                        e,
                    )
                else:
                    return round(value / step) * step

        return value

    def _get_current_output(self):
        state = self._hass.states.get(self._target_entity_id)
        if state:
            try:
                return float(state.state)
            except ValueError as e:
                _LOGGER.warning(
                    "%s - %s: unable to convert number value to float: %s. Error: %s",
                    self._thermostat.entity_id,
                    self.name,
                    state.state,
                    e,
                )
        return None

    async def _async_turn_on(self, reason=None):
        if self._switch_entity_id is None:
            return

        _LOGGER.debug(
            "%s - %s: turning on %s (%s)",
            self._thermostat.entity_id,
            self.name,
            self._switch_entity_id,
            reason,
        )

        service = SERVICE_TURN_ON if not self._switch_inverted else SERVICE_TURN_OFF
        service_data = {ATTR_ENTITY_ID: self._switch_entity_id}
        await self._hass.services.async_call(
            domain=HOMEASSISTANT_DOMAIN,
            service=service,
            service_data=service_data,
            blocking=True,
            context=self._context,
        )

    async def _async_turn_off(self, reason):
        if self._switch_entity_id is None:
            return

        _LOGGER.debug(
            "%s - %s: turning off %s (%s)",
            self._thermostat.entity_id,
            self.name,
            self._switch_entity_id,
            reason,
        )

        service = SERVICE_TURN_OFF if not self._inverted else SERVICE_TURN_ON
        service_data = {ATTR_ENTITY_ID: self._switch_entity_id}
        await self._hass.services.async_call(
            domain=HOMEASSISTANT_DOMAIN,
            service=service,
            service_data=service_data,
            blocking=True,
            context=self._context,
        )

    async def _async_stop(self):
        await super()._async_stop()
        await self._async_turn_off(REASON_THERMOSTAT_STOP)

    async def _async_ensure_not_running(self):
        if self._is_on:
            await self._async_turn_off(REASON_THERMOSTAT_NOT_RUNNING)

    def _get_output_limits(self) -> tuple[float, float]:
        if self.mode == HVACMode.COOL:
            return self._max_output, self._min_output
        return self._min_output, self._max_output

    async def _apply_output(self, output: float):
        domain = split_entity_id(self._target_entity_id)[0]
        service_data = {ATTR_ENTITY_ID: self._target_entity_id, ATTR_VALUE: output}
        await self._hass.services.async_call(
            domain=domain,
            service=SERVICE_SET_VALUE,
            service_data=service_data,
            context=self._context,
        )

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

        if not self._is_on or reason == REASON_KEEP_ALIVE:
            await self._async_turn_on(reason=reason)
