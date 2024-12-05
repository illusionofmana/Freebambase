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
Working with objects (mesh, material, sprites, ...)
"""

import bpy
from bpy_extras import object_utils
from os import path

from .addon import addon
from .image import COLOR_MODES
from . import util
from . import modify
from . import ase


_sprite_enum_items_ref = None

def _get_sprite_enum_items(self, context):
    # enum items reference must be stored to avoid crashing the UI
    global _sprite_enum_items_ref

    if context:
        images = (("IMG" + img.name, img.name, "") for img in bpy.data.images if not img.sb_props.is_layer and not img.sb_props.is_sheet and img.source in ('FILE', 'GENERATED'))
        trees = (("GRP" + tree.name, tree.name, "") for tree in bpy.data.node_groups if tree.type == 'SHADER' and tree.sb_props.source)
        _sprite_enum_items_ref = [*images, *trees] 
    else:
        _sprite_enum_items_ref = []
        
    return _sprite_enum_items_ref


_anim_sprite_enum_items_ref = None

def _get_anim_sprite_enum_items(self, context):
    # enum items reference must be stored to avoid crashing the UI
    global _anim_sprite_enum_items_ref
    _sprite_enum_items_ref = [(img.name, img.name, "") for img in bpy.data.images if img.sb_props.sheet] if context else []
    return _sprite_enum_items_ref


# Pretty annoying but Add SPrite operator should incorporate material creation/assignment, so goo portion of material setup will live outside the operator
_material_sprite_common_props = {    
    "two_sided": bpy.props.BoolProperty(
        name="Two-Sided",
        description="Make both sided of each face visible",
        default=False),
    
    "sheet": bpy.props.BoolProperty(
        name="Animated",
        description="Use spritesheet image in the material. Use when UV animation is set up, or will be",
        default=False),

    "blend": bpy.props.EnumProperty(name="Blend Mode", description="Imitate blending mode for the material", items=(
        ('NORM', "Normal", "", 0),
        ('ADD', "Additive", "", 1),
        ('MUL', "Multply", "", 2)), 
        default='NORM'),
        
    "sprite": bpy.props.EnumProperty(
        name="Sprite",
        description="Image to use",
        items=_get_sprite_enum_items)}


def _draw_material_props(self:bpy.types.Operator, layout:bpy.types.UILayout):
    if self.sprite[:3] == 'IMG' and bpy.data.images[self.sprite[3:]].sb_props.sheet:
        layout.prop(self, "sheet")
    layout.prop(self, "two_sided")
    layout.prop(self, "blend")


class SB_OT_material_add(bpy.types.Operator):
    bl_idname = "pribambase.material_add"
    bl_label = "New Pixel Material"
    bl_description = "Quick pixel material setup"
    bl_options = {'REGISTER', 'UNDO'}

    shading: bpy.props.EnumProperty(name="Shading", description="Material",
        items=(
            ('LIT', "Lit", "Basic material that receives lighting", 1), 
            ('SHADELESS', "Shadeless", "Emission material that works without any lighting in the scene", 2)), 
        default='LIT')
    
    assign: bpy.props.BoolProperty(name="Assign To Selected",
        description="Assign created material to selected objects. Otherwise only material is created.", 
        default=True)

    sheet: _material_sprite_common_props["sheet"]
    two_sided: _material_sprite_common_props["two_sided"]
    blend: _material_sprite_common_props["blend"]
    sprite: _material_sprite_common_props["sprite"]


    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True

        sprow = layout.row()
        sprow.prop(self, "sprite")
        if not self.sprite:
            sprow.label(text="Required", icon='ERROR')
        layout.row().prop(self, "shading", expand=True)
        _draw_material_props(self, layout)
        layout.row().prop(self, "assign")


    @classmethod
    def poll(cls, context):
        return next((True for i in bpy.data.images if not i.sb_props.is_sheet), False)
    

    def execute(self, context):
        if not self.sprite:
            self.report({'ERROR'}, "Sprite image needs to be specified. Material was not created.")
            return {'CANCELLED'}
        img_type, img_name = self.sprite[:3], self.sprite[3:]

        mat = bpy.data.materials.new(img_name)
        # create nodes
        mat.use_nodes = True
        mat.use_backface_culling = not self.two_sided
        mat.blend_method = 'CLIP'
        
        tree = mat.node_tree
        
        if img_type == 'IMG':
            img = bpy.data.images[img_name]

            if img.sb_props.sheet and self.sheet:
                img = img.sb_props.sheet

            tex = tree.nodes.new("ShaderNodeTexImage")
            tex.image = img
            tex.interpolation = 'Closest'
            tex.extension = 'CLIP'

        elif img_type == 'GRP':
            img = bpy.data.node_groups[img_name]
            tex = tree.nodes.new('ShaderNodeGroup')
            tex.node_tree = img

        else:
            raise RuntimeError()
            
        tex.location = (-500, 100)

        bsdf = next((n for n in tree.nodes if n.type == 'BSDF_PRINCIPLED'))
        bsdf.location = (-200, 250)
        try: # probably fails in older blender versions
            bsdf.inputs[0].default_value = (0, 0, 0) # Base Color
        except: # definitely fails in newer blender versions 
            bsdf.inputs[0].default_value = (0, 0, 0, 1) # Base Color

        if self.shading == 'LIT':
            tree.links.new(tex.outputs[0], bsdf.inputs[0]) # Color : Base Color
        elif self.shading == 'SHADELESS':
            bsdf.inputs[7].default_value = 0 # Specular
            tree.links.new(tex.outputs[0], bsdf.inputs[19]) # Color : Emission
        tree.links.new(tex.outputs[1], bsdf.inputs[21]) # : Alpha

        out = next((n for n in tree.nodes if n.type == 'OUTPUT_MATERIAL'))
        out.location = (300, 50)

        if self.blend == 'ADD':
            mat.blend_method = 'BLEND'
            trans = tree.nodes.new("ShaderNodeBsdfTransparent")
            trans.location = (80, 100)
            add = tree.nodes.new("ShaderNodeAddShader")
            add.location = (130, -100)
            tree.links.new(trans.outputs[0], add.inputs[0]) # BSDF
            tree.links.new(bsdf.outputs[0], add.inputs[1]) # BSDF
            tree.links.new(add.outputs[0], out.inputs[0]) # Shader : Surface

        elif self.blend == 'MUL':
            mat.blend_method = 'BLEND'
            tree.nodes.remove(bsdf)
            trans = tree.nodes.new("ShaderNodeBsdfTransparent")
            trans.location = (0, -20)
            tree.links.new(tex.outputs[0], trans.inputs[0]) # Color : Color
            tree.links.new(trans.outputs[0], out.inputs[0]) # BSDF : Surface

        if self.assign:
            for obj in context.selected_objects:
                obj.active_material = mat

        return {'FINISHED'}


    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class SB_OT_plane_add(bpy.types.Operator):
    bl_idname = "pribambase.plane_add"
    bl_label = "Add Sprite"
    bl_description = "All-in-one 2D sprite setup"
    bl_options = {'REGISTER', 'UNDO'}

    scale: bpy.props.FloatProperty(
        name="Texture Density", 
        description="In pixels per unit. Defaults to 1 pixel per 1 world grid step")

    pivot: bpy.props.FloatVectorProperty(
        name="Pivot",
        description="Placement of the origin in the texture space. (X:0, Y:0) is lower-left, (X:0.5, Y:0) is lower-middle, and so on",
        size=2,
        subtype='XYZ',
        default=(0.5,0.5))
    
    pivot_relative: bpy.props.BoolProperty(
        name="Relative Pivot Coordinates",
        description="If checked, pivot position is interpreted as UV coordinate (0 to 1), otherwise as pixels",
        default=True)
    
    facing: bpy.props.EnumProperty(
        name="Facing",
        description="Sprite orientation, follows the opposite naming to camera shortcuts, so e.g. picking Top means the sprite will be facing Top camera view",
        items=(
            ('YNEG', "Front", "Negative Y axis"),
            ('YPOS', "Back", "Positive Y axis"),
            ('XNEG', "Left", "Negative X axis"),
            ('XPOS', "Right", "Positive X axis"),
            ('ZPOS', "Top", "Positive Z axis"),
            ('ZNEG', "Bottom", "Negative Z axis"),
            ('SPH', "Look At", "Face the chosen object, usually camera, from any angle (spherical billboard)"),
            ('CYL', "Look At XY", "Face the chosen object by rotating around Z axis only (cylindrical billboard)")),
        default='YNEG')

    look_at: bpy.props.EnumProperty(
        name="Look At",
        description="Object that the billboard will be facing",
        items=(
            ('CAMERA', "Active Camera", "Current active camera"),
            ('ACTIVE', "Active Object", "Current active object"),
            ('NONE', "None", "Leave target unspecified")),
        default='CAMERA'
    )

    shading: bpy.props.EnumProperty(name="Shading", description="Material",
        items=(
            ('NONE', "None", "Do not create material", 0),
            ('LIT', "Lit", "Basic material that receives lighting", 1), 
            ('SHADELESS', "Shadeless", "Emission material that works without any lighting in the scene", 2)), 
        default='LIT')
    
    layers: bpy.props.BoolProperty(
        options={'HIDDEN'},
        name="Separate Layers", 
        description="If checked, sync layers to blender separately, and generate a node group to combine them; Otherwise, sync flattened sprite to a single image. Same as 'Layers' switch in Aseprite's sync popup",
        default=False)
    
    ## New Image
    new_image: bpy.props.BoolProperty("New Image", options={'HIDDEN'})

    new_sprite: bpy.props.StringProperty(
        name="Name",
        description="Name of the texture. It will also be displayed on the tab in Aseprite until you save the file",
        default="Sprite")

    new_size: bpy.props.IntVectorProperty(
        name="Size",
        description="Size of the created canvas",
        default=(128, 128),
        size=2,
        min=1,
        max=65535)

    new_mode: bpy.props.EnumProperty(
        name="Color Mode",
        description="Color mode of the created sprite",
        items=COLOR_MODES,
        default='rgba')
    
    ## FILE DIALOG
    from_file: bpy.props.BoolProperty("Open File", options={'HIDDEN'})
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    relative: bpy.props.BoolProperty(name="Relative Path", description="Select the file relative to blend file")
    # dialog settings
    filter_glob: bpy.props.StringProperty(default="*.ase;*.aseprite;*.bmp;*.jpeg;*.jpg;*.png", options={'HIDDEN'})
    use_filter: bpy.props.BoolProperty(default=True, options={'HIDDEN'})

    ## MATERIAL PROPS
    sheet: _material_sprite_common_props["sheet"]
    two_sided: _material_sprite_common_props["two_sided"]
    blend: _material_sprite_common_props["blend"]
    sprite: _material_sprite_common_props["sprite"]

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        
        if self.new_image:
            layout.prop(self, "new_sprite")
            layout.prop(self, "new_size")
            layout.prop(self, "new_mode")
            layout.prop(self, "sheet")
        elif self.from_file:
            layout.label(text="Sprite:")
            layout.prop(self, "sheet")
        else:
            layout.row().prop(self, "sprite")

        layout.label(text="Plane")
        layout.prop(self, "facing")
        if self.facing in ('SPH', 'CYL'):
            row = layout.row()
            row.prop(self, "look_at")
        layout.prop(self, "scale")
        layout.prop(self, "pivot")
        layout.prop(self, "pivot_relative", text="Relative")
        
        layout.label(text="Material")
        layout.row().prop(self, "shading", expand=True)
        if self.shading != 'NONE':
            _draw_material_props(self, layout)


    @classmethod
    def poll(self, context):
        return next((True for i in bpy.data.images if not i.sb_props.is_sheet), False)
    

    def execute(self, context):
        if self.new_image:
            bpy.ops.pribambase.sprite_new(
                sprite=self.new_sprite, 
                size=self.new_size, 
                mode=self.new_mode, 
                sheet=self.sheet)
            w,h = self.new_size
            img = bpy.data.images[self.new_sprite]
            self.sprite = 'IMG' + self.new_sprite

        elif self.from_file:
            if self.filepath.endswith(".ase") or self.filepath.endswith(".aseprite"):
                (w, h), _ = ase.info(self.filepath)
                img_name = path.basename(self.filepath)

                if addon.connected:
                    # open the sprite normally
                    res = bpy.ops.pribambase.sprite_open(filepath=self.filepath, relative=self.relative, sheet=self.sheet, layers=self.layers)
                    if 'CANCELLED' in res:
                        return res
                else:
                    # make a stub and wait for the user to launch Ase
                    bpy.ops.pribambase.sprite_stub(name=img_name, source=self.filepath, layers=self.layers, sheet=self.sheet)
                    self.report({'INFO'}, "Placeholder image created. Connect aseprite and open it to retrieve image data")

                if self.layers:
                    img = next(g for g in bpy.data.node_groups if g.type == 'SHADER' and g.sb_props.source_abs == self.filepath)
                    self.sprite = 'GRP' + img.name
                else:
                    img = next(i for i in bpy.data.images if i.sb_props.source_abs == self.filepath)
                    self.sprite = 'IMG' + img.name
            else:
                # blender supported
                img = bpy.data.images.load(self.filepath)
                w, h = img.size
                self.sprite = 'IMG' + img.name
            
        else:
            img_type, img_name = self.sprite[:3], self.sprite[3:]

            if img_type == 'IMG':
                img = bpy.data.images[img_name]
                w,h = img.size
            elif img_type == 'GRP':
                img = bpy.data.node_groups[img_name]
                w,h = img.sb_props.size

        # normalize to pixel coord
        px, py = self.pivot
        if self.pivot_relative:
            px *= w
            py *= h
        px = w - px

        # start with 2d uv coords, scaled to pixels
        points = []
        for u,v in [(w - px, -py), (-px, -py), (-px, h - py), (w - px, h - py)]:
            # scale to grid, flip if needed
            f = -1 if self.facing in ('XPOS', 'YNEG', 'ZPOS', 'SPH', 'CYL') else 1
            u = u * f / self.scale
            v = v / self.scale
            # now add third coord
            if self.facing in ('XPOS', 'XNEG'):
                points.append((0, u, v))
            elif self.facing in ('YPOS', 'YNEG'):
                points.append((u, 0, v))
            elif self.facing in ('ZPOS', 'SPH', 'CYL'):
                points.append((u, v, 0))
            elif self.facing == 'ZNEG':
                points.append((-u, -v, 0))

        mesh = bpy.data.meshes.new("Plane")
        mesh.from_pydata(
            vertices=points,
            edges=[(0, 1),(1, 2),(2, 3),(3, 0)],
            faces=[(0, 1, 2, 3)])
        mesh.uv_layers.new().data.foreach_set("uv", [0, 0, 1, 0, 1, 1, 0, 1])

        obj = object_utils.object_data_add(context, mesh, name="Sprite")
        if self.shading != 'NONE':
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            bpy.ops.pribambase.material_add(shading=self.shading, two_sided=self.two_sided, sheet=self.sheet, blend=self.blend, sprite=self.sprite)
        
        if isinstance(img, bpy.types.Image) and img.sb_props.sheet:
            bpy.ops.pribambase.spritesheet_rig(sprite=img.name)

        # TODO remove this
        if self.facing in ('SPH', 'CYL'):
            # Face camera
            face:bpy.types.CopyRotationConstraint = obj.constraints.new('COPY_ROTATION')
            if self.facing == 'CYL':
                face.use_x = False
                face.use_y = False

            if self.look_at == 'CAMERA':
                face.target = context.scene.camera
            elif self.look_at == 'ACTIVE':
                face.targe = context.active_object

            if self.facing == 'CYL':
                # For cylindric, also constrain rotation
                lock = obj.constraints.new('LIMIT_ROTATION')
                lock.use_limit_x = True
                lock.use_limit_y = True

        return {'FINISHED'}


    def invoke(self, context, event):
        self.scale = 1 / context.space_data.overlay.grid_scale

        if self.from_file:
            context.window_manager.fileselect_add(self)
            return {'RUNNING_MODAL'}
        else:
            return context.window_manager.invoke_props_dialog(self)


_uv_map_enum_items_ref = None
def _uv_map_enum_items(self, context):
    # enum items reference must be stored to avoid crashing the UI
    global _uv_map_enum_items_ref
    if context is None:
        _uv_map_enum_items_ref = []
    else: 
        _uv_map_enum_items_ref = [("__none__", "", "", 0)] + [(layer.name, layer.name, "", i + 1) for i,layer in enumerate(context.active_object.data.uv_layers)]
    return _uv_map_enum_items_ref
    
class SB_OT_spritesheet_rig(bpy.types.Operator):
    bl_idname = "pribambase.spritesheet_rig"
    bl_label = "Set Up Animation"
    bl_description = "Set up spritesheet UV animation for this object. Does not assign materials or textures"
    bl_options = {'UNDO'}

    uv_map: bpy.props.EnumProperty(
        name="UV Layer",
        description="UV Layer that transforms apply to",
        items=_uv_map_enum_items)
    
    update_nodes: bpy.props.BoolProperty(
        name="Update Image Nodes",
        description="Replace the image with spritesheet in Image Texture nodes of the object's material, if there's any",
        default=True)

    sprite: bpy.props.EnumProperty(
        name="Sprite",
        description="Sprite to use. Only sprites with animation sync are available",
        items=_get_anim_sprite_enum_items)


    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.prop(self, "sprite")
        layout.prop(self, "uv_map")
        layout.prop(self, "update_nodes")
    

    @classmethod
    def poll(self, context):
        # need a mesh to store modifiers these days
        return context.active_object and context.active_object.type == 'MESH' and context.active_object.select_get() \
                and next((img for img in bpy.data.images if img.sb_props.sheet), False) and not context.active_object.sb_props.animation


    def execute(self, context):
        obj:bpy.types.Object = context.active_object
        img:bpy.types.Image = bpy.data.images[self.sprite]
        if not img:
            self.report({'ERROR'}, "No sprite selected")
            return {'CANCELLED'}
        start = img.sb_props.sheet.sb_props.sheet_start

        prop_path = '["pribambase_frame"]'
        obj.sb_props.animation = img

        # create animation_data. Not having one breaks action setter shortcut
        if obj.animation_data is None:
            obj.animation_data_create()

        # custom property
        if "pribambase_frame" not in obj:
            obj["pribambase_frame"] = start

        try:
            # 3.0
            obj.id_properties_ui("pribambase_frame").update(description="Animation frame, uses the same numbering as timeline in Aseprite")
        except AttributeError:
            # 2.[8/9]x
            if "_RNA_UI" not in obj:
                obj["_RNA_UI"] = {}
            obj["_RNA_UI"]["pribambase_frame"] = { "description": "Animation frame, uses the same numbering as timeline in Aseprite"}

        # modifier
        if "UV Frame (Pribambase)" not in obj.modifiers:
            obj.modifiers.new("UV Frame (Pribambase)", "UV_WARP")
        
        uvwarp:bpy.types.UVWarpModifier = obj.modifiers["UV Frame (Pribambase)"]
        uvwarp.uv_layer = "" if self.uv_map == "__none__" else self.uv_map
        uvwarp.center = (0.0, 1.0)

        if not uvwarp.object_from:
            uvwarp.object_from = addon.uv_offset_origin
        
        if not uvwarp.object_to:
            uvwarp.object_to = bpy.data.objects.new("~PribambaseUVDriver_" + obj.name, None)
            uvwarp.object_to.use_fake_user = True
            uvwarp.object_to.parent = uvwarp.object_from
        offset = uvwarp.object_to

        modify.sheet_animation(obj, obj.sb_props.animation)

        # revive the curves if needed
        if offset.animation_data and offset.animation_data.action:
            for fcurve in offset.animation_data.action.fcurves:
                if fcurve.data_path == prop_path:
                    # It seems there's no way to clear FCURVE_DISABLED flag directly from script
                    # Seems that changing the path does that as a side effect
                    fcurve.data_path += ""
                    fcurve.update()

        offset.animation_data.drivers.update()
        offset.update_tag()

        # try updating the material
        if self.update_nodes and obj.active_material and obj.active_material.use_nodes:
            if obj.active_material.users > 1:
                # duplicate the mat so it doesn't break the rest of the objects using it
                mat_name = obj.active_material.name + " *Sheet*"
                if mat_name not in bpy.data.materials:
                    mat = obj.active_material.copy()
                    mat.name = mat_name
                obj.active_material = bpy.data.materials[mat_name]

            for node in obj.active_material.node_tree.nodes:
                if node.bl_idname == 'ShaderNodeTexImage' and node.image == img:
                    node.image = img.sb_props.sheet

        util.refresh()

        return {'FINISHED'}


    def invoke(self, context, event):
        if not next((True for img in bpy.data.images if img.sb_props.sheet), False):
            self.report({'ERROR'}, "No animated sprites in the current blendfile")
            return {'CANCELLED'}

        if not context.active_object.data.uv_layers:
            self.report({'ERROR'}, "The object must have at least one UV map")
            return {'CANCELLED'}
        
        return context.window_manager.invoke_props_dialog(self)


class SB_OT_spritesheet_unrig(bpy.types.Operator):
    bl_idname = "pribambase.spritesheet_unrig"
    bl_label = "Remove Animation"
    bl_description = "Remove modifier, drivers, and custom property created buy spritesheet UV animation"
    bl_options = {'UNDO'}

    @classmethod 
    def poll(self, context):
        try:
            return context.active_object.select_get() and context.active_object.sb_props.animation
        except (AttributeError, IndexError):
            return False
    
    def execute(self, context):
        obj = context.active_object

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

        # modifier
        if "UV Frame (Pribambase)" in obj.modifiers:
            mod = obj.modifiers["UV Frame (Pribambase)"]
            if mod.object_to:
                bpy.data.objects.remove(mod.object_to)
            obj.modifiers.remove(mod)
        
        # animation
        obj.sb_props.animation = None

        return {'FINISHED'}