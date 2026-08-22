# Viam Integration Guide

This guide covers running the skeleton control system under Viam: how the pieces fit together, how to register the custom module on each skeleton Pi, how to drive one skeleton directly, and how the desktop conductor plays the same script on every skeleton at the same instant.

## Architecture

```
conductor PC (desktop)                  each skeleton Pi (one per skeleton)
┌───────────────────────────┐  gRPC   ┌─────────────────────────────────────────┐
│ conductor.py              │ ──────▶ │ viam-server                             │
│  - connects to all Pis    │         │  └─ skeleton-module (python process)    │
│  - measures clock offsets │         │      └─ SkeletonCore                    │
│  - schedules play(t0)     │         │          ├─ SkeletonRig (PCA9685 I2C)   │
└───────────────────────────┘         │          ├─ AudioEngine (jaw+eyes)      │
                                      │          ├─ ScriptPlayer (timeline)     │
                                      │          └─ legacy trigger/ambient loop │
                                      └─────────────────────────────────────────┘
```

Key points:

- Each Pi runs **viam-server** plus one **python module process** (`skeletonModule.py`). The module process is the *only* process that touches the PCA9685, audio, and scripts — do not run `main.py` and viam-server on the same Pi at the same time.
- The conductor is a plain python script on the desktop (or any PC). It only needs the `viam-sdk` client library — **no viam-server on the conductor**.
- **Synchronization** is NTP (enabled on every machine) plus a per-play clock handshake: the conductor pings each skeleton with `get_time`, computes the skeleton's clock offset (RTT-corrected), and sends `play(script, start_epoch=t0, offset)`. Each skeleton converts `t0` to its own local monotonic clock and starts exactly then. On a LAN this lands all skeletons within a few milliseconds.

## 1. Prerequisites (per Pi)

- Raspberry Pi OS with I2C enabled; PCA9685 wired to the I2C bus (SDA/SCL, 3.3 V).
- [viam-server](https://docs.viam.com/get-started/install/) installed and running (either linked to a robot in the [Viam app](https://app.viam.com) or standalone on the LAN).
- Python 3 with dependencies installed:
  ```sh
  cd /root/ChatterPi
  pip install -r requirements.txt
  ```
- NTP enabled (Raspberry Pi OS ships with `systemd-timesyncd`):
  ```sh
  timedatectl set-ntp true
  timedatectl status   # "NTP service: active" and a sane time source
  ```

The code is deployed at `/root/ChatterPi` (the default path used by the example configs below). If you deploy elsewhere, update `executable_path`, the `env` block, and `CHATTERPI_CONFIG`.

## 2. Configure the skeleton

All hardware is declared in `/root/ChatterPi/src/config.ini`. Every servo or LED is a `[PART <name>]` section, so each skeleton's config describes its own equipment:

```ini
[PART head]
type = servo
channel = 1
min_angle = -30
max_angle = 30
pulse_min = 500
pulse_max = 2500
rest = 0

[PART eyes]
type = led
channel = 4
```

| field | meaning |
|---|---|
| `type` | `servo` or `led` |
| `channel` | PCA9685 channel (0–15) |
| `min_angle` / `max_angle` | servo limits (degrees); may be flipped to reverse direction |
| `pulse_min` / `pulse_max` | servo pulse-width range in µs (per your servo) |
| `rest` | position returned to after a script finishes (and on `stop`) |
| `enabled` | set `false` to skip a part declared but not wired (default `true`) |

Other relevant settings (see the committed `config.ini` for a full example):

- `[SCRIPTS] directory` — where scripts are read from (default `scripts`, relative to the process working directory; use an absolute path to be safe).
- `[AUDIO] jaw_part` — the part the audio level drives (default `jaw`).
- `[CONTROLLER] style` / thresholds — legacy jaw controller (0/1/2), unchanged.
- The config file location defaults to `/root/ChatterPi/src/config.ini` and can be overridden with the `CHATTERPI_CONFIG` environment variable (the module config below sets it).

Scripts live as JSON files in the scripts directory (default `/root/ChatterPi/src/scripts/`). See [§6 Script format](#6-script-format).

## 3. Register the module with viam-server

The module entrypoint is `src/run.sh` (a small wrapper that `cd`s into `src` and runs `python3 skeletonModule.py`, so relative paths resolve identically to dev mode):

```sh
#!/bin/sh
cd /root/ChatterPi/src
exec python3 skeletonModule.py
```

Add the module and the service to the robot config. In the Viam app (JSON form):

```json
{
  "modules": {
    "skeleton-module": {
      "type": "local",
      "executable_path": "/root/ChatterPi/src/run.sh",
      "env": {
        "CHATTERPI_CONFIG": "/root/ChatterPi/src/config.ini"
      }
    }
  },
  "services": {
    "skeleton": {
      "name": "skeleton",
      "namespace": "rdk",
      "type": "service",
      "subtype": "generic",
      "model": "mcmeekin:service:skeleton",
      "attributes": {}
    }
  }
}
```

The same config in YAML (config file form):

```yaml
modules:
  skeleton-module:
    type: local
    executable_path: /root/ChatterPi/src/run.sh
    env:
      CHATTERPI_CONFIG: /root/ChatterPi/src/config.ini

services:
  - name: skeleton
    namespace: rdk
    type: service
    subtype: generic
    model: mcmeekin:service:skeleton
```

- `env` is optional — it only matters if your config.ini is not at the default path.
- The service is a **generic service**: its API is `rdk:service:generic`, its model is `mcmeekin:service:skeleton`, and its instance name (`skeleton` above) is what clients use to find it.

Start (or restart) viam-server. A successful module start logs:

```
skeleton <name> ready: parts=['arm_l', 'arm_r', 'eyes', 'head', 'jaw'] scripts=['greet', 'point']
```

## 4. Talking to one skeleton (python client)

Any machine with `viam-sdk` installed can talk to a single skeleton:

```python
import asyncio

from viam.robot.client import RobotClient
from viam.resource.types import resource_name_from_string

ADDRESS = "http://192.168.1.50:8090"   # the Pi's viam-server

async def main():
    # For a standalone (not app-linked) viam-server on the LAN, use:
    #   options = RobotClient.Options()
    # For an app-linked robot:
    #   options = RobotClient.Options.with_api_key("<API-KEY>", "<API-KEY-ID>")
    options = RobotClient.Options()
    robot = await RobotClient.at_address(ADDRESS, options)
    svc = robot.get_service(resource_name_from_string("rdk:service:generic/skeleton"))

    print(await svc.do_command({"cmnd": "list_scripts"}))
    print(await svc.do_command({"cmnd": "status"}))
    print(await svc.do_command({"cmnd": "play", "script": "greet"}))
    # ...
    # await svc.do_command({"cmnd": "stop"})

    await robot.close()

asyncio.run(main())
```

## 5. Multi-skeleton choreography (the conductor)

The conductor (`src/conductor.py`) runs on the desktop. Setup:

```sh
pip install viam-sdk
```

Edit `src/conductor.json` — one entry per skeleton:

```json
{
  "lead_seconds": 3,
  "skeletons": [
    {
      "name": "skeleton1",
      "address": "http://192.168.1.50:8090",
      "api_key": "",
      "api_key_id": "",
      "service_name": "skeleton"
    },
    {
      "name": "skeleton2",
      "address": "http://192.168.1.51:8090",
      "api_key": "",
      "api_key_id": "",
      "service_name": "skeleton"
    }
  ]
}
```

| field | meaning |
|---|---|
| `name` | label used in logs |
| `address` | the Pi's viam-server address (`http://<ip>:8090`) |
| `api_key` / `api_key_id` | the robot's API key pair if it is linked to the Viam app; leave `""` for standalone LAN viam-servers |
| `service_name` | the service instance name (default `skeleton`) |
| `lead_seconds` | default countdown before the script starts |

Usage:

```sh
python src/conductor.py --list                 # list scripts on each skeleton
python src/conductor.py --script greet         # play "greet" on all, ~3s from now
python src/conductor.py --script greet --lead 5 --wait --timeout 60
```

What happens under the hood:

1. Connect to every skeleton.
2. `get_time` handshake with each: the conductor computes `offset = pi_epoch − (send_time + rtt/2)` — how far that Pi's clock leads the conductor's.
3. Pick one shared start time `t0 = now + lead`.
4. `play(script, start_epoch=t0, offset)` on every skeleton. Each skeleton starts its timeline when *its* wall clock hits `t0 + offset`, i.e. the same shared instant.
5. With `--wait`, the conductor polls `status` until every skeleton reports `idle` (or `--timeout`).

Accuracy: NTP keeps all clocks within ~ms on a LAN; the handshake removes any per-Pi bias. If a Pi's clock is wildly wrong, the script will start far early or late — check `timedatectl status` on the misbehaving Pi.

## 6. Script format

Scripts are JSON files in the scripts directory. `t` is the offset in **seconds from the start of the script**:

```json
{
  "name": "greet",
  "steps": [
    { "t": 0.0, "audio": "v01.wav" },
    { "t": 0.4, "move": { "head": 15, "ms": 400 } },
    { "t": 1.2, "move": { "arm_l": 60, "ms": 300 } },
    { "t": 2.0, "set": { "eyes": 100 } },
    { "t": 2.6, "move": { "arm_l": 0, "ms": 500 } },
    { "t": 3.4, "set": { "eyes": 0 } },
    { "t": 4.0, "move": { "head": 0, "ms": 400 } }
  ]
}
```

| step field | meaning |
|---|---|
| `t` | when the step fires, seconds from the script start |
| `audio` | play a track (filename in the vocals dir, or a full path). The jaw is driven automatically by the audio level using the configured STYLE 0/1/2 controller. |
| `move` | object of `{ "part_name": target_value, "ms": duration }`. Each part eases to its target over `ms` milliseconds (default 0 = immediate). Multiple parts may move in one step. |
| `set` | object of `{ "part_name": value }`, applied immediately (used for LEDs like `eyes`). |

Notes:

- Steps may appear in any order in the file; they execute sorted by `t`.
- Part names must match `[PART <name>]` sections in that skeleton's config. Unknown parts log a warning and are skipped — the same script can therefore run on skeletons with different equipment (missing parts just no-op).
- After the last step, all parts return to their configured `rest` positions.
- The committed `src/scripts/greet.json` and `src/scripts/point.json` are working examples (`greet.json` is the one above).
- JSON has no comments; keep the format strict so the loader validates it. (If you'd prefer an alternative — e.g. a YAML with comments, or a Python DSL for authored choreography — say so and we can add a converter; the on-wire format the player consumes is this JSON.)

## 7. Command reference

All commands are sent with `do_command` on the service. Every response includes `"ok"`.

| `cmnd` | arguments | response |
|---|---|---|
| `play` | `script` (name), optional `start_epoch` (shared wall-clock seconds), optional `offset` (this skeleton's clock offset in seconds) | `script`, `start_epoch`, `offset`, `duration` |
| `stop` | — | — (aborts the current script, stops audio, returns parts to rest) |
| `list_scripts` | — | `scripts: [...]` |
| `status` | — | `mode` (`idle`/`legacy`/`script`), `player: {state, script}`, `audio_playing`, `parts` |
| `get_time` | — | `epoch` — current wall-clock time on the skeleton (used by the clock handshake) |
| `set_part` | `part`, `value`, optional `ms` | — (immediate or eased move of one part) |
| `rest` | — | — (all parts to their rest positions) |

A `play` with no `start_epoch` starts immediately on that skeleton (no cross-skeleton synchronization).

The legacy trigger/ambient modes (PIR/TIMER/START, `AMBIENT` on/off) keep working inside the module process. While a script is scheduled or playing, the legacy loop yields the hardware to it and resumes afterwards. PIR triggering is not supported in this build (it was already dead code before the refactor).

## 8. Troubleshooting

- **Module never becomes ready / viam-server logs "module exited"** — run the entrypoint manually to see the real traceback: `sh /root/ChatterPi/src/run.sh`. Most causes are missing `pip` dependencies or I2C errors (check `i2cdetect -y` and the wiring; the PCA9685 must be 3.3 V logic on the Pi).
- **`script 'x' not found`** — the scripts directory is resolved relative to the module's working directory; `run.sh` `cd`s into `src`, so the default `scripts` directory is `src/scripts`. Use an absolute path in `[SCRIPTS] directory` if you move things.
- **`PortAudio status: output underflow` log lines** — the audio buffer underran (CPU contention or a very slow I2C write). The I2C worker thread isolates I2C from the audio thread; if it persists, check what else is running on the Pi.
- **Movements lag behind the audio** — raise `blocksize` in `audioEngine.py` or lower servo tick rate; also make sure no other process is driving the same PCA9685 (only the module process may).
- **Skeletons start at noticeably different times** — check `timedatectl status` on each Pi (NTP active? same time source?), and the conductor log lines `skeletonN: clock offset +X.X ms` — a large offset means that Pi's NTP isn't tracking.
- **`do_command` returns `{"ok": false, "error": "..."}`** — the message names the cause (unknown script, unknown part, script already running, etc.).
- **Changing config.ini at runtime** — servo/controller values are re-read on the next vocal track (legacy behavior); `PART`/script-dir changes require restarting viam-server (the module process).