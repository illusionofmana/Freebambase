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

"""
Connection panel and general stuff.
"""

import bpy

from .addon import addon
from .image import SB_OT_sprite_reload_all
from .setup import SB_OT_launch


class SB_OT_grid_set(bpy.types.Operator):
    bl_idname = "pribambase.grid_set"
    bl_label = "Pixel Grid"
    bl_description = "Set grid step in every viewport"
    

    step: bpy.props.IntProperty(
        name="Density (px/m)",
        description="Grid step in pixels. It's inverse of what viewport uses",
        min=1,
        default=10)

    absolute: bpy.props.BoolProperty(
        name="Absolute Scale",
        description="Make grid scale independent of viewport zoom",
        default=True)
    

    def execute(self, context):
        if not context or not context.window_manager:
            return {'CANCELLED'}

        context.scene.unit_settings.system = 'NONE'
        # looong looong
        for wsp in bpy.data.workspaces:
            for screen in wsp.screens:
                for area in screen.areas:
                    if area.type == 'VIEW_3D':
                        for space in area.spaces:
                            if space.type == 'VIEW_3D':
                                space.overlay.grid_subdivisions = 1 if self.absolute else self.step
                                space.overlay.grid_scale = 1/self.step

        return {'FINISHED'}
    

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class SB_PT_uv_draw(bpy.types.Panel):
    bl_idname = "SB_PT_uv_draw"
    bl_label = "UV Style"
    bl_category = "Pribambase"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}
        

    def draw(self, ctx):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        watch_row = layout.row()
        watch_row.enabled = addon.prefs.uv_sync_auto
        watch_row.prop(addon.state, "uv_watch")
        size_row = layout.row(align=True)
        if addon.state.uv_is_relative:
            size_row.prop(addon.state, "uv_scale")
            size_row.prop(addon.state, "uv_is_relative", icon='LINKED', text="")
        else:
            size_row.prop(addon.state, "uv_size")
            size_row.prop(addon.state, "uv_is_relative", icon='UNLINKED', text="")
        layout.prop(addon.state, "uv_color")
        layout.prop(addon.state, "uv_weight")


class SB_PT_edit(bpy.types.Panel):
    bl_idname = "SB_PT_edit"
    bl_label = "Edit"
    bl_category = "Pribambase"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"


    def draw(self, context):
        layout = self.layout

        row = layout.row()
        row.label(text="Sprite Plane")
        row = row.row(align=True)
        row.alignment = 'RIGHT'

        op = row.operator("pribambase.plane_add", text="", icon='FILE_IMAGE')
        op.new_image = False
        op.from_file = False

        op = row.operator("pribambase.plane_add", text="", icon='FILE_FOLDER')
        op.new_image = False
        op.from_file = True

        op = row.operator("pribambase.plane_add", text="", icon='FILE')
        op.new_image = True
        op.from_file = False

        layout.operator("pribambase.grid_set", icon='GRID')
        layout.operator("pribambase.material_add", icon='MATERIAL')
        
        row = layout.row()
        row.operator("pribambase.sprite_reload_all", icon='FILE_REFRESH')
        if not SB_OT_sprite_reload_all.poll(context):
            row.label(text="", icon='UNLINKED')


class SB_PT_link(bpy.types.Panel):
    bl_idname = "SB_PT_link"
    bl_label = "Sync"
    bl_category = "Pribambase"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"


    def draw(self, context):
        layout = self.layout

        status = "Off"
        icon = 'UNLINKED'
        if addon.connected:
            status = "Connected"
            icon = 'CHECKMARK'
        elif addon.server_up:
            status = "Waiting..."
            icon = 'SORTTIME'

        if bpy.app.version < (2, 81):
            icon = 'NONE' # :\

        layout.row().label(text=status, icon=icon)
        
        if addon.server_up:
            layout.operator("pribambase.server_stop", text="Stop", icon='DECORATE_LIBRARY_OVERRIDE')
        else:
            layout.operator("pribambase.launch", icon='GREASEPENCIL')
            layout.operator("pribambase.server_start", text="Connect", icon='DECORATE_LINKED')
        
        if "Arm" in bpy.data.worlds:
            layout.prop(context.scene.sb_state, "use_sync_armory")
            

class SB_MT_sprite(bpy.types.Menu):
    bl_label = "Sprite"
    bl_idname = "SB_MT_sprite"


    def draw(self, context):
        layout = self.layout
        connected = addon.connected
        active = connected or SB_OT_launch.poll(context)

        layout.operator("pribambase.sprite_new", icon='FILE_NEW' if active else 'UNLINKED')
        layout.operator("pribambase.sprite_open", icon='FILE_FOLDER' if active else 'UNLINKED')
        layout.operator("pribambase.sprite_edit", icon='GREASEPENCIL' if active else 'UNLINKED')
        layout.operator("pribambase.sprite_edit_copy", icon='DUPLICATE' if active else 'UNLINKED')
        layout.operator("pribambase.sprite_replace", icon='FILE_REFRESH' if active else 'UNLINKED')
        layout.separator()
        layout.operator("pribambase.sprite_make_animated")
        layout.operator("pribambase.uv_send_ui", icon='UV_VERTEXSEL' if connected else 'UNLINKED')


    def header_draw(self, context):
        # deceiptively, self is not the menu here but the header
        self.layout.menu("SB_MT_sprite")


class SB_PT_sprite(bpy.types.Panel):
    bl_idname = "SB_PT_sprite"
    bl_label = "Sprite Info"
    bl_category = "Pribambase"
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"


    def draw(self, context):
        layout = self.layout

        if not context.edit_image:
            layout.label(text="No image", icon='INFO')
            return
            
        img = context.edit_image
        props = img.sb_props
        origin = next((i for i in bpy.data.images if i.sb_props.sheet == img), None)

        sprite = layout.row(align=True)
        source = sprite.row()
        if props.is_sheet and origin:
            source.prop(origin.sb_props, "source")
            
            sub = layout.row()
            sub.alignment = 'RIGHT'
            sub.label(text=f"Sheet {props.sheet_size[0]}x{props.sheet_size[1]}, {props.animation_length} frames")

        else:
            source.prop(context.edit_image.sb_props, "source")
            row = layout.row()
            row.enabled = False
            row.prop(context.edit_image.sb_props, "sheet")

        sprite.operator("pribambase.sprite_purge", icon='TRASH', text="")


class SB_PT_sprite_edit(bpy.types.Panel):
    bl_idname = "SB_PT_sprite_edit"
    bl_label = "Edit"
    bl_category = "Pribambase"
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"


    def draw(self, context):
        layout = self.layout
        connected = addon.connected

        if not connected:
            layout.operator("pribambase.server_start", icon='ERROR')
            layout.separator()

        if not context.edit_image:
            layout.label(text="No image", icon='INFO')
            return

        SB_MT_sprite.draw(self, layout)


class SB_PT_animation(bpy.types.Panel):
    bl_idname = "SB_PT_animation"
    bl_label = "Animation"
    bl_category = "Pribambase"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"


    def draw(self, context):        
        layout = self.layout

        if context.active_object and context.active_object.type == 'MESH':
            obj = context.active_object
            
            # Info
            if next((False for img in bpy.data.images if img.sb_props.sheet), True):
                layout.row().label(text="No synced animations", icon='INFO')

            if not obj.material_slots:
                layout.row().label(text="No material", icon='INFO')

            if obj.sb_props.animation:
                layout.row().label(text=obj.sb_props.animation.name, icon='IMAGE_DATA')

                try:
                    drivers = obj.modifiers["UV Frame (Pribambase)"].object_to.animation_data.drivers
                    if not next((True for d in drivers if d.data_path == "location")):
                        layout.row().label(text="Driver curve not found", icon='ERROR')
                except KeyError:
                    layout.row().label(text="UVWarp not found", icon='ERROR')
                except AttributeError:
                    layout.row().label(text="Driver not found", icon='ERROR')

                if "pribambase_frame" not in obj:
                    layout.row().label(text="Property not found", icon='ERROR')
            else:
                layout.label(text="None", icon='IMAGE_DATA')
                layout.operator("pribambase.spritesheet_rig", icon='ADD', text="Animate")

            row = layout.row()
            row.enabled = bool("pribambase_frame" in obj and obj.sb_props.animation)
            if "pribambase_frame" in obj:
                row.prop(obj, '["pribambase_frame"]', text="Frame")
            else:
                row.prop(addon.state, "frame_stub", text="Frame")

            row = layout.row(align=True)
            row.enabled = bool(obj.animation_data)

            sub = row.column()
            sub.enabled = bool(obj.sb_props.animation)
            sub.prop(obj.sb_props, "animation_tag_setter", text="Tag")
            
            if addon.state.action_preview_enabled:
                active_picked = (context.active_object == addon.state.action_preview)
                row.operator("pribambase.action_preview_set", icon='EYEDROPPER', text="", depress=active_picked)
                row.operator("pribambase.action_preview_clear", icon='PREVIEW_RANGE', text="", depress=True)
            else:
                row.operator("pribambase.action_preview_set", icon='PREVIEW_RANGE', text="")

            if obj.sb_props.animation:
                layout.row().operator("pribambase.spritesheet_unrig", icon='TRASH')

        else:
            layout.label(text="Select a mesh")