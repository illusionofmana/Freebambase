# Copyright (c) 2021 lampysprites
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import annotations
from aiohttp.web_ws import WebSocketResponse

import bpy
import asyncio
import aiohttp
from aiohttp import web
from time import time
from itertools import chain

from . import async_loop
from . import util
from .image import uv_lines
from .messaging import encode
from .addon import addon


class Server():
    def __init__(self, host="", port=0):
        self.host = host
        self.port = port
        self._ws = None
        self._server = None
        self._site = None
        self.ev_connect = None
        self._start_time = 0


    def send(self, msg, binary=True):
        if self._ws is not None:
            if binary:
                asyncio.ensure_future(self._ws.send_bytes(msg, False))
            else:
                asyncio.ensure_future(self._ws.send_str(msg, False))


    @property
    def connected(self):
        return self._ws is not None and not self._ws.closed


    def start(self):
        started = False

        self._start_time = int(time())

        async def _start_a(self):
            nonlocal started
            self._server = web.Server(self._receive)

            runner = web.ServerRunner(self._server)
            await runner.setup()

            self._site = web.TCPSite(runner, self.host, self.port)
            await self._site.start()

            started = True

        self.ev_connect = asyncio.Event()
        async_loop.ensure_async_loop()
        stop = asyncio.wait_for(_start_a(self), timeout=5.0)

        try:
            asyncio.get_event_loop().run_until_complete(stop)
            util.refresh()
        except asyncio.TimeoutError:
            raise RuntimeError(f"Could not start server at {self.host}:{self.port}")


    def stop(self):
        async def _stop_a():
            if self._ws is not None:  # no connections happened
                await self._ws.close()
            await self._site.stop()
            await self._site._runner.cleanup()
            await self._server.shutdown()
            addon.active_sprite = None

        asyncio.ensure_future(_stop_a())
        async_loop.erase_async_loop()
        util.refresh()


    async def _receive(self, request) -> WebSocketResponse:
        self._ws = web.WebSocketResponse(max_msg_size=0)

        await self._ws.prepare(request)

        # client connected
        await self._ws.send_bytes(encode.texture_list(addon.state.identifier, addon.texture_list), False)
        bpy.ops.pribambase.report(message_type='INFO', message="Aseprite connected")
        self.ev_connect.set()

        if addon.prefs.uv_sync_auto:
            addon.watch = UVWatch()
            addon.watch.start()

        util.refresh()

        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.BINARY:
                await addon.handlers.process(msg.data)

            elif msg.type == aiohttp.WSMsgType.ERROR:
                bpy.ops.pribambase.report(message_type='ERROR', message=f"Aseprite connection closed with exception {self._ws.exception()}")

        # client disconnected
        
        if addon.watch:
            addon.watch.stop()
            addon.watch = None

        bpy.ops.pribambase.report(message_type='INFO', message="Aseprite disconnected")
        util.refresh()

        return self._ws


class UVWatch:
    running = None # only allow one running watch to avoid the confusion, and keep performance acceptable

    PERIOD = 0.2 # seconds between timer updates
    
    def __init__(self):
        self.is_running = False
    

    def start(self):
        assert not self.__class__.running
        self.last_hash = 0
        self.scene_hash = 0
        self.idle_t = 0
        self.send_pending = False
        self.resend()
        self.__class__.running = self
        bpy.app.timers.register(self.timer_callback)
        self.timer_callback()
    

    def stop(self):
        assert self == self.__class__.running
        self.__class__.running = None
    

    def resend(self):
        """Schedule uv send, even if there's no change in the uv map. Not a forced send - it respects sync mode."""
        watched = addon.state.uv_watch

        if watched == 'NEVER':
            return
        else:
            active_sprite = addon.active_sprite_image
            send = bool(active_sprite) and ('SHOW_UV' in active_sprite.sb_props.sync_flags)

            if watched == 'SHOWN':
                send = send and self.active_sprite_open(bpy.context)

            self.send_pending = self.send_pending or send


    def timer_callback(self):
        if self != self.__class__.running:
            return None

        self.idle_t += self.PERIOD

        context = bpy.context
        watched = addon.state.uv_watch

        if not self.send_pending:
            # shim older blender unconditionally returning `context.mode -> 'OBJECT'`
            ctx_mode = 'APIBUG' # /rly wanted to put a bad word here/
            if (context and context.view_layer.objects.active):
                ctx_mode = context.view_layer.objects.active.mode

            # go sleep in several cases that do not imply sending the UVs
            if watched == 'NEVER' \
                    or ctx_mode not in ('EDIT', 'TEXTURE_PAINT') \
                    or (watched == 'SHOWN' and not self.active_sprite_open(context)) \
                    or addon.active_sprite_image is None \
                    or ('SHOW_UV' not in addon.active_sprite_image.sb_props.sync_flags):
                return self.PERIOD

            changed = self.update_lines(context) or self.update_scene() # skip checks when waiting to send
            self.send_pending = self.send_pending or changed and self.last_hash
        
        if self.send_pending: # not elif!!
            if self.idle_t >= addon.prefs.debounce:
                size = addon.state.uv_size
                if addon.state.uv_is_relative:
                    img = addon.active_sprite_image
                    if img:
                        size = (int(img.size[0] * addon.state.uv_scale), int(img.size[1] * addon.state.uv_scale))
                
                if bpy.app.version >= (4, 0, 0):
                    with context.temp_override(**context.copy()):
                        bpy.ops.pribambase.uv_send(
                            size=size,
                            color=addon.state.uv_color,
                            weight=addon.state.uv_weight)
                else:
                    bpy.ops.pribambase.uv_send(context.copy(), 
                        size=size,
                        color=addon.state.uv_color, 
                        weight=addon.state.uv_weight)
                self.send_pending = False
                self.idle_t = 0

        return self.PERIOD


    def update_lines(self, context:bpy.types.Context) -> bool:
        # older versions have some mess for bpy.context here, and does not have selected/active object fields, hence view_layer
        meshes = (obj.data for obj in context.view_layer.objects if obj.select_get() and obj.type == 'MESH' and obj.data)
        active_obj = context.view_layer.objects.active
        if active_obj and active_obj.type == 'MESH':
            meshes = chain(meshes, [active_obj.data])

        lines = frozenset(line for mesh in meshes for line in uv_lines(mesh, only_selected=not context.scene.tool_settings.use_uv_select_sync))
        new_hash = hash(lines) if lines else 0
        changed = (new_hash != self.last_hash)
        self.last_hash = new_hash
        return changed

    
    def update_scene(self) -> bool:
        new_hash = hash((addon.active_sprite, *addon.state.uv_color, addon.state.uv_is_relative, addon.state.uv_scale,
            *addon.state.uv_size, addon.state.uv_weight))
        changed = self.scene_hash != new_hash
        self.scene_hash = new_hash
        return changed
    

    def active_sprite_open(self, context) -> bool:
        active = addon.active_sprite

        image_editors = (a for window in context.window_manager.windows for a in window.screen.areas if a.type=='IMAGE_EDITOR')

        for area in image_editors:
            image = area.spaces[0].image
            if image and image.sb_props.sync_name == active:
                return True

        return False


class SB_OT_server_start(bpy.types.Operator):
    bl_idname = "pribambase.server_start"
    bl_label = "Open Connection"
    bl_description = "Begin accepting connections from Aseprite"


    @classmethod
    def poll(self, ctx):
        return not addon.server_up


    def execute(self, context):
        addon.start_server()
        return {'FINISHED'}


class SB_OT_server_stop(bpy.types.Operator):
    bl_idname = "pribambase.server_stop"
    bl_label = "Close Connection"
    bl_description = "Disconnect and stop accepting connections from Aseprite"


    @classmethod
    def poll(self, ctx):
        return addon.server_up


    def execute(self, context):
        addon.stop_server()
        return {"FINISHED"}


class SB_OT_send_texture_list(bpy.types.Operator):
    bl_idname = "pribambase.send_texture_list"
    bl_label = "Update Texture List"
    bl_description = "Update Aseprite about which textures are used in the blendfile"
    bl_options = {'INTERNAL'}


    @classmethod
    def poll(self, ctx):
        return addon.server_up


    def execute(self, context):
        if addon.connected:
            msg = encode.texture_list(addon.state.identifier, addon.texture_list)
            addon.server.send(msg)

        return {'FINISHED'}
