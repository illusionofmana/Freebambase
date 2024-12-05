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

# import wheel deps
import sys
import os.path as path
from glob import glob
thirdparty = path.join(path.dirname(__file__), "thirdparty", "*.whl")
sys.path += glob(thirdparty)

from bpy.app.handlers import persistent

from .async_loop import *
from .props import *
from .sync import *
from .image import *
from .ui import *
from .object import *
from .animation import *
from .modify import *
from .util import *
from .setup import *
from .addon import addon


bl_info = {
    "name": "Pribambase",
    "author": "lampysprites",
    "description": "Paint pixelart textures in Blender using Aseprite",
    "blender": (2, 80, 0),
    "version": (2, 6, 1),
    "category": "Paint"
}


classes = (
    # Property types
    SB_State,
    SB_Preferences,
    SB_ObjectProperties,
    SB_ImageProperties,
    SB_ShaderNodeTreeProperties,
    SB_ActionProperties,
    # Operators
    SB_OT_server_start,
    SB_OT_server_stop,
    SB_OT_uv_send,
    SB_OT_uv_send_ui,
    SB_OT_send_texture_list,
    SB_OT_sprite_stub,
    SB_OT_sprite_open,
    SB_OT_sprite_new,
    SB_OT_sprite_edit,
    SB_OT_sprite_edit_copy,
    SB_OT_sprite_replace,
    SB_OT_sprite_make_animated,
    SB_OT_sprite_purge,
    SB_OT_material_add,
    SB_OT_plane_add,
    SB_OT_sprite_reload_all,
    SB_OT_grid_set,
    SB_OT_update_image,
    SB_OT_update_image_layers,
    SB_OT_update_spritesheet,
    SB_OT_update_frame,
    SB_OT_new_texture,
    SB_OT_action_preview_set,
    SB_OT_action_preview_clear,
    SB_OT_spritesheet_rig,
    SB_OT_spritesheet_unrig,
    SB_OT_report,
    SB_OT_setup,
    SB_OT_launch,
    # Panels
    SB_PT_link,
    SB_PT_edit,
    SB_PT_uv_draw,
    SB_PT_animation,
    SB_PT_sprite,
    SB_PT_sprite_edit,
    # Menus
    SB_MT_sprite
)


addon_keymaps = []


def register():
    # async thread
    async_loop.setup_asyncio_executor()

    # types
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)

    # custom data
    bpy.types.Scene.sb_state = bpy.props.PointerProperty(type=SB_State)
    bpy.types.Image.sb_props = bpy.props.PointerProperty(type=SB_ImageProperties)
    bpy.types.Action.sb_props = bpy.props.PointerProperty(type=SB_ActionProperties)
    bpy.types.Object.sb_props = bpy.props.PointerProperty(type=SB_ObjectProperties)
    bpy.types.ShaderNodeTree.sb_props = bpy.props.PointerProperty(type=SB_ShaderNodeTreeProperties)
    
    # add menu items
    try:
        editor_menus = bpy.types.IMAGE_MT_editor_menus
    except AttributeError:
        editor_menus = bpy.types.MASK_MT_editor_menus
    editor_menus.append(SB_MT_sprite.header_draw)

    # hotkeys
    try:
        kcfg = bpy.context.window_manager.keyconfigs.addon
        # register empty item
        key = lambda km,idname: addon_keymaps.append((km, km.keymap_items.new(idname=idname, type='NONE', value='PRESS')))

        km_screen = kcfg.keymaps.new(name="Window", space_type='EMPTY')
        key(km_screen, "pribambase.server_start")
        key(km_screen, "pribambase.server_stop")
        key(km_screen, "pribambase.grid_set")
        key(km_screen, "pribambase.action_preview_set")
        key(km_screen, "pribambase.action_preview_clear")
        key(km_screen, "pribambase.sprite_reload_all")

        km_v3d = kcfg.keymaps.new(name="3D View", space_type='VIEW_3D')
        key(km_v3d, "pribambase.plane_add")
        key(km_v3d, "pribambase.material_add")
        key(km_v3d, "pribambase.spritesheet_rig")

        km_img = kcfg.keymaps.new(name="Image", space_type='IMAGE_EDITOR')
        key(km_img, "pribambase.uv_send")
        key(km_img, "pribambase.sprite_open")
        key(km_img, "pribambase.sprite_new")
        key(km_img, "pribambase.sprite_edit")
        key(km_img, "pribambase.sprite_edit_copy")
        key(km_img, "pribambase.sprite_purge")
        key(km_img, "pribambase.sprite_replace")
        key(km_img, "pribambase.sprite_make_animated")
    except Exception as e:
        # not sure when it fails (headless launch?) but keymaps don't affect functionality, let's ignore and continue
        bpy.ops.pribambase.report(message_type='WARNING', message=f"Failed to register addon keymap: {str(e)}")


    # execute async loop
    # delay is just in case something else happens at startup
    # `persistent` protects the timer if the user loads a file before it fires
    bpy.app.timers.register(start, first_interval=0.5, persistent=True)


def unregister():
    if addon.server_up:
        addon.stop_server()

    if bpy.app.timers.is_registered(start):
        bpy.app.timers.unregister(start)

    if sb_on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(sb_on_load_post)

    if sb_on_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(sb_on_load_pre)

    if sb_on_save_post in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(sb_on_save_post)

    if sb_on_depsgraph_update_post in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(sb_on_depsgraph_update_post)

    try:
        editor_menus = bpy.types.IMAGE_MT_editor_menus
    except AttributeError:
        editor_menus = bpy.types.MASK_MT_editor_menus
    editor_menus.remove(SB_MT_sprite.header_draw)

    global addon_keymaps
    for km,item in addon_keymaps:
        km.keymap_items.remove(item)
    addon_keymaps = []

    del bpy.types.Scene.sb_state
    del bpy.types.Image.sb_props
    del bpy.types.Action.sb_props
    del bpy.types.Object.sb_props
    del bpy.types.ShaderNodeTree.sb_props

    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)


# hash for the set of image sources/names that is used to check if new images were added
_images_hv = 0


@persistent
def start():
    # hasn't been called for already loaded file
    sb_on_load_post(None)

    if sb_on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(sb_on_load_post)

    if sb_on_load_pre not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(sb_on_load_pre)

    if sb_on_save_post not in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.append(sb_on_save_post)

    if sb_on_depsgraph_update_post not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(sb_on_depsgraph_update_post)


@persistent
def sb_on_load_post(scene):
    global _images_hv
    _images_hv = hash(frozenset(img.sb_props.sync_name for img in bpy.data.images))

    # these settings aren't supposed to persist but 'SKIP_SAVE' flag didn't do anyhitng so let's clear them manually if needed
    if addon.state.action_preview_enabled:
        bpy.context.scene.use_preview_range = False
    addon.state.action_preview = None
    addon.state.action_preview_enabled = False
    

@persistent
def sb_on_load_pre(scene):
    if addon.server_up:
        addon.stop_server()


@persistent
def sb_on_save_post(scene):
    if addon.server_up:
        bpy.ops.pribambase.send_texture_list()


@persistent
def sb_on_depsgraph_update_post(scene):
    global _images_hv

    dg = bpy.context.evaluated_depsgraph_get()

    if dg.id_type_updated('IMAGE'):
        imgs = frozenset(img.sb_props.sync_name for img in bpy.data.images)
        hv = hash(imgs)

        if _images_hv != hv:
            _images_hv = hv
            if addon.server_up:
                addon.server.send(encode.texture_list(addon.state.identifier, addon.texture_list))
