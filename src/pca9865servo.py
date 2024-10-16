import time
from servo import StandardServo

servo = StandardServo(channel=1)
servo.set_angle(90)
time.sleep(1)
servo.set_angle(180)
time.sleep(1)
servo.set_angle(0)