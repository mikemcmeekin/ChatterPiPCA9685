# -*- coding: utf-8 -*-
"""
Single worker thread for all PCA9685 I2C writes.

Callers (audio callback, script scheduler, Viam service) never touch I2C:
they push commands into a queue, and this thread applies them. Commands
are drained in order, latest command per part wins, so a slow write can
never build a backlog that stalls audio playback.

Two command types per part:
  set  - write the value immediately
  move - interpolate from the part's current value to the target over ms
         (re-targeting mid-move restarts the move from the current value)
"""
import time
import queue
from threading import Thread

class ServoWorker:
    def __init__(self, tick=0.002):
        self.tick = tick
        self.q = queue.Queue()
        self._stopped = False
        self._parts = {}     # name -> PartDevice
        self._current = {}   # name -> last value written
        self._active = {}    # name -> (from, to, start_monotonic, dur_s)
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()

    def add_part(self, name, part, initial):
        self._parts[name] = part
        self._current[name] = initial

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
            if name in self._parts:
                self._active.pop(name, None)
                self._write(name, value)
        elif kind == 'move':
            _, name, value, ms = it
            if name not in self._parts:
                return
            if ms <= 0:
                self._active.pop(name, None)
                self._write(name, value)
            else:
                start = self._current.get(name, value)
                self._active[name] = (start, value, time.monotonic(), ms / 1000.0)

    def _tick_moves(self):
        now = time.monotonic()
        for name, (start, to, t0, dur) in list(self._active.items()):
            if now - t0 >= dur:
                self._write(name, to)
                del self._active[name]
            else:
                p = (now - t0) / dur
                self._write(name, start + (to - start) * p)

    def _write(self, name, value):
        self._parts[name].set_value(value)
        self._current[name] = value