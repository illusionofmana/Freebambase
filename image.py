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

import bpy
import bmesh
import gpu
if bpy.app.version < (3, 5, 0):
    import bgl
from mathutils import Matrix
from gpu_extras.batch import batch_for_shader
import numpy as np
from os import path

from .messaging import encode
from . import util
from . import layers
from .layers import find_tree, update_color_outputs
from .addon import addon
from .util import image_nodata
from .setup import SB_OT_launch

from typing import Tuple, Generator

COLOR_MODES = [
    ('rgba', "RGBA", "32-bit color with transparency. If not sure, pick this one"),
    ('indexed', "Indexed", "Palettized image with arbitrary palette"),
    ('gray', "Grayscale", "Palettized with 256 levels of gray")]


def uv_lines(mesh:bpy.types.Mesh, only_selected=True) -> Generator[Tuple[Tuple[float, float], Tuple[float, float]], None, None]:
    """Iterate over line segments of the UV map. End points are sorted, so overlaps always have same point order."""
    # need to make a copy, otherwise uv watch will interrupt the user editing the uv map or mesh itself
    # not needed for oneshot send but if we can do it on timer, migh as well always
    mc = mesh.copy()
    bm = bmesh.new()
    try:
        bm.from_mesh(mc)
        uv = bm.loops.layers.uv.active

        # get all edges
        for face in bm.faces:
            # not shown in the UV editor, skipping
            try:
                if only_selected and not face.select_face:
                    continue
            except AttributeError:
                if only_selected and not face.select:
                    continue

            for i in range(0, len(face.loops)):
                a = face.loops[i - 1][uv].uv.to_tuple()
                b = face.loops[i][uv].uv.to_tuple()

                # sorting helps catching overlapping lines for differently directed loops
                # order doesn't really matter - just that there is one
                if a > b:
                    yield (b, a)
                else:
                    yield (a, b)
                    
    except Exception as e:
        print(e)
        
    finally:
        bm.free()
        bpy.data.meshes.remove(mc)


def launch_ase():
    if not addon.connected:
        return 'FINISHED' in bpy.ops.pribambase.launch(wait_connect=True)
    return True


class SB_OT_uv_send(bpy.types.Operator):
    bl_idname = "pribambase.uv_send"
    bl_label = "Send UV (manual)"
    bl_description = "Show UV in Aseprite"

    size: bpy.props.IntVectorProperty(
        name="Resolution",
        description="The size for the created UVMap. The image is scaled to the size of the sprite",
        size=2,
        min=1,
        max=65535,
        default=(128, 128))

    color: bpy.props.FloatVectorProperty(
        name="Color",
        description="Color to draw the UVs with",
        size=4,
        min=0.0,
        max=1.0,
        default=(0.0, 0.0, 0.0, 1.0),
        subtype='COLOR')

    weight: bpy.props.FloatProperty(
        name="Thickness",
        description="Thickness of the UV map lines at its original resolution",
        min=0,
        max=65535,
        default=1)


    @classmethod
    def poll(self, context):
        return addon.connected


    def setup_bgl(self):
        # might not be needed later on. linux driver bug or something; see #21
        bgl.glClearColor(0.0, 0.0, 0.0, 0.0)
        bgl.glClear(bgl.GL_COLOR_BUFFER_BIT)

        bgl.glEnable(bgl.GL_BLEND)
        bgl.glBlendFunc(bgl.GL_SRC_ALPHA, bgl.GL_ONE_MINUS_SRC_ALPHA)
        bgl.glLineWidth(self.weight)

        bgl.glDisable(bgl.GL_BLEND)
        bgl.glDisable(bgl.GL_LINE_SMOOTH)
        bgl.glHint(bgl.GL_LINE_SMOOTH_HINT, bgl.GL_FASTEST)


    def execute(self, context):
        w, h = self.size

        lines = self.color[0:3] + (1.0,)
        nbuf = np.zeros((h, w, 4), dtype=np.uint8)

        offscreen = gpu.types.GPUOffScreen(w, h)

        objects = [obj for obj in context.view_layer.objects if obj.select_get() and obj.type == 'MESH']
        active_obj = context.view_layer.objects.active
        if active_obj and active_obj.type == 'MESH':
            objects.append(active_obj)

        edges = set(line for obj in objects for line in uv_lines(obj.data, only_selected=not context.scene.tool_settings.use_uv_select_sync))
        coords = [c for pt in edges for c in pt]
        try: # 3.4+
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        except ValueError: # older versions
            shader = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'LINES', {"pos": coords})

        with offscreen.bind():
            with gpu.matrix.push_pop():
                # see explanation in https://blender.stackexchange.com/questions/153697/gpu-python-module-why-drawed-pixels-are-shifted-in-the-result-image
                projection_matrix = Matrix.Diagonal((2.0, -2.0, 1.0))
                projection_matrix = Matrix.Translation((-1.0 + 1.0 / w, 1.0 + 1.0 / h, 0.0)) @ projection_matrix.to_4x4()
                gpu.matrix.load_projection_matrix(projection_matrix)

                # bgl is deprecated on some platforms since 3.5, but gpu is not entirely functional
                # in earlier versions, so it's still used for old versions.
                if bpy.app.version < (3, 5, 0):
                    self.setup_bgl()
                else:
                    fb = gpu.state.active_framebuffer_get()
                    fb.clear(color=(0.0, 0.0, 0.0, 0.0))
                    gpu.state.blend_set('ALPHA')
                    gpu.state.line_width_set(self.weight)

                shader.bind()
                shader.uniform_float("color", lines)
                batch.draw(shader)

            # retrieve the texture
            if bpy.app.version < (3, 5, 0):
                # https://blender.stackexchange.com/questions/221110/fastest-way-copying-from-bgl-buffer-to-numpy-array
                buffer = bgl.Buffer(bgl.GL_BYTE, nbuf.shape, nbuf)
                bgl.glReadPixels(0, 0, w, h, bgl.GL_RGBA, bgl.GL_UNSIGNED_BYTE, buffer)
            else:
                buffer = gpu.types.Buffer('UBYTE', (w, h, 4), nbuf)
                fb.read_color(0, 0, w, h, 4, 0, 'UBYTE', data=buffer)
        
        offscreen.free()

        # send data
        msg = encode.uv_map(
            size=(w, h),
            pixels=nbuf.tobytes(),
            layer=addon.prefs.uv_layer,
            opacity=int(self.color[3] * 255))

        addon.server.send(msg)

        return {"FINISHED"}


    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class SB_OT_uv_send_ui(bpy.types.Operator):
    """Hack that forwards to `pribambase.send_uv`. Used to disable the button in the UI, but allows 
       to keep using `pribambase.send_uv` in the code for automatic sync - hence, it shouldn't fail
       at mode check. FIXME: make this less sloppy."""
    bl_idname = "pribambase.uv_send_ui"
    bl_label = "Send UV (manual)"
    bl_description = "Show UV in Aseprite"

    @classmethod
    def poll(self, context):
        return addon.connected and addon.state.uv_watch == 'NEVER'
    
    def invoke(self, context, event):
        bpy.ops.pribambase.uv_send('INVOKE_DEFAULT')
        return {'CANCELLED'}


class SB_OT_sprite_open(bpy.types.Operator):
    bl_idname = "pribambase.sprite_open"
    bl_label = "Open..."
    bl_description = "Set up a texture from a file using Aseprite"
    bl_options = {'UNDO'}


    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    relative: bpy.props.BoolProperty(name="Relative Path", description="Select the file relative to blend file")
    sheet: bpy.props.BoolProperty(name="Sheet Animation", description="If checked, sync entire animation to blender as a spritesheet image; if not, only send the current frame. Same as 'Animation' switch in Aseprite's sync popup")
    layers: bpy.props.BoolProperty(options={'HIDDEN'}, name="Separate Layers", description="If checked, sync layers to blender separately, and generate a node group to combine them; Otherwise, sync flattened sprite to a single image. Same as 'Layers' switch in Aseprite's sync popup")

    # dialog settings
    filter_glob: bpy.props.StringProperty(default="*.ase;*.aseprite;*.bmp;*.flc;*.fli;*.gif;*.ico;*.jpeg;*.jpg;*.pcx;*.pcc;*.png;*.tga;*.webp", options={'HIDDEN'})
    use_filter: bpy.props.BoolProperty(default=True, options={'HIDDEN'})


    @classmethod
    def poll(self, context):
        return addon.connected or SB_OT_launch.poll(context)


    def execute(self, context):
        if not launch_ase():
            return {'CANCELLED'}

        _, name = path.split(self.filepath)

        self.__class__._last_relative = self.relative
        
        bpy.ops.pribambase.sprite_stub(name=name, source=self.filepath, layers=self.layers, sheet=self.sheet)

        # switch to the image in the editor
        if not self.layers and context and context.area and context.area.type == 'IMAGE_EDITOR':
            img = next(i for i in bpy.data.images if i.sb_props.source_abs == self.filepath)
            context.area.spaces.active.image = img

        flags = set()
        if self.sheet:
            flags.add('SHEET')
        if self.layers:
            flags.add('LAYERS')
        msg = encode.sprite_open(name=self.filepath, flags=flags)
        addon.server.send(msg)

        return {'FINISHED'}


    def invoke(self, context, event):
        self.invoke_context = context

        # TODO  I have a feeling blender already has a solution but can't seem to find it
        if not hasattr(self.__class__, "_last_relative"):
            self.__class__._last_relative = addon.prefs.use_relative_path
        self.relative = self.__class__._last_relative

        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class SB_OT_sprite_stub(bpy.types.Operator):
    bl_description = "Prepare placeholder sprite that awaits data from aseprite later. Does not require ase connection."
    bl_idname = "pribambase.sprite_stub"
    bl_label = "Stub Sprite"
    bl_options = {'INTERNAL'}
    
    name:bpy.props.StringProperty(description="Datablock name. Shall not be empty")
    source:bpy.props.StringProperty(description="Sprite filepath or identifier. Shall not be empty")
    layers:bpy.props.BoolProperty(default=False)
    sheet:bpy.props.BoolProperty(default=False)
    path_relative:bpy.props.EnumProperty(items=(('DEFAULT', "", ""), ('RELATIVE', "", ""), ('ABSOLUTE', "", "")), default='DEFAULT')
    
    def execute(self, context):
        # TODO implement and remove
        if self.layers and self.sheet:
            raise NotImplementedError
        
        if not self.name or not self.source:
            raise RuntimeError

        created = False
        
        if self.layers:
            try:
                # we might have this image opened already
                img = next(g for g in bpy.data.node_groups if g.type == 'SHADER' and g.sb_props.source_abs == self.source)
            except StopIteration:
                # create a stub that will be filled after receiving data
                with util.pause_depsgraph_updates():
                    img = bpy.data.node_groups.new(self.name, 'ShaderNodeTree')
                    update_color_outputs(img, [])
                    created = True
        else:
            try:
                # we might have this image opened already
                img = next(i for i in bpy.data.images if i.sb_props.source_abs == self.source)
            except StopIteration:
                # create a stub that will be filled after receiving data
                with util.pause_depsgraph_updates():
                    img = bpy.data.images.new(self.name, 1, 1, alpha=True)
                    img.sb_props.needs_save = True
                    util.pack_empty_png(img)
                    created = True
        
        if created:
            if self.path_relative == 'DEFAULT':
                img.sb_props.source_set(self.source)
            else:
                img.sb_props.source_set(self.source, self.path_relative == 'RELATIVE')

        flags = set()
        if self.sheet:
            flags.add('SHEET')
        if self.layers:
            flags.add('LAYERS')
        img.sb_props.sync_flags

        return {'FINISHED'}
        

class SB_OT_sprite_new(bpy.types.Operator):
    bl_idname = "pribambase.sprite_new"
    bl_label = "New"
    bl_description = "Set up a new texture using Aseprite"
    bl_options={'UNDO'}

    sprite: bpy.props.StringProperty(
        name="Name",
        description="Name of the texture. It will also be displayed on the tab in Aseprite until you save the file",
        default="Sprite")

    size: bpy.props.IntVectorProperty(
        name="Size",
        description="Size of the created canvas",
        default=(128, 128),
        size=2,
        min=1,
        max=65535)

    mode: bpy.props.EnumProperty(
        name="Color Mode",
        description="Color mode of the created sprite",
        items=COLOR_MODES,
        default='rgba')
    
    sheet: bpy.props.BoolProperty(
        name="Sync Animation", 
        description="If checked, sync entire animation to blender as a spritesheet image; if not, only send the current frame. Same as 'Animation' switch in Aseprite's sync popup")

    layers: bpy.props.BoolProperty(
        options={'HIDDEN'}, # experimental - probably will be removed later
        name="Sync Layers", 
        description="If checked, sync layers to blender separately, and generate a node group to combine them; Otherwise, sync flattened sprite to a single image. Same as 'Layers' switch in Aseprite's sync popup")


    @classmethod
    def poll(self, context):
        return addon.connected or SB_OT_launch.poll(context)


    def execute(self, context):
        if not launch_ase():
            return {'CANCELLED'}

        if not self.sprite:
            self.report({'ERROR'}, "The sprite must have a name")
            return {'CANCELLED'}

        # create a stub that will be filled after receiving data
        with util.pause_depsgraph_updates():
            img = bpy.data.images.new(self.sprite, 1, 1, alpha=True)
            img.sb_props.needs_save = True
            util.pack_empty_png(img)
        # switch to it in the editor
        if context.area.type == 'IMAGE_EDITOR':
            context.area.spaces.active.image = img

        mode = 0
        for i,m in enumerate(COLOR_MODES):
            if m[0] == self.mode:
                mode = i
        
        flags = set()
        if self.sheet:
            flags.add('SHEET')
        if self.layers:
            flags.add('LAYERS')

        msg = encode.sprite_new(
            name=img.name,
            size=self.size,
            flags=flags,
            mode=mode)

        addon.server.send(msg)

        return {'FINISHED'}


    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class SB_OT_sprite_edit(bpy.types.Operator):
    bl_idname = "pribambase.sprite_edit"
    bl_label = "Edit"
    bl_description = "Open the file for this texture with Aseprite"


    @classmethod
    def poll(self, context):
        return (addon.connected or SB_OT_launch.poll(context)) and \
            context.area.type == 'IMAGE_EDITOR' and not image_nodata(context.edit_image)


    def execute(self, context):
        if not launch_ase():
            return {'CANCELLED'}

        img = context.edit_image
        if img.sb_props.is_sheet:
            img = next((i for i in bpy.data.images if i.sb_props.sheet == img), img)
        edit_name = img.sb_props.sync_name
        msg = None

        if path.exists(edit_name):
            msg = encode.sprite_open(name=edit_name, flags=img.sb_props.sync_flags)
        else:
            pixels = np.asarray(np.array(img.pixels) * 255, dtype=np.ubyte)
            pixels.shape = (img.size[1], img.size[0], 4)
            pixels = np.ravel(pixels[::-1,:,:])

            msg = encode.image(
                name=img.name,
                size=img.size,
                pixels=pixels.tobytes())

        addon.server.send(msg)

        return {'FINISHED'}


class SB_OT_sprite_edit_copy(bpy.types.Operator):
    bl_idname = "pribambase.sprite_edit_copy"
    bl_label = "Edit Copy"
    bl_description = "Open copy of the image in a new file in Aseprite, without syncing"


    @classmethod
    def poll(self, context):
        return (addon.connected or SB_OT_launch.poll(context)) and \
            context.area.type == 'IMAGE_EDITOR' and not image_nodata(context.edit_image)


    def execute(self, context):
        if not launch_ase():
            return {'CANCELLED'}

        img = context.edit_image
        pixels = np.asarray(np.array(img.pixels) * 255, dtype=np.ubyte)
        pixels.shape = (img.size[1], img.size[0], 4)
        pixels = np.ravel(pixels[::-1,:,:])
        msg = encode.image(name="", size=img.size, pixels=pixels.tobytes())
        addon.server.send(msg)

        return {'FINISHED'}


class SB_OT_sprite_purge(bpy.types.Operator):
    bl_label = "Purge"
    bl_idname = "pribambase.sprite_purge"
    bl_description = "Erase sprite-related data created by the plugin. Can remove unwanted animation setups"
    bl_options = {'UNDO'}


    remove_anim: bpy.props.BoolProperty(
        name="Animations", 
        description="Remove animations that use the sprite (UVWarp modifier, object property, and drivers)", 
        default=True)

    remove_actions: bpy.props.BoolProperty(
        name="Actions", 
        description="Remove generated actions and keyframes for the sprite", 
        default=True)

    remove_sheet: bpy.props.BoolProperty(
        name="Spritesheet Image", 
        description="Remove spritesheet image",
         default=True)

    remove_sprite: bpy.props.BoolProperty(
        name="Sprite Image", 
        description="Remove 'view' image. All relations to other pieces of data will be erased, so unchecking those makes IMPOSSIBLE to remove them automatically another time", 
        default=True)

    remove_nodes: bpy.props.BoolProperty(
        name="Node Group", 
        description="Remove node group of the sprite. All relations to other pieces of data will be erased, so unchecking those makes IMPOSSIBLE to remove them automatically another time", 
        default=True)
    
    remove_cels: bpy.props.BoolProperty(
        name="Layer Images", 
        description="Remove images used for separate layers", 
        default=True)


    @classmethod
    def poll(cls, context):
        if context.mode != 'PAINT_TEXTURE' or not hasattr(context, "edit_image"):
            return False
        props = context.edit_image.sb_props
        return props.is_sheet or props.sheet or props.is_layer
    
    def draw(self, context):
        row=self.layout.split(factor=.28)
        row.label(text="Remove:")
        col = row.column(align=True)
        if context.edit_image.sb_props.is_layer:
            col.prop(self, "remove_nodes")
            col.prop(self, "remove_cels")
        else:
            col.prop(self, "remove_sprite")
            col.prop(self, "remove_sheet")
            col.prop(self, "remove_anim")
            col.prop(self, "remove_actions")
    

    def execute(self, context):
        if not self.img:
            self.report({'INFO'}, "The main sprite has been already removed, along with recorded relations. Some data items may require manual removal")
        
        if self.remove_anim:
            for obj in bpy.data.objects:
                if obj.sb_props.animation == self.img:
                    if "UV Frame (Pribambase)" in obj.modifiers:
                        mod = obj.modifiers["UV Frame (Pribambase)"]
                        if mod.object_to:
                            bpy.data.objects.remove(mod.object_to)
                        obj.modifiers.remove(mod)

                    # custom property
                    try:
                        # 3.0+
                        obj.id_properties_ui("pribambase_frame").clear()
                    except AttributeError:
                        # 2.[8/9]x
                        if "_RNA_UI" in obj and "pribambase_frame" in obj["_RNA_UI"]:
                            del obj["_RNA_UI"]["pribambase_frame"]

                    if "pribambase_frame" in obj:
                        del obj["pribambase_frame"]

                    obj.sb_props.animation_remove()


        if self.remove_actions:
            for action in bpy.data.actions:
                if action.sb_props.sprite == self.img:
                    bpy.data.actions.remove(action)
        
        if self.remove_sheet and self.sheet:
                bpy.data.images.remove(self.sheet)

        if self.remove_sprite and self.img:
                bpy.data.images.remove(self.img)

        if self.is_layer:
            tree = find_tree(self.img)

            if self.remove_cels:
                for node in tree.nodes:
                    if node.type == 'TEX_IMAGE':
                        bpy.data.images.remove(node.image)

            if self.remove_nodes:
                # goes after everything else
                bpy.data.node_groups.remove(tree)

        return {'FINISHED'}


    def invoke(self, context, event):
        self.img = context.edit_image
        self.sheet = self.img.sb_props.sheet
        if self.img.sb_props.is_sheet: # user selected the spritesheet, not the "original" image
            sheet = self.img
            self.img = next((i for i in bpy.data.images if i.sb_props.sheet == sheet), None)
            self.remove_sprite = False # change default in this case

        return context.window_manager.invoke_props_dialog(self)


class SB_OT_sprite_replace(bpy.types.Operator):
    bl_description = "Replace current texture with a file using Aseprite"
    bl_idname = "pribambase.sprite_replace"
    bl_label = "Replace..."
    bl_options = {'UNDO'}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    relative: bpy.props.BoolProperty(name="Relative Path", description="Select the file relative to blend file")

    # dialog settings
    filter_glob: bpy.props.StringProperty(default="*.ase;*.aseprite;*.bmp;*.flc;*.fli;*.gif;*.ico;*.jpeg;*.jpg;*.pcx;*.pcc;*.png;*.tga;*.webp", options={'HIDDEN'})
    use_filter: bpy.props.BoolProperty(default=True, options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return (addon.connected or SB_OT_launch.poll(context)) and \
            context.area.type == 'IMAGE_EDITOR'

    def execute(self, context):
        if not launch_ase():
            return {'CANCELLED'}

        self.__class__._last_relative = self.relative
        img = context.edit_image

        if img.sb_props.is_sheet:
            img = next((i for i in bpy.data.images if i.sb_props.sheet == img), img)

        if img.sb_props.is_layer:
            img = layers.find_tree(img)

        img.sb_props.source_set(self.filepath, self.relative)
        msg = encode.sprite_open(name=self.filepath, flags=img.sb_props.sync_flags)
        addon.server.send(msg)

        return {'FINISHED'}


    def invoke(self, context, event):
        self.invoke_context = context

        # I have a feeling blender already has a solution but can't seem to find it
        if not hasattr(self.__class__, "_last_relative"):
            self.__class__._last_relative = addon.prefs.use_relative_path
        self.relative = self.__class__._last_relative

        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class SB_OT_sprite_make_animated(bpy.types.Operator):
    bl_idname = "pribambase.sprite_make_animated"
    bl_label = "Enable Animation"
    bl_description = "Mark the image as animated, same as checking Animated in aseprite popup"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return (addon.connected or SB_OT_launch.poll(context)) and \
            context.area.type == 'IMAGE_EDITOR' and context.edit_image and \
            'SHEET' not in context.edit_image.sb_props.sync_flags and not context.edit_image.sb_props.is_sheet
    
    def execute(self, context):
        if not launch_ase():
            return {'CANCELLED'}
            
        img = context.edit_image
        img.sb_props.sync_flags = {'SHEET', *img.sb_props.sync_flags}
        msg = encode.sprite_open(img.sb_props.sync_name, img.sb_props.sync_flags)
        addon.server.send(msg)
        return {'FINISHED'}


class SB_OT_sprite_reload_all(bpy.types.Operator):
    bl_idname = "pribambase.sprite_reload_all"
    bl_label = "Reload Sprites"
    bl_description = "Update data for all sprite textures from their original files"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return addon.connected or SB_OT_launch.poll(context)

    def execute(self, context):
        if not launch_ase():
            return {'CANCELLED'}
        addon.server.send(encode.peek([it for it in addon.texture_list if path.exists(it[0])]))
        return {'FINISHED'}