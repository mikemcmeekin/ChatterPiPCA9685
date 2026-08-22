# -*- coding: utf-8 -*-
"""
Conductor: plays a script on all configured skeletons, locked together.

Runs on the conductor machine (e.g. a desktop PC) - no viam-server needed
here, just the viam-sdk python client. For every skeleton it:

  1. measures the skeleton's clock offset with an RTT-corrected get_time
     handshake (the skeleton also needs NTP as a baseline), and
  2. issues play(script, start_epoch=t0, offset) so every skeleton starts
     at the same shared wall-clock instant.

Usage:
  python conductor.py --script greet
  python conductor.py --script greet --lead 5 --wait
  python conductor.py --list
"""
import argparse
import asyncio
import json
import logging
import time

from viam.robot.client import RobotClient
from viam.resource.types import resource_name_from_string

log = logging.getLogger("chatterpi.conductor")


def load_config(path):
    with open(path) as f:
        return json.load(f)


async def connect(entry):
    address = entry["address"]
    if entry.get("api_key"):
        options = RobotClient.Options.with_api_key(entry["api_key"],
                                                   entry.get("api_key_id", ""))
    else:
        options = RobotClient.Options()
    robot = await RobotClient.at_address(address, options)
    service_name = entry.get("service_name", "skeleton")
    rn = resource_name_from_string(f"rdk:service:generic/{service_name}")
    return robot, robot.get_service(rn)


async def measure_offset(service):
    """Return how far the skeleton's clock leads the conductor's (seconds)."""
    t_send = time.time()
    resp = await service.do_command({"cmnd": "get_time"})
    t_recv = time.time()
    if not resp.get("ok"):
        raise RuntimeError(f"get_time failed: {resp}")
    rtt = t_recv - t_send
    return resp["epoch"] - (t_send + rtt / 2.0)


async def wait_idle(services, timeout=120.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        states = []
        for name, svc in services:
            st = await svc.do_command({"cmnd": "status"})
            states.append(st.get("player", {}).get("state", "idle"))
        if all(s == "idle" for s in states):
            return True
        await asyncio.sleep(1.0)
    return False


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="conductor.json")
    parser.add_argument("--script", help="script name to play on all skeletons")
    parser.add_argument("--lead", type=float, default=None,
                        help="seconds to wait before the script starts "
                             "(default: from config or 3)")
    parser.add_argument("--wait", action="store_true",
                        help="wait until every skeleton finishes the script")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--list", action="store_true", help="list scripts on each skeleton")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    cfg = load_config(args.config)
    skeletons = cfg["skeletons"]
    lead = args.lead if args.lead is not None else float(cfg.get("lead_seconds", 3.0))

    connected = []
    try:
        for entry in skeletons:
            robot, svc = await connect(entry)
            connected.append((entry["name"], robot, svc))
            log.info("connected to %s (%s)", entry["name"], entry["address"])

        if args.list:
            for name, _robot, svc in connected:
                resp = await svc.do_command({"cmnd": "list_scripts"})
                print(f"{name}: {resp.get('scripts', [])}")
            return

        if not args.script:
            parser.error("--script is required")

        offsets = {}
        for name, _robot, svc in connected:
            offsets[name] = await measure_offset(svc)
            log.info("%s: clock offset %+.1f ms (rtt included)", name, offsets[name] * 1000)

        t0 = time.time() + lead
        for name, _robot, svc in connected:
            resp = await svc.do_command({"cmnd": "play", "script": args.script,
                                         "start_epoch": t0, "offset": offsets[name]})
            if not resp.get("ok"):
                raise RuntimeError(f"play failed on {name}: {resp}")
            log.info("scheduled %r on %s for t0=%.3f", args.script, name, t0)

        if args.wait:
            ok = await wait_idle([(n, s) for n, _r, s in connected], timeout=args.timeout)
            log.info("all skeletons idle: %s", ok)
    finally:
        for _name, robot, _svc in connected:
            await robot.close()


if __name__ == "__main__":
    asyncio.run(main())