"""Support for switch+number controllers with PID."""

from datetime import timedelta
import logging
from typing import Optional

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
from homeassistant.core import DOMAIN as HA_DOMAIN, State, split_entity_id
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.template import RenderInfo, Template

from ..const import (
    REASON_KEEP_ALIVE,
    REASON_THERMOSTAT_NOT_RUNNING,
    REASON_THERMOSTAT_STOP,
)
from . import AbstractPidController

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
        keep_alive: Optional[timedelta],
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
        )
        self._output_min_template = output_min_template
        self._output_max_template = output_max_template
        self._switch_entity_id = switch_entity_id
        self._switch_inverted = switch_inverted

    def get_target_entity_ids(self) -> list[str]:
        """Add target entities to subscribe state change on them."""
        tracked_entities = super().get_target_entity_ids()
        tracked_entities.append(self._switch_entity_id)
        return tracked_entities

    def get_used_template_entity_ids(self) -> list[str]:
        """Add used template entities to track state change."""
        tracked_entities = super().get_used_template_entity_ids()

        if self._output_min_template is not None:
            try:
                template_info: RenderInfo = (
                    self._output_min_template.async_render_to_info()
                )
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "Unable to get template info: %s.\nError: %s",
                    self._output_min_template,
                    e,
                )
            else:
                tracked_entities.extend(template_info.entities)

        if self._output_max_template is not None:
            try:
                template_info: RenderInfo = (
                    self._output_max_template.async_render_to_info()
                )
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "Unable to get template info: %s.\nError: %s",
                    self._output_max_template,
                    e,
                )
            else:
                tracked_entities.extend(template_info.entities)

        return tracked_entities

    def _is_on(self):
        return self._hass.states.is_state(
            self._switch_entity_id, STATE_ON if not self._switch_inverted else STATE_OFF
        )

    def _adapt_pid_output(self, value: float) -> float:
        min_output, max_output = self._get_output_limits()
        return min_output + (value * (max_output - min_output) / 100)

    async def _async_turn_on(self, reason=None):
        _LOGGER.info(
            "%s: %s - Turning on switch %s (%s)",
            self._switch_entity_id,
            self.name,
            self._switch_entity_id,
            reason,
        )

        service = SERVICE_TURN_ON if not self._switch_inverted else SERVICE_TURN_OFF
        await self._hass.services.async_call(
            HA_DOMAIN,
            service,
            {ATTR_ENTITY_ID: self._switch_entity_id},
            context=self._context,
        )

    async def _async_turn_off(self, reason):
        _LOGGER.info(
            "%s: %s - Turning off switch %s (%s)",
            self._switch_entity_id,
            self.name,
            self._switch_entity_id,
            reason,
        )

        service = SERVICE_TURN_OFF if not self._switch_inverted else SERVICE_TURN_ON
        await self._hass.services.async_call(
            HA_DOMAIN,
            service,
            {ATTR_ENTITY_ID: self._switch_entity_id},
            context=self._context,
        )

    async def _async_stop(self):
        await super()._async_stop()
        await self._async_turn_off(REASON_THERMOSTAT_STOP)

    async def _async_ensure_not_running(self):
        if self._is_on():
            await self._async_turn_off(REASON_THERMOSTAT_NOT_RUNNING)

    def _round_to_target_precision(self, value: float) -> float:
        state: State = self._hass.states.get(self._target_entity_id)
        if not state:
            return value
        step = state.attributes.get(ATTR_STEP)
        return round(value / step) * step

    def _get_current_output(self):
        state = self._hass.states.get(self._target_entity_id)
        if state:
            return float(state.state)
        return None

    @property
    def _get_default_output_min(self) -> float | None:
        """Returns Default PID Output minimum value."""

        state: State = self._hass.states.get(self._target_entity_id)
        if state:
            return state.attributes.get(ATTR_MIN)

    @property
    def output_min(self) -> float | None:
        """Returns PID Output minimum value."""

        if self._output_min_template is None:
            _LOGGER.debug(
                "PID Output minumum not provided in config. Returning number entity min"
            )
            return self._get_default_output_min

        try:
            output_min = self._output_min_template.async_render(parse_result=False)
        except (TemplateError, TypeError) as e:
            _LOGGER.warning(
                "Unable to render template value: %s. Error: %s. Returning number entity min",
                self._output_min_template,
                e,
            )
            return self._get_default_output_min

        try:
            output_min = float(output_min)
        except ValueError as e:
            _LOGGER.warning(
                "Can't parse float value: %s. Error: %s. Returning number entity min",
                output_min,
                e,
            )
            return self._get_default_output_min

        return max(output_min, self._get_default_output_min)

    @property
    def _get_default_output_max(self) -> float | None:
        """Returns Default PID Output maximum value."""

        state: State = self._hass.states.get(self._target_entity_id)
        if state:
            return state.attributes.get(ATTR_MAX)

    @property
    def output_max(self) -> float | None:
        """Returns PID Output maximum value."""

        if self._output_max_template is None:
            _LOGGER.debug(
                "PID Output maximum not provided in config. Returning number entity max"
            )
            return self._get_default_output_max

        try:
            output_max = self._output_max_template.async_render(parse_result=False)
        except (TemplateError, TypeError) as e:
            _LOGGER.warning(
                "Unable to render template value: %s. Error: %s. Returning number entity max",
                self._output_max_template,
                e,
            )
            return self._get_default_output_max

        try:
            output_max = float(output_max)
        except ValueError as e:
            _LOGGER.warning(
                "Can't parse float value: %s. Error: %s. Returning number entity max",
                output_max,
                e,
            )
            return self._get_default_output_max

        return min(output_max, self._get_default_output_max)

    def _get_output_limits(self) -> tuple[None, None]:
        if self.mode == HVACMode.COOL:
            return self.output_max, self.output_min
        return self.output_min, self.output_max

    async def _apply_output(self, output: float):
        domain = split_entity_id(self._target_entity_id)[0]

        await self._hass.services.async_call(
            domain,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: self._target_entity_id, ATTR_VALUE: output},
            context=self._context,
        )

    async def _async_control(
        self,
        cur_temp,
        target_temp,
        target_temp_low,
        target_temp_high,
        time=None,
        force=False,
        reason=None,
    ):
        if not self._is_on() or reason == REASON_KEEP_ALIVE:
            await self._async_turn_on(reason=reason)
        await super()._async_control(
            cur_temp,
            target_temp,
            target_temp_low,
            target_temp_high,
            time,
            force,
            reason,
        )
