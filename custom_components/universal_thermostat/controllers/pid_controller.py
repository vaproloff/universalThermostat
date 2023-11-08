"""
PID Controller.
"""
import time
import logging

from ..const import DEFAULT_PID_MIN, DEFAULT_PID_MAX

_LOGGER = logging.getLogger(__name__)


class PIDController:
    """PID Controller"""

    def __init__(
        self,
        kp=0.0,
        ki=0.0,
        kd=0.0,
        sample_time=None,
        output_limits=(DEFAULT_PID_MIN, DEFAULT_PID_MAX),
    ) -> None:
        self._set_point = 0
        self._output = 0.0

        self._kp = kp
        self._ki = ki
        self._kd = kd

        self._sample_time = sample_time

        self._output_limits = output_limits

        self._p_term = 0.0
        self._i_term = 0.0
        self._d_term = 0.0

        self._last_output = None
        self._last_input = None
        self._last_time = None

    def update(self, feedback_value, in_time=None):
        """Calculates PID value for given reference feedback"""

        current_time = in_time if in_time is not None else self.current_time()
        if self._last_time is None:
            self._last_time = current_time

        # Fill PID information
        delta_time = current_time - self._last_time
        if not delta_time:
            delta_time = 1e-16
        elif delta_time < 0:
            return

        # Return last output if sample time not met
        if (
            self._sample_time is not None
            and self._last_output is not None
            and delta_time < self._sample_time
        ):
            return self._last_output

        # Calculate error
        error = self._set_point - feedback_value
        last_error = self._set_point - (
            self._last_input if self._last_input is not None else self._set_point
        )

        # Calculate delta error
        delta_error = error - last_error

        # Calculate P
        self._p_term = self._kp * error

        # Calculate I
        self._i_term += self._ki * error * delta_time
        self._i_term = self.clamp_value(self._i_term, self._output_limits)

        # Calculate D
        self._d_term = self._kd * delta_error / delta_time

        # Compute final output
        self._output = self._p_term + self._i_term + self._d_term
        self._output = self.clamp_value(self._output, self._output_limits)

        # Keep Track
        self._last_output = self._output
        self._last_input = feedback_value
        self._last_time = current_time

        return self._output

    @property
    def kp(self):
        """Aggressively the PID reacts to the current error with setting Proportional Gain"""
        return self._kp

    @kp.setter
    def kp(self, value):
        self._kp = value

    @property
    def ki(self):
        """Aggressively the PID reacts to the current error with setting Integral Gain"""
        return self._ki

    @ki.setter
    def ki(self, value):
        self._ki = value

    @property
    def kd(self):
        """Determines how aggressively the PID reacts to the current
        error with setting Derivative Gain"""
        return self._kd

    @kd.setter
    def kd(self, value):
        self._kd = value

    @property
    def set_point(self):
        """The target point to the PID"""
        return self._set_point

    @set_point.setter
    def set_point(self, value):
        self._set_point = value

    @property
    def sample_time(self):
        """PID that should be updated at a regular interval.
        Based on a pre-determined sampe time, the PID decides if it should compute or
        return immediately.
        """
        return self._sample_time

    @sample_time.setter
    def sample_time(self, value):
        self._sample_time = value

    @property
    def p(self):
        return self._p_term

    @property
    def i(self):
        return self._i_term

    @property
    def d(self):
        return self._d_term

    def reset(self):
        self._p_term = 0
        self._i_term = 0
        self._d_term = 0

        self._last_output = None
        self._last_input = None
        self._last_time = None

    @property
    def output(self):
        """PID result"""
        return self._output

    def current_time(self):
        try:
            ret_time = time.monotonic()
        except AttributeError:
            ret_time = time.time()

        return ret_time

    def clamp_value(self, value, limits):
        lower, upper = limits

        if value is None:
            return None
        return max(min(value, upper), lower)
