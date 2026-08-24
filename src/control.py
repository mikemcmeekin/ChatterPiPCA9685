# -*- coding: utf-8 -*-
"""
Legacy trigger/ambient control loop, refactored onto SkeletonCore.

Runs on its own thread and yields whenever a script is scheduled or
playing, so Viam-driven choreography always has the hardware to itself.
"""
import logging
import time

import config as c

log = logging.getLogger("chatterpi.control")


def _eyes_on(core, on):
    if c.EYES == 'ON' and c.EYES_PART in core.rig.parts:
        core.rig.set(c.EYES_PART, 100 if on else 0)


def _trigger_out(core):
    if c.TRIGGER_OUT == 'ON' and c.TRIGGER_OUT_PART in core.rig.parts:
        core.rig.set(c.TRIGGER_OUT_PART, 100)
        time.sleep(0.5)
        core.rig.set(c.TRIGGER_OUT_PART, 0)


def _in_script(core):
    return core.mode == 'script'


def _event_handler(core):
    """Play one vocal track the old ChatterPi way (files source)."""
    c.update()
    _eyes_on(core, True)
    _trigger_out(core)
    core.tracks.play_vocal()
    _eyes_on(core, False)


def _wait_ambient(core, finished, until, stop_event):
    """Wait for the current ambient track to finish, interrupted by the
    trigger time (or shutdown). Returns True if interrupted."""
    while not stop_event.is_set():
        if time.time() > until:
            core.audio.stop()
            finished.wait(timeout=2)
            return True
        if finished.is_set():
            return False
        time.sleep(0.5)
    return False


def run_control_loop(core, stop_event):
    try:
        if c.PROP_TRIGGER == 'MANUAL':
            # No autonomous trigger/ambient loop. Playback happens only via an
            # explicit Viam `play` (manual run), which plays the track once;
            # the skeleton then idles until the next play command.
            log.info("manual mode: no auto-trigger loop; playback via Viam play only")
            while not stop_event.is_set():
                time.sleep(1)
            return
        if c.AMBIENT == 'ON':
            if c.PROP_TRIGGER == 'START':
                # No ambient tracks play with this setting
                _eyes_on(core, True)
                _trigger_out(core)
                core.tracks.play_vocal()
                _eyes_on(core, False)
            elif c.PROP_TRIGGER == 'TIMER':
                while not stop_event.is_set():
                    if _in_script(core):
                        time.sleep(1)
                        continue
                    trigger_time = time.time() + c.DELAY
                    finished = core.tracks.play_ambient()
                    if finished is None:
                        log.warning("no ambient tracks available; idling")
                        time.sleep(5)
                        continue
                    if _wait_ambient(core, finished, trigger_time, stop_event):
                        _event_handler(core)
                        if not stop_event.is_set():
                            time.sleep(c.DELAY)
            else:  # PIR
                log.warning("PIR trigger is not supported in this build; idling")
                while not stop_event.is_set():
                    time.sleep(1)
        else:  # AMBIENT == 'OFF'
            if c.PROP_TRIGGER == 'TIMER':
                start_time = time.time()
                while not stop_event.is_set():
                    if _in_script(core):
                        start_time = time.time()
                        time.sleep(1)
                        continue
                    if time.time() > start_time + c.DELAY:
                        _event_handler(core)
                        start_time = time.time()
            elif c.PROP_TRIGGER == 'START':
                _eyes_on(core, True)
                _trigger_out(core)
                core.tracks.play_vocal()
                _eyes_on(core, False)
            else:  # PIR
                log.warning("PIR trigger is not supported in this build; idling")
                while not stop_event.is_set():
                    time.sleep(1)
    except SystemExit:
        log.info("legacy control loop ended (vocal play count reached)")
    except Exception:
        log.exception("legacy control loop terminated")