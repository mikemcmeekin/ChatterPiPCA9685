# -*- coding: utf-8 -*-
"""
Viam module that exposes one skeleton's capabilities as a generic service.

Launched by viam-server (see the module entry in the robot config).
Commands are sent with do_command:

    play          {"cmnd": "play", "script": "greet",
                   "start_epoch": 1755000000.0,   # shared wall clock
                   "offset": 0.003}               # this Pi's clock offset
    stop          {"cmnd": "stop"}
    list_scripts  {"cmnd": "list_scripts"}
    status        {"cmnd": "status"}
    get_time      {"cmnd": "get_time"}            # {"ok":true,"epoch":...}
    set_part      {"cmnd": "set_part", "part": "head", "value": 15, "ms": 300}
    rest          {"cmnd": "rest"}
"""
import asyncio
import logging

from viam.module.module import Module
from viam.resource.easy_resource import EasyResource
from viam.services.generic import Generic

import config as c
from skeleton import SkeletonCore

log = logging.getLogger("chatterpi.module")


class SkeletonService(Generic, EasyResource):
    MODEL = "mcmeekin:service:skeleton"

    def __init__(self, name):
        super().__init__(name)
        self._core = None

    def reconfigure(self, config, dependencies):
        # reconfigure may be called more than once; build the core once
        if self._core is None:
            c.update()
            self._core = SkeletonCore()
            self._core.start_legacy()
            log.info("skeleton %s ready: parts=%s scripts=%s",
                     self.name, list(self._core.rig.parts), self._core.list_scripts())

    async def do_command(self, command, *, timeout=None, **kwargs):
        core = self._core
        if core is None:
            return {"ok": False, "error": "skeleton not configured"}
        cmnd = command.get("cmnd")
        try:
            if cmnd == "play":
                result = core.play_script(command["script"],
                                          start_epoch=command.get("start_epoch"),
                                          offset=float(command.get("offset", 0.0)))
                return {"ok": True, **result}
            elif cmnd == "stop":
                core.stop()
                return {"ok": True}
            elif cmnd == "list_scripts":
                return {"ok": True, "scripts": core.list_scripts()}
            elif cmnd == "status":
                return {"ok": True, **core.status()}
            elif cmnd == "get_time":
                return {"ok": True, **core.get_time()}
            elif cmnd == "set_part":
                core.set_part(command["part"], command["value"], ms=command.get("ms", 0))
                return {"ok": True}
            elif cmnd == "rest":
                core.rest_all()
                return {"ok": True}
            else:
                return {"ok": False, "error": f"unknown cmnd {cmnd!r}"}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    async def stop(self):
        if self._core is not None:
            self._core.close()
            self._core = None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(Module.run_from_registry())