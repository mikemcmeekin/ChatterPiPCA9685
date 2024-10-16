from adafruit_servokit import ServoKit

class StandardServo:
    def __init__(self, channel, min_angle=0, 
                    max_angle=140, initial_angle=None, min_pulse_width=500, max_pulse_width=2500):
        """
        Initializes a single servo on a specified channel.

        :param channel: The channel number where the servo is connected.
        :param min_pulse: Minimum pulse width in microseconds (default: 500).
        :param max_pulse: Maximum pulse width in microseconds (default: 2500).
        """
        self.kit = ServoKit(channels=16)
        self.servo = self.kit.servo[channel]
        self.servo.set_pulse_width_range(min_pulse_width, max_pulse_width)
        self.min_angle = min_angle
        self.max_angle = max_angle
        self.initial_angle = initial_angle
        self.set_angle(min_angle)

    def set_angle(self, angle):
        """
        Set the angle of the servo.

        :param angle: The angle to set the servo to (0 to 180 degrees).
        """
        if 0 <= angle <= 180:
            self.servo.angle = angle
        else:
            raise ValueError("Angle must be between 0 and 180 degrees")
            print("Angle value was " & angle)

    def disable(self):
        """
        Disable the servo (by setting its angle to None).
        """
        self.servo.angle = None

    def close(self):
         self.servo.angle = None