from pca import get_pca

class StandardServo:
    def __init__(self, channel=0, min_angle=0,
                 max_angle=140, initial_angle=None, min_pulse_width=500, max_pulse_width=2500,
                 pca=None):
        """
        Initializes a single servo on a specified channel.

        :param channel: The channel number where the servo is connected.
        :param min_pulse: Minimum pulse width in microseconds (default: 500).
        :param max_pulse: Maximum pulse width in microseconds (default: 2500).
        :param pca: Shared PCA9685 instance (default: process-wide singleton).
        """
        self.pca = pca if pca is not None else get_pca()
        self.channel = self.pca.channels[channel]
        self.min_angle = min_angle
        self.max_angle = max_angle
        self.min_pulse = min_pulse_width
        self.max_pulse = max_pulse_width
        self._period = 1000000.0 / self.pca.frequency
        self.set_angle(min_angle)

    def set_angle(self, angle):
        """
        Set the angle of the servo (0 to 180 degrees).
        Maps the angle onto the configured min/max pulse widths, exactly
        like the previous ServoKit-based implementation.
        """
        if angle <= self.min_angle:
            angle = self.min_angle
        elif angle >= self.max_angle:
            angle = self.max_angle
        pulse = self.min_pulse + (angle / 180.0) * (self.max_pulse - self.min_pulse)
        self.channel.duty_cycle = int(pulse / self._period * 65535)
        return angle

    def disable(self):
        """
        Disable the servo (no PWM output).
        """
        self.channel.duty_cycle = 0

    def close(self):
        self.channel.duty_cycle = 0