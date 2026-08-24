# -*- coding: utf-8 -*-
"""
Two-servo neck: a left and right MG995 mounted on the shoulder blades,
driving the head by acting on the back of it.

    both servos the same way  -> pitch (chin up / down)
    servos opposite ways      -> yaw (head left / right)

Neck holds no hardware. It translates a (yaw, pitch) pose into angles
for the two underlying servo parts and hands them to the rig's worker
queue, like every other part. The mount direction is only knowable on
the real rig, so the signs and travel deltas come from the [NECK]
config section and are flipped during the first live sweep.

    [NECK]
    left_part = neck_l
    right_part = neck_r
    base = 90        # both servos at neutral head pose
    yaw_delta = 40   # per-servo angle for full yaw
    pitch_delta = 30 # per-servo angle for full pitch
    yaw_sign_l = 1
    yaw_sign_r = -1
    pitch_sign = 1
"""
import logging

log = logging.getLogger("chatterpi.neck")

POSES = {
    'center': (0.0, 0.0),
    'left': (-1.0, 0.0),
    'right': (1.0, 0.0),
    'up': (0.0, 1.0),
    'down': (0.0, -1.0),
}


class Neck:
    def __init__(self, rig, spec):
        self.rig = rig
        self.left_part = spec['left_part']
        self.right_part = spec['right_part']
        self.base = spec['base']
        self.yaw_delta = spec['yaw_delta']
        self.pitch_delta = spec['pitch_delta']
        self.yaw_sign_l = spec['yaw_sign_l']
        self.yaw_sign_r = spec['yaw_sign_r']
        self.pitch_sign = spec['pitch_sign']
        log.info("neck ready: %s/%s base=%s yaw_delta=%s pitch_delta=%s signs l=%s r=%s pitch=%s",
                 self.left_part, self.right_part, self.base,
                 self.yaw_delta, self.pitch_delta,
                 self.yaw_sign_l, self.yaw_sign_r, self.pitch_sign)

    def pose(self, yaw, pitch):
        """Map a pose to (left angle, right angle).

        yaw:   -1 (full left) .. +1 (full right)
        pitch: -1 (full down) .. +1 (full up)
        Values are clamped to [-1, 1].
        """
        yaw = max(-1.0, min(1.0, yaw))
        pitch = max(-1.0, min(1.0, pitch))
        left = (self.base
                + self.pitch_delta * self.pitch_sign * pitch
                + self.yaw_delta * self.yaw_sign_l * yaw)
        right = (self.base
                 + self.pitch_delta * self.pitch_sign * pitch
                 + self.yaw_delta * self.yaw_sign_r * yaw)
        return left, right

    def look(self, yaw=0.0, pitch=0.0, ms=400):
        """Turn the head toward (yaw, pitch) over ms milliseconds.
        ms <= 0 writes immediately (still subject to part smoothing)."""
        left, right = self.pose(yaw, pitch)
        if ms <= 0:
            self.rig.set(self.left_part, left)
            self.rig.set(self.right_part, right)
        else:
            self.rig.move(self.left_part, left, ms)
            self.rig.move(self.right_part, right, ms)

    def look_preset(self, pose, ms=400):
        """Named pose: center / left / right / up / down."""
        if pose not in POSES:
            raise ValueError(f"unknown neck pose {pose!r} "
                             f"(want one of {sorted(POSES)})")
        yaw, pitch = POSES[pose]
        self.look(yaw, pitch, ms)

    def center(self, ms=400):
        self.look(0.0, 0.0, ms)