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
Addon-related data structures and type properties
"""

import bpy
import secrets
import os.path

from .addon import addon


def _get_identifier(self):
    if bpy.data.filepath:
        return bpy.data.filepath

    if "_identifier" not in self:
        self["_identifier"] = secrets.token_hex(4) # 8 chars should be enough?

    return self["_identifier"]


def _find_aseprite(_self):
    exe = addon.prefs.executable
    lookup_paths = (
        "C:\\Program Files\\Aseprite\\aseprite.exe",
        "C:\\Program Files (x86)\\Aseprite\\aseprite.exe",
        "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Aseprite\\aseprite.exe",
        "/Applications/Aseprite.app",
        "~/Library/Application Support/Steam/steamapps/common/Aseprite/Aseprite.app",
        "~/.steam/debian-installation/steamapps/common/Aseprite/aseprite",
        "/usr/bin/aseprite")

    if exe and os.path.exists(exe):
        return exe
    else:
        return next((p for p in lookup_paths if os.path.exists(p)), "")


class SB_State(bpy.types.PropertyGroup):
    """Pribambase file-related data"""
    identifier: bpy.props.StringProperty(
        name="Identifier",
        description="Unique but not permanent id for the current file. Prevents accidentally syncing textures from another file",
        get=_get_identifier)
    
    action_preview: bpy.props.PointerProperty(
        name="Action Preview",
        description="For locking timeline preview range",
        type=bpy.types.Object,
        poll=lambda self, object : object is None or object.type == 'MESH')
    
    action_preview_enabled: bpy.props.BoolProperty(
        name="Action Preview",
        description="Lock timeline preview range to action length")

    uv_watch: bpy.props.EnumProperty(
        name="Update",
        description="Change when UV map updates in Aseprite",
        items=(('ALWAYS', "Always", "Update displayed UVs when enabled in the currently open document in Aseprite"), 
            ('SHOWN', "Image Editor", "Only update UVs when currently open document in Aseprite is also open in the Blender's image editor"),
            ('NEVER', "Manual", "Do not sync UV when they change in Blender. UVs can be sent to Aseprite from image editor menu")))
    
    uv_is_relative: bpy.props.BoolProperty(
        name="Relative Size",
        description="Make UVMap size proportional to the size of the image",
        default=True)
    
    uv_scale:bpy.props.FloatProperty(
        name="Scale",
        description="Resolution of the UV layer relative to that of the sprite",
        default=2.0,
        min=0.0,
        max=10.0,
        subtype='FACTOR')
    
    uv_size:bpy.props.IntVectorProperty(
        name="Size",
        description="Resolution of the UV layer in pixels",
        size=2,
        default=(128, 128),
        min=0)

    uv_color: bpy.props.FloatVectorProperty(
        name="Color",
        description="Default color to draw the UVs with",
        size=4,
        default=(0.0, 0.0, 0.0, 0.45),
        min=0.0,
        max=1.0,
        subtype='COLOR')

    uv_weight: bpy.props.FloatProperty(
        name="Thickness",
        description="Default thickness of the UV map with scale appied. For example, if `UV scale` is 2 and thickness is 3, the lines will be 1.5 pixel thick in aseprite",
        default=1.0)

    use_sync_armory: bpy.props.BoolProperty(
        name="Generate Armory Sprites",
        description="Create and update sprite sheets and sprite actions far Armory engine (in material tab) alongside pribabase animations",
        default=False)

    # stub to show in the animation panel instead of the object property when it's absent
    frame_stub: bpy.props.IntProperty(
        name="Frame",
        description="Animation frame, uses the same numbering as timeline in Aseprite",
        default=0,
        min=0,
        max=0)


_enum_tag_action_items = []
def _enum_tag_actions(self, context):
    global _enum_tag_action_items
    if not context:
        return []
    obj = context.active_object
    # TODO icons?
    # tag actions
    idx = 0
    actions = [("__none__", "", "", 'BLANK1', idx)] # empty list item
    for a in bpy.data.actions:
        idx += 1
        if a.sb_props.sprite == obj.sb_props.animation:
            if a.sb_props.tag == "__loop__":
                actions.append((a.name, "*Loop*", "Playback section in Aseprite", 'SEQUENCE', idx))
            elif a.sb_props.tag == "__view__":
                actions.append((a.name, "*View*", "Current frame in aseprite, behaves the same as non-animated mode", 'HIDE_OFF', idx))
            elif a.sb_props.tag:
                actions.append((a.name, a.sb_props.tag, "Tag Action", 'KEYFRAME', idx))
    # add current action
    if context.active_object.animation_data and context.active_object.animation_data.action and \
            context.active_object.animation_data.action.sb_props.sprite != obj.sb_props.animation:
        a = context.active_object.animation_data.action
        actions.insert(1, (a.name, a.name, "Current non-sprite action of this object", 'ACTION', idx))
    _enum_tag_action_items = actions
    return _enum_tag_action_items

def _set_animation_tag(self, val):
    name = next(it[0] for it in _enum_tag_action_items if it[4] == val)
    self.id_data.animation_data.action = bpy.data.actions[name] if name != "__none__" else None


class SB_ObjectProperties(bpy.types.PropertyGroup):
    animation: bpy.props.PointerProperty(
        name="Animation",
        description="Image used for UV animation. The image stores the data. Can be None",
        type=bpy.types.Image,
        options={'HIDDEN'})
    
    animation_tag_setter: bpy.props.EnumProperty(
        name="Tag",
        description="Shortcut for changing the action to current animation tags",
        options={'SKIP_SAVE'},
        items=_enum_tag_actions,
        get=lambda self : next((it[4] for it in _enum_tag_action_items if self.id_data.animation_data and self.id_data.animation_data.action 
                and self.id_data.animation_data.action.name == it[0]), 0),
        set=_set_animation_tag)


class SB_ImageProperties(bpy.types.PropertyGroup):
    """Pribambase image-related data"""

    source: bpy.props.StringProperty(
        name="Sprite",
        description="The file from which the image was created, and that will be synced with this image",
        subtype='FILE_PATH')
    
    source_abs:bpy.props.StringProperty(
        name="Sprite Path",
        description="Absolute and normalized source path",
        subtype='FILE_PATH',
        get=lambda self: os.path.normpath(bpy.path.abspath(self.source)) if self.source and self.source.startswith("//") else self.source)

    sheet: bpy.props.PointerProperty(
        name="Sheet",
        description="Spritesheet that stores animation frames",
        type=bpy.types.Image)

    frame: bpy.props.IntProperty(
        name="Frame Number",
        description="Index of the image in the spritesheet. Starts at 0",
        options={'HIDDEN'})

    sync_flags: bpy.props.EnumProperty(
        name="Sync Flags",
        description="Sync related flags passed to Aseprite with texture list",
        items=(('SHEET', "All Frames", "Send all frames via spritesheet"),
            ('SHOW_UV', "Show UV", "Sync UV changes to sprite"),
            ('LAYERS', "Layers", "Separate sprite layers"),),
        options={'ENUM_FLAG'})

    needs_save: bpy.props.BoolProperty(
        name="Freshly created",
        description="Used internally to save the image after the (first) update from Aseprite, to avoid issues caused by resetting to empty image",
        default=False)

    is_layer: bpy.props.BoolProperty(
        name="Layer",
        description="Flag if the image is a layer",
        default=False)

    # Spritesheet-specific props
    is_sheet: bpy.props.BoolProperty(
        name="Spritesheet",
        description="Flag if the image is a spritesheet",
        default=False)
    
    animation_length: bpy.props.IntProperty(
        name="Animation Length",
        description="Number of frames in the Aseprite's timeline. Can be higher than the number of frames in the spritesheet due to repeats",
        default=1)

    sheet_size: bpy.props.IntVectorProperty(
        name="Size",
        description="Spritesheed size in frames",
        size=2,
        default=(1, 1),
        min=1)
        
    sheet_start: bpy.props.IntProperty(
        name="Start",
        description="First frame number",
        options={'HIDDEN'})

    
    def source_set(self, source, relative:bool=None):
        """
        Set source as relative/absolute path according to relative path setting. Use every time when assigning sources automatically, 
        and never for user interaction. If relative is not specified but possible, it's picked automatically based on blender prefs."""
        if not source:
            self.source = ""
        elif (relative or (relative is None and addon.prefs.use_relative_path)) and bpy.data.filepath: # need to check for None explicitly because bool
            try:
                self.source = bpy.path.relpath(source)
            except ValueError:
                self.source = os.path.normpath(source)
        else:
            self.source = os.path.normpath(source)

    @property
    def sync_name(self):
        img = self.id_data
        fp = img.filepath
        name = img.name

        if img.sb_props.source:
            name = os.path.normpath(img.sb_props.source_abs)

        elif not img.packed_file and fp:
            name = os.path.normpath(bpy.path.abspath(fp) if fp.startswith("//") else fp)

        return name


class SB_ShaderNodeTreeProperties(bpy.types.PropertyGroup):
    """Pribambase node-group-related data"""

    source: bpy.props.StringProperty(
        name="Sprite",
        description="The file from which the image was created, and that will be synced with this image",
        subtype='FILE_PATH')
    
    source_abs:bpy.props.StringProperty(
        name="Sprite Path",
        description="Absolute and normalized source path",
        subtype='FILE_PATH',
        get=lambda self: os.path.normpath(bpy.path.abspath(self.source)) if self.source and self.source.startswith("//") else self.source)
    
    size:bpy.props.IntVectorProperty(
        name="Size",
        description="Dimensions of the sprite in pixels. Individual images can be different from that",
        size=2)

    sync_flags: bpy.props.EnumProperty(
        name="Sync Flags",
        description="Sync related flags passed to Aseprite with texture list",
        items=(('SHEET', "All Frames", "Send all frames via spritesheet"),
            ('SHOW_UV', "Show UV", "Sync UV changes to sprite"),
            ('LAYERS', "Layers", "Separate sprite layers"),),
        options={'ENUM_FLAG'})

    def source_set(self, source, relative:bool=None):
        """
        Set source as relative/absolute path according to relative path setting. Use every time when assigning sources automatically, 
        and never for user interaction. If relative is not specified but possible, it's picked automatically based on blender prefs."""
        if not source:
            self.source = ""
        elif (relative or (relative is None and addon.prefs.use_relative_path)) and bpy.data.filepath: # need to check for None explicitly because bool
            try:
                self.source = bpy.path.relpath(source)
            except ValueError:
                self.source = os.path.normpath(source)
        else:
            self.source = os.path.normpath(source)

    @property
    def sync_name(self):
        # unlike image, layer always come from a sprite
        return os.path.normpath(self.source_abs)


class SB_ActionProperties(bpy.types.PropertyGroup):
    """Pribambase action-related data"""
    
    sprite: bpy.props.PointerProperty(
        name="Sprite",
        description="Image for the sprite the action came from",
        type=bpy.types.Image)

    tag: bpy.props.StringProperty(
        name="Tag",
        description="Corresponding tag on Asperite timeline")


class SB_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    executable: bpy.props.StringProperty(
        name="Aseprite Executable",
        subtype='FILE_PATH',
        description="Path to Aseprite program. It will be launched by some Pribambase operators. If not specified, auto-detected path is used")

    port: bpy.props.IntProperty(
        name="Port",
        description="Port used by the websocket server. Aseprite plugin must have the same value to connect",
        default=34613,
        min=1025,
        max=65535)

    localhost: bpy.props.BoolProperty(
        name="Only Local Connections",
        description="Only accept connections from localhost (127.0.0.1)",
        default=True)
    
    debounce: bpy.props.FloatProperty(
        name="Debounce",
        description="Minimum time before sending an update to Aseprite after the previous one. Lower values make changes apply faster, but may cause unstable behavior",
        default=0.5)

    uv_layer:bpy.props.StringProperty(
        name="Layer Name",
        description="Name of the reference layer that will be created to display the UVs in Aseprite",
        default="UVMap")
    
    uv_sync_auto: bpy.props.BoolProperty(
        name="Sync Automatically",
        description="Automatically update UV map in Aseprite, when enabled in the sprite",
        default=True)

    use_relative_path: bpy.props.BoolProperty(
        name="Relative Paths",
        description="Changes how the file paths are stored. The addon stays consistent with Blender behavior, which can be changed in \"Preferences > Save & Load\"",
        get=lambda self: bpy.context.preferences.filepaths.use_relative_paths)
    
    whole_frames: bpy.props.BoolProperty(
        name="Round Fractional Frames",
        description="When sprite timings do not match the scene framerate, move keyframes to the nearest whole frame. Otherwise, use fractional frames to preserver timing",
        default=True)
    
    use_fake_users: bpy.props.BoolProperty(
        name="Add Fake Users",
        description="Turns on fake user for plugin-created data (images/actions/...) to protect it from disappearing after file reload. Changing this settin won't affect already existing data, only new",
        default=False)
    
    save_after_sync: bpy.props.BoolProperty(
        name="Save After Sync",
        description="Save/pack the image and reload it every time after syncing with aseprite. NOT RECOMMENDED due to potential heavy disk load - it's needed to work around blender 3.1 image update bug",
        default=False)

    executable_auto: bpy.props.StringProperty(
        name="Aseprite Executable",
        description="An auto-detected standard distribution of Aseprite (if there's any). If there's no custom path specified, it will be the one launched from Pribambase operators",
        options={'HIDDEN', 'SKIP_SAVE'},
        get=_find_aseprite)

    def template_box(self, layout, label="Box"):
        row = layout.row().split(factor=0.15)
        row.label(text=label)
        return row.box()


    def draw(self, context):
        layout = self.layout
        
        box = self.template_box(layout, label="Aseprite:")

        box.row().prop(self, "executable", text="Executable")
        row = box.row()
        row.enabled = False
        row.prop(self, "executable_auto", text="Auto-detected")
        box.row().operator("pribambase.setup")

        box = self.template_box(layout, label="UV Map:")

        box.row().prop(self, "uv_layer")
        box.row().prop(self, "uv_sync_auto")

        box = self.template_box(layout, label="Connection:")

        row = box.row()
        row.enabled = not addon.server_up
        row.prop(self, "localhost")
        row.prop(self, "port")
        box.row().prop(self, "debounce")

        if addon.server_up:
            box.row().operator("pribambase.server_stop")
        else:
            box.row().operator("pribambase.server_start")

        box = self.template_box(layout, label="Misc:")

        box.row().prop(self, "use_fake_users")
        box.row().prop(self, "save_after_sync")
        box.row().prop(self, "use_relative_path")
        box.row().prop(self, "whole_frames")