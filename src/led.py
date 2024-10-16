from adafruit_servokit import ServoKit
import board
import busio
from adafruit_pca9685 import PCA9685

class LEDControl:
    def __init__(self, channel, min_brightness=0, max_brightness=1):
        """
        Initializes an LED controlled by the ServoKit.

        :param channel: The channel number where the LED is connected.
        :param min_brightness: The minimum brightness level (default: 0).
        :param max_brightness: The maximum brightness level (default: 100).
        """
        self.i2c = board.I2C() # uses board.SCL and board.SDA
        self.pca = PCA9685(self.i2c)
        self.pca.frequency = 60
        self.led =  self.pca.channels[channel]
        #self.kit = ServoKit(channels=16)
        #self.led = self.kit.continuous_servo[channel]
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
            self.led.duty_cycle = pwm_value
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