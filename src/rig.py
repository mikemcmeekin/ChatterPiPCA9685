# -*- coding: utf-8 -*-
"""
SkeletonRig: the single owner of all hardware for one skeleton.

Parts (servos and LEDs) are declared in config.ini as [PART <name>]
sections, so each skeleton describes its own equipment. All I2C writes
go through one ServoWorker thread - no other code may touch the PCA9685.
"""
import logging

import config as c
from pca import get_pca
from servo import StandardServo
from led import LEDControl
from servoWorker import ServoWorker

log = logging.getLogger("chatterpi.rig")


class PartDevice:
    """Adapts a servo or LED to the worker's set_value/disable protocol."""

    def __init__(self, kind, device, min_v, max_v, rest):
        self.kind = kind
        self.device = device
        self.min_v = min_v
        self.max_v = max_v
        self.rest = rest

    def set_value(self, value):
        value = min(max(value, self.min_v), self.max_v)
        if self.kind == 'servo':
            self.device.set_angle(value)
        else:
            self.device.set_brightness(value)

    def disable(self):
        if self.kind == 'servo':
            self.device.disable()
        else:
            self.device.close()


class SkeletonRig:
    def __init__(self):
        c.update()
        self.pca = get_pca()
        self.worker = ServoWorker()
        self.parts = {}
        for name, spec in c.PARTS.items():
            if not spec.get('enabled', True):
                log.info("part %s is disabled in config, skipping", name)
                continue
            if spec['type'] == 'servo':
                device = StandardServo(channel=spec['channel'],
                                       min_angle=spec['min_angle'],
                                       max_angle=spec['max_angle'],
                                       min_pulse_width=spec['pulse_min'],
                                       max_pulse_width=spec['pulse_max'],
                                       pca=self.pca)
                self.parts[name] = PartDevice('servo', device,
                                              spec['min_angle'], spec['max_angle'],
                                              spec['rest'])
            else:
                device = LEDControl(channel=spec['channel'],
                                    min_brightness=spec['min_brightness'],
                                    max_brightness=spec['max_brightness'],
                                    pca=self.pca)
                self.parts[name] = PartDevice('led', device,
                                              spec['min_brightness'], spec['max_brightness'],
                                              spec['rest'])
            self.worker.add_part(name, self.parts[name], self.parts[name].rest,
                                 spec.get('smoothing_ms', 0))
            # servo constructors park at min_angle; queue the configured rest value
            self.worker.set(name, self.parts[name].rest)
        if c.JAW_PART not in self.parts:
            raise ValueError(f"jaw part {c.JAW_PART!r} not defined in config parts {list(self.parts)}")

    def set(self, name, value):
        """Immediately drive part to value (no-op if part is unknown/disabled)."""
        if name in self.parts:
            self.worker.set(name, value)

    def move(self, name, value, ms):
        """Drive part to value over ms milliseconds (no-op if unknown/disabled)."""
        if name in self.parts:
            self.worker.move(name, value, ms)

    def rest_all(self):
        for name, part in self.parts.items():
            self.worker.set(name, part.rest)

    def close(self):
        self.worker.stop(disable=True)