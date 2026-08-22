from pca import get_pca

class LEDControl:
    def __init__(self, channel, min_brightness=0, max_brightness=100, pca=None):
        """
        Initializes an LED controlled by the shared PCA9685.

        :param channel: The channel number where the LED is connected.
        :param min_brightness: Minimum brightness level (default: 0).
        :param max_brightness: Maximum brightness level (default: 100).
        :param pca: Shared PCA9685 instance (default: process-wide singleton).
        """
        self.pca = pca if pca is not None else get_pca()
        self.led = self.pca.channels[channel]
        self.min_brightness = min_brightness
        self.max_brightness = max_brightness
        
    def set_brightness(self, brightness):
        """
        Set the brightness of the LED.

        :param brightness: The brightness level (0 to 100).
        """
        if self.min_brightness <= brightness <= self.max_brightness:
            # Convert brightness percentage to a PWM value
            pwm_value = brightness / 100 * 65535
            self.led.duty_cycle = int(pwm_value)
        else:
            raise ValueError(f"Brightness must be between {self.min_brightness} and {self.max_brightness}")

    def on(self):
         self.led.duty_cycle = 65535

    def off(self):
        """
        Turns the LED off.
        """
        self.led.duty_cycle = 0

    def close(self):
         self.led.duty_cycle = 0