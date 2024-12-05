import bpy
from os import path
import sys
import webbrowser
import asyncio
from subprocess import Popen

from .addon import addon


class SB_OT_setup(bpy.types.Operator):
    bl_idname = "pribambase.setup"
    bl_label = "Install Aseprite Extension"
    bl_description = "Install an extension to Aseprite, that makes it possible to communicate with Blender"

    def execute(self, context):
        where = path.join(path.dirname(__file__), "aseprite")
        self.report({'INFO'}, f"Opening '{where}'...")
        webbrowser.open(where)
        return {'FINISHED'}


class SB_OT_launch(bpy.types.Operator):
    bl_idname = "pribambase.launch"
    bl_label = "Launch Aseprite"
    bl_description = "Launch Aseprite for texture painting"

    wait_connect:bpy.props.BoolProperty(default=False, options={'HIDDEN'})

    @classmethod
    def poll(self, context):
        return not addon.connected


    def execute(self, context):
        exe = addon.prefs.executable or addon.prefs.executable_auto
        print(addon.prefs.executable_auto)
        if not exe:
            self.report({'ERROR'}, "Please specify a valid path to aseprite exe/app in addon settings.")
            return {'CANCELLED'}

        if not addon.connected:
            if addon.server_up:
                bpy.ops.pribambase.server_stop() # fixes some networking issues after disconnect

            bpy.ops.pribambase.server_start()

            if self.wait_connect:
                # If there's already an instance ready to connect, let it do so. That feels somewhat
                # out of control when using, but avoids situation when second instance of aseprite 
                # appears and doesn't connect to anything
                try:
                    wait = asyncio.wait_for(addon.server.ev_connect.wait(), timeout=0.1)
                    asyncio.get_event_loop().run_until_complete(wait)
                    return {'FINISHED'}
                except asyncio.TimeoutError:
                    pass # it's okay

        start_lua = path.join(path.dirname(__file__), "scripts", "start.lua")
        if sys.platform == "win32":
            from subprocess import DETACHED_PROCESS
            Popen([exe, "--script", start_lua], creationflags=DETACHED_PROCESS)
        else:
            Popen([exe, "--script", start_lua])
        
        if self.wait_connect:
            try:
                wait = asyncio.wait_for(addon.server.ev_connect.wait(), timeout=5.0)
                asyncio.get_event_loop().run_until_complete(wait)
            except asyncio.TimeoutError:
                self.report({'ERROR'}, "Aseprite takes too long to start...")
                return {'CANCELLED'}

        return {'FINISHED'}