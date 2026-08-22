# -*- coding: utf-8 -*-
"""
Single shared PCA9685 driver.

All servo and LED code must use get_pca() instead of opening its own
PCA9685, so the chip is initialized exactly once and every component
agrees on the PWM frequency.
"""
import board
from adafruit_pca9685 import PCA9685

_pca = None

def get_pca(frequency=60):
    global _pca
    if _pca is None:
        _pca = PCA9685(board.I2C())
        _pca.frequency = frequency
    return _pca