import bpy
from bpy.app.translations import pgettext as tr

import numpy as np
from itertools import chain
from typing import List, Tuple

from .ase import BlendMode
from .util import pack_empty_png


def create_node_helper():
    """Create helper node group. It calculates the mask of the cel, and does gamma correction for mixing later"""        
    tree:bpy.types.ShaderNodeTree = bpy.data.node_groups.new("PribambaseLayersHelper", 'ShaderNodeTree')

    tree.inputs.new('NodeSocketVector', tr("UV"))
    tree.inputs.new('NodeSocketColor', tr("Color"))
    tree.inputs.new('NodeSocketFloat', tr("Alpha"))
    tree.inputs.new('NodeSocketFloat', tr("Layer Opacity"))

    tree.outputs.new('NodeSocketColor', tr("Color"))
    tree.outputs.new('NodeSocketFloat', tr("Alpha"))

    group_in = tree.nodes.new('NodeGroupInput')
    group_in.location = (0, 0)
    group_out = tree.nodes.new('NodeGroupOutput')
    group_out.location = (1200, 0)

    # mask rectangle (0,1)x(0,1) - clear texture stretching outside of the cel
    xyz = tree.nodes.new('ShaderNodeSeparateXYZ')
    xyz.location = (300, 100)

    cmp_x:bpy.types.ShaderNodeMath = tree.nodes.new('ShaderNodeMath')
    cmp_x.location = (450, 200)
    cmp_y:bpy.types.ShaderNodeMath = tree.nodes.new('ShaderNodeMath')
    cmp_y.location = (450, 100)
    cmp_x.operation = cmp_y.operation = 'COMPARE'
    cmp_x.inputs[0].default_value = cmp_y.inputs[0].default_value = 0.5
    cmp_x.inputs[1].default_value = cmp_y.inputs[1].default_value = 0.5

    cmp_and:bpy.types.ShaderNodeMath = tree.nodes.new('ShaderNodeMath')
    cmp_and.location = (600, 100)
    cmp_and.operation = 'MINIMUM'

    # Using string key breaks some localizations (i.e. ZH), so use indices for ins/outs everywhere!
    tree.links.new(group_in.outputs[0], xyz.inputs[0]) # UV : Vector
    tree.links.new(xyz.outputs[0], cmp_x.inputs[0]) # X : Value
    tree.links.new(xyz.outputs[1], cmp_y.inputs[1]) # Y : Value
    tree.links.new(cmp_x.outputs[0], cmp_and.inputs[0]) # Value : Arg0
    tree.links.new(cmp_y.outputs[0], cmp_and.inputs[1]) # Value : Arg1

    # mix aplhas
    a_ch:bpy.types.ShaderNodeMath = tree.nodes.new('ShaderNodeMath')
    a_ch.location = (750, 100)
    a_layer:bpy.types.ShaderNodeMath = tree.nodes.new('ShaderNodeMath')
    a_layer.location = (900, 100)
    a_ch.operation = a_layer.operation = 'MULTIPLY'

    tree.links.new(cmp_and.outputs[0], a_ch.inputs[0]) # Value : Arg0
    tree.links.new(group_in.outputs[1], a_ch.inputs[1]) # Alpha : Arg1
    tree.links.new(a_ch.outputs[0], a_layer.inputs[0]) # Value : Arg0
    tree.links.new(group_in.outputs[3], a_layer.inputs[1]) # Layer Opacity : Arg1
    tree.links.new(a_layer.outputs[0], group_out.inputs[1]) # Value : Alpha

    # correct color gamma so that mix node blending works same as in ase
    # after blending it should be corrected back
    gamma_out = add_gamma_nodes(tree, 300, -100, 1/2.2, group_in.outputs[1]) # ... : Color
    tree.links.new(gamma_out, group_out.inputs[0]) # ... : Color


def create_node_exclusion():
    """Create mix node equivalent for exclusion blend mode in ase. The formula for each channel is `C_res = C_src + C_dst - 2*C_src*C_dst`"""        
    tree:bpy.types.ShaderNodeTree = bpy.data.node_groups.new("PribambaseMixExclusion", 'ShaderNodeTree')

    tree.inputs.new('NodeSocketFloat', tr("Fac"))
    tree.inputs.new('NodeSocketColor', tr("Color1"))
    tree.inputs.new('NodeSocketColor', tr("Color2"))

    tree.outputs.new('NodeSocketColor', tr("Color"))

    group_in = tree.nodes.new('NodeGroupInput')
    group_in.location = (0, 0)
    group_out = tree.nodes.new('NodeGroupOutput')
    group_out.location = (850, 0)

    fac:bpy.types.ShaderNodeVectorMath = tree.nodes.new('ShaderNodeVectorMath')
    fac.operation = 'SCALE'
    fac.location = (250, 0)
    add:bpy.types.ShaderNodeVectorMath = tree.nodes.new('ShaderNodeVectorMath')
    add.operation = 'ADD'
    add.location = (450, -150)
    mul:bpy.types.ShaderNodeVectorMath = tree.nodes.new('ShaderNodeVectorMath')
    mul.operation = 'MULTIPLY'
    mul.location = (450, 0)
    combine:bpy.types.ShaderNodeVectorMath = tree.nodes.new('ShaderNodeVectorMath')
    combine.operation = 'MULTIPLY_ADD'
    combine.inputs[1].default_value = (-2, -2, -2)
    combine.location = (650, 0)

    tree.links.new(group_in.outputs[0], fac.inputs[1]) # Fac : Scale
    tree.links.new(group_in.outputs[2], fac.inputs[0]) # Color2 : Vector
    tree.links.new(group_in.outputs[1], mul.inputs[0]) # Color1 : Arg0
    tree.links.new(fac.outputs[0], mul.inputs[1]) # Vector : Arg1
    tree.links.new(group_in.outputs[1], add.inputs[0]) # Color1 : Arg0
    tree.links.new(fac.outputs[0], add.inputs[1]) # Vector : Arg1
    tree.links.new(mul.outputs[0], combine.inputs[0]) # Vector : Arg0
    tree.links.new(add.outputs[0], combine.inputs[2]) # Vector: Arg2
    tree.links.new(combine.outputs[0], group_out.inputs[0]) # Vecor : Color


def update_color_outputs(tree:bpy.types.ShaderNodeTree, groups:List[Tuple]):
    """Create or assure Color and Alpha outputs for the entire sprite and each top-level group. Moves existing ones of the same name in order to preserve connections."""
    outs = tree.outputs

    # first iteration checks first two outputs being sprite's combined color and alpha
    # after that, extra two per group, same order as the groups
    for i, (layer_name,) in enumerate(chain([("",)], groups)):
        # first two are the sprite's color and alpha
        color_name, alpha_name = (f"{layer_name} Color", f"{layer_name} Alpha") if layer_name else ("Color", "Alpha")

        color_idx = next((i for i,out in enumerate(outs) if out.name == color_name), -1)
        color_goes = 2 * i
        if color_idx < 0:
            color_idx = len(outs)
            outs.new('NodeSocketColor', tr(color_name))
            
        if color_idx != color_goes:
            outs.move(color_idx, color_goes)
        
        alpha_idx = next((i for i,out in enumerate(outs) if out.name == alpha_name), -1)
        alpha_goes = 2 * i + 1
        if alpha_idx < 0:
            alpha_idx = len(outs)
            outs.new('NodeSocketFloat', tr(alpha_name))

        if alpha_idx != alpha_goes:
            outs.move(alpha_idx, alpha_goes)
    
    # at this point, we swapped first `2 + 2*len(groups)` outputs
    # ones remaining are no longer in the sprite and should be removed
    end = 2 + 2 * len(groups)
    for _ in range(end, len(outs)):
        outs.remove(outs[end]) # del is not implemented ( ' _ ' )


def add_layer_image_nodes(tree:bpy.types.ShaderNodeTree, node_x:float, node_y:float, uv_node:bpy.types.ShaderNodeUVMap, \
    x:float, y:float, w:float, h:float, image:bpy.types.Image, opacity:float) \
        -> Tuple[bpy.types.NodeSocketColor, bpy.types.NodeSocketFloat]: # outputs for color and alpha
    """Transform and mask cel image. NOTE this function accepts normalized x/y/w/h/opacity, as in (0.0, 1.0) range"""
    mapping:bpy.types.ShaderNodeMapping = tree.nodes.new('ShaderNodeMapping')
    mapping.vector_type = 'TEXTURE'
    mapping.inputs['Location'].default_value = (x, y, 0.0)
    mapping.inputs['Scale'].default_value = (w, h, 0.0)
    mapping.location = (node_x, node_y)

    image_node:bpy.types.ShaderNodeTexImage = tree.nodes.new('ShaderNodeTexImage')
    image_node.location = (node_x + 200, node_y)
    image_node.image = image
    image_node.interpolation = 'Closest'

    helper:bpy.types.ShaderNodeGroup = tree.nodes.new('ShaderNodeGroup')
    helper.location = (node_x + 500, node_y)
    helper.node_tree = bpy.data.node_groups["PribambaseLayersHelper"]
    helper.inputs[3].default_value = opacity # Layer Opacity

    tree.links.new(uv_node.outputs[0], mapping.inputs[0]) # UV : Vector
    tree.links.new(mapping.outputs[0], helper.inputs[0]) # Vector : UV
    tree.links.new(mapping.outputs[0], image_node.inputs[0]) # Vector : Vector
    tree.links.new(image_node.outputs[0], helper.inputs[1]) # Color : Color
    tree.links.new(image_node.outputs[1], helper.inputs[2]) # Alpha : Alpha

    return (helper.outputs[0], helper.outputs[1]) # Color: Alpha


def add_mix_nodes(tree:bpy.types.ShaderNodeTree, node_x:float, node_y:float, blend_mode:str, \
    color1:bpy.types.NodeSocketColor, alpha1:bpy.types.NodeSocketFloat, \
    color2:bpy.types.NodeSocketColor, alpha2:bpy.types.NodeSocketFloat) \
        -> Tuple[bpy.types.NodeSocketColor, bpy.types.NodeSocketFloat]: # outputs for color and alpha
    """Nodes for mixing RGB components and alpha"""

    mix:bpy.types.ShaderNode = None
    if blend_mode == 'EXCLUSION':
        if "PribambaseMixExclusion" not in bpy.data.node_groups:
            create_node_exclusion()
        mix = tree.nodes.new('ShaderNodeGroup')
        mix.node_tree = bpy.data.node_groups["PribambaseMixExclusion"]
    else:
        mix = tree.nodes.new('ShaderNodeMixRGB')
        mix.blend_type = blend_mode
    mix.location = (node_x, node_y + 200)

    inv:bpy.types.ShaderNodeMath = tree.nodes.new('ShaderNodeMath')
    inv.location = (node_x, node_y)
    inv.operation = 'SUBTRACT'
    inv.inputs[0].default_value = 1.0

    mul:bpy.types.ShaderNodeMath = tree.nodes.new('ShaderNodeMath')
    mul.location = (node_x + 200, node_y)
    mul.operation = 'MULTIPLY'

    add:bpy.types.ShaderNodeMath = tree.nodes.new('ShaderNodeMath')
    add.location = (node_x + 400, node_y)
    add.operation = 'ADD'
    add.use_clamp = True

    tree.links.new(color1, mix.inputs[1]) # : Color1
    tree.links.new(alpha1, inv.inputs[1])
    tree.links.new(alpha1, add.inputs[1])
    tree.links.new(color2, mix.inputs[2]) # : Color2
    tree.links.new(alpha2, mix.inputs[0]) # : Fac
    tree.links.new(alpha2, mul.inputs[1])
    tree.links.new(inv.outputs[0], mul.inputs[0]) # Value :
    tree.links.new(mul.outputs[0], add.inputs[0]) # Value :

    return (mix.outputs[0], add.outputs[0]) # Color, Value


def add_gamma_nodes(tree:bpy.types.ShaderNodeTree, node_x:float, node_y:float, gamma:float, color_in:bpy.types.NodeSocketColor):
    """Per-component vector exponent"""

    sep:bpy.types.ShaderNodeSeparateRGB = tree.nodes.new('ShaderNodeSeparateRGB')
    sep.location = (node_x, node_y)
    comb:bpy.types.ShaderNodeCombineRGB = tree.nodes.new('ShaderNodeCombineRGB')
    comb.location = (node_x + 300, node_y)
    math_x:bpy.types.ShaderNodeMath = tree.nodes.new('ShaderNodeMath')
    math_x.location = (node_x + 150, node_y)
    math_y:bpy.types.ShaderNodeMath = tree.nodes.new('ShaderNodeMath')
    math_y.location = (node_x + 150, node_y - 50)
    math_z:bpy.types.ShaderNodeMath = tree.nodes.new('ShaderNodeMath')
    math_z.location = (node_x + 150, node_y - 100)
    math_x.hide = math_y.hide = math_z.hide = True

    math_x.operation = math_y.operation = math_z.operation = 'POWER'
    math_x.inputs[1].default_value = math_y.inputs[1].default_value = math_z.inputs[1].default_value = gamma

    tree.links.new(color_in, sep.inputs[0]) # : Image
    tree.links.new(sep.outputs[0], math_x.inputs[0]) # R :
    tree.links.new(sep.outputs[1], math_y.inputs[0]) # G :
    tree.links.new(sep.outputs[2], math_z.inputs[0]) # B :
    tree.links.new(math_x.outputs[0], comb.inputs[0]) # Value : R
    tree.links.new(math_y.outputs[0], comb.inputs[1]) # Value : G
    tree.links.new(math_z.outputs[0], comb.inputs[2]) # Value : B

    return comb.outputs[0] # Image


def update_layers(tree:bpy.types.ShaderNodeTree, sprite_name:str, sprite_width:int, sprite_height:int, groups:List, layers:List):
    if "PribambaseLayersHelper" not in bpy.data.node_groups:
        create_node_helper()

    # this must happen before clearing the node tree. the function checks the existing nodes
    images = update_images(tree, sprite_name, layers)

    tree.nodes.clear()
    update_color_outputs(tree, groups)

    group_out = tree.nodes.new('NodeGroupOutput')
    group_out.location = (3250, 0)

    uv:bpy.types.ShaderNodeUVMap = tree.nodes.new('ShaderNodeUVMap')

    # cels
    last_out_color = None
    last_out_alpha = None
    last_group_color = None
    last_group_alpha = None

    for i in range(len(layers)):
        _idx, blend, opacity, group, x, y, w, h, _name, _pixels = layers[i]
        layer_image = images[i]

        node_y = i * -500

        mix = BlendMode(blend).toMix()
        x, y, w, h = x / sprite_width, y / sprite_height, w / sprite_width, h / sprite_height
        y = (1.0 - y - h)
    
        layer_out_color, layer_out_alpha = add_layer_image_nodes(tree, 300, node_y, uv, \
            x, y, w, h, layer_image, opacity / 255)
        
        # top level layer
        if last_out_color:
            last_out_color, last_out_alpha = add_mix_nodes(tree, 1100, node_y + 150, mix, \
                last_out_color, last_out_alpha, layer_out_color, layer_out_alpha)
        else:
            # bottomest layer in the sprite
            last_out_color = layer_out_color
            last_out_alpha = layer_out_alpha

        # mix groups separately
        if group != 0:
            next_group = layers[i + 1][3] if i < len(layers) - 1 else -1

            if last_group_color:
                last_group_color, last_group_alpha = add_mix_nodes(tree, 1800, node_y + 150, mix, \
                    last_group_color, last_group_alpha, layer_out_color, layer_out_alpha)
            else:
                last_group_color = layer_out_color
                last_group_alpha = layer_out_alpha
            
            if group != next_group:
                (group_name, ) = groups[group - 1]
                gamma_out = add_gamma_nodes(tree, 2500, (group + 1) * -200, 2.2, last_group_color)
                tree.links.new(gamma_out, group_out.inputs[f"{group_name} Color"])
                tree.links.new(last_group_alpha, group_out.inputs[f"{group_name} Alpha"])
                last_group_color = None
                last_group_alpha = None

    gamma_out = add_gamma_nodes(tree, 2500, 0, 2.2, last_out_color)
    tree.links.new(gamma_out, group_out.inputs[0]) # Color
    tree.links.new(last_out_alpha, group_out.inputs[1]) # Alpha

    tree.nodes.update()
    tree.links.update()
    tree.update_tag()


def update_images(tree:bpy.types.ShaderNodeTree, sprite_name:str, layers:List[Tuple]) -> List[bpy.types.Image]:
    """Update pixel data and return list of the images in the same order as layers. 
        Will Image Texture nodes inside the tree for existing images, and remove those that aren't in the list of layers."""
    basename = bpy.path.basename(sprite_name)
    images = []
    # later, remove from the set the ones that are still in use
    unused_images = set(node.image for node in tree.nodes if node.type == 'TEX_IMAGE' and node.image)

    for _idx, _blend, _opacity, _group, _x, _y, w, h, name, pixels in layers:
        # image data
        image = None
        image_name = f"{basename}:{name}"
        image_created = False

        if image_name not in bpy.data.images:
            image = bpy.data.images.new(image_name, 1, 1, alpha=True)
            image.sb_props.needs_save = True
            pack_empty_png(image)
            image_created = True
        else:
            image = bpy.data.images[image_name]
        
        image.sb_props.is_layer = True
        
        try:
            unused_images.remove(image)
        except KeyError:
            pass

        if pixels:
            if image.size != (w, h):
                image.scale(w, h)
            
            pixels = np.float32(pixels) / 255.0
            # flip y axis ass backwards
            pixels.shape = (h, pixels.size // h)
            pixels = pixels[::-1,:].ravel()

            # change blender data
            try:
                # version >= 2.83; this is much faster
                image.pixels.foreach_set(pixels)
            except AttributeError:
                # version < 2.83
                image.pixels[:] = pixels
        else:
            if not image_created:
                image.scale(1, 1)
                image.pixels.foreach_set([0.0, 0.0, 0.0, 0.0])

        image.update()
        image.update_tag()

        images.append(image)
    
    for image in unused_images:
        bpy.data.images.remove(image)

    return images


def find_tree(layer:bpy.types.Image) -> bpy.types.ShaderNodeTree:
    return next((tree \
        for tree in bpy.data.node_groups if tree.type == 'SHADER' \
            for node in tree.nodes if node.type == 'TEX_IMAGE' and node.image == layer), None)