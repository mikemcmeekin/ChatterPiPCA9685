# -*- coding: utf-8 -*-
"""
Single worker thread for all PCA9685 I2C writes.

Callers (audio callback, script scheduler, Viam service) never touch I2C:
they push commands into a queue, and this thread applies them. Commands
are drained in order, latest command per part wins, so a slow write can
never build a backlog that stalls audio playback.

Two command types per part:
  set  - write the value immediately; on a smoothed part (smoothing_ms > 0)
         it eases in/out over the smoothing window instead
  move - interpolate from the part's current value to the target over ms
         (re-targeting mid-move restarts the move from the current value;
         smoothed parts follow an ease-in-out curve, others stay linear)
"""
import time
import queue
from threading import Thread

class MovementProfile:
    """How a part moves between values.

    LINEAR - constant velocity (original behaviour).
    SMOOTH - eased (smoothed servo): slow start, fast middle, slow
             finish. Every set/move of the part eases over smoothing_ms.
    """
    LINEAR = 0
    SMOOTH = 1

    def __init__(self, style, smoothing_ms=0):
        self.style = style
        self.smoothing_ms = int(smoothing_ms)

    @classmethod
    def from_config(cls, smoothing_ms):
        """Build a profile from a part's smoothing_ms config value."""
        if int(smoothing_ms) > 0:
            return cls(cls.SMOOTH, smoothing_ms)
        return cls(cls.LINEAR, 0)

    def ease(self, p):
        """Map linear progress p (0..1) to eased progress (0..1)."""
        if self.style == MovementProfile.SMOOTH:
            return p * p * (3.0 - 2.0 * p)  # smoothstep
        return p


class ServoWorker:
    def __init__(self, tick=0.002):
        self.tick = tick
        self.q = queue.Queue()
        self._stopped = False
        self._parts = {}     # name -> PartDevice
        self._current = {}   # name -> last value written
        self._active = {}    # name -> (from, to, start_monotonic, dur_s)
        self._profile = {}   # name -> MovementProfile
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()

    def add_part(self, name, part, initial, smoothing_ms=0):
        self._parts[name] = part
        self._current[name] = initial
        self._profile[name] = MovementProfile.from_config(smoothing_ms)

    def set(self, name, value):
        """Write value immediately (non-blocking)."""
        self.q.put(('set', name, value))

    def move(self, name, value, ms):
        """Move to value over ms milliseconds (non-blocking). ms<=0 = immediate."""
        self.q.put(('move', name, value, ms))

    def stop(self, disable=False):
        if self._stopped:
            return
        self._stopped = True
        self._thread.join(timeout=5)
        if disable:
            for part in self._parts.values():
                part.disable()

    # ---- internal ----

    def _run(self):
        while not self._stopped:
            pending = []
            try:
                pending.append(self.q.get(timeout=self.tick))
            except queue.Empty:
                pass
            else:
                while True:
                    try:
                        pending.append(self.q.get_nowait())
                    except queue.Empty:
                        break
            if pending:
                self._drain(pending)
            # Always advance in-flight moves, even when the queue is idle.
            self._tick_moves()
            if pending:
                time.sleep(self.tick)

    def _drain(self, items):
        coalesced = {}
        order = []
        for it in items:
            name = it[1]
            if name in coalesced:
                coalesced[name] = it          # latest command for this part wins
            else:
                coalesced[name] = it
                order.append(name)
        for name in order:
            self._apply(coalesced[name])

    def _apply(self, it):
        kind = it[0]
        if kind == 'set':
            _, name, value = it
            if name not in self._parts:
                return
            profile = self._profile[name]
            if profile.smoothing_ms > 0:
                # smoothed part: ease to the value over the smoothing window
                self._start_move(name, value, profile.smoothing_ms)
            else:
                self._active.pop(name, None)
                if self._current.get(name) != value:
                    self._write(name, value)
        elif kind == 'move':
            _, name, value, ms = it
            if name not in self._parts:
                return
            if ms <= 0:
                self._active.pop(name, None)
                if self._current.get(name) != value:
                    self._write(name, value)
            else:
                self._start_move(name, value, ms)

    def _start_move(self, name, value, ms):
        start = self._current.get(name, value)
        if start == value:
            self._write(name, value)
            return
        self._active[name] = (start, value, time.monotonic(), ms / 1000.0)

    def _tick_moves(self):
        now = time.monotonic()
        for name, (start, to, t0, dur) in list(self._active.items()):
            p = (now - t0) / dur
            if p >= 1.0:
                self._write(name, to)
                del self._active[name]
            else:
                self._write(name, start + (to - start) * self._profile[name].ease(p))

    def _write(self, name, value):
        self._parts[name].set_value(value)
        self._current[name] = value