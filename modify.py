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
Operators used internally to modify blender data during sync.
"""

import bpy
import numpy as np
from typing import Collection, Tuple
from . import util
from .util import ModalExecuteMixin, image_nodata
from .addon import addon
from .layers import update_layers


_update_image_args = None
def image(w, h, name, frame, flags, pixels):
    # NOTE this operator removes animation flag from image
    global _update_image_args
    _update_image_args = w, h, name, frame, flags, pixels
    bpy.ops.pribambase.update_image()

class SB_OT_update_image(bpy.types.Operator, ModalExecuteMixin):
    bl_idname = "pribambase.update_image"
    bl_label = "Update Image"
    bl_description = ""
    bl_options = {'UNDO_GROUPED', 'INTERNAL'}
    bl_undo_group = "pribambase.update_image"

    def modal_execute(self, context):
        """Replace the image with pixel data"""
        img = None
        w, h, name, frame, flags, pixels = self.args

        # convert data to blender accepted floats
        pixels = np.float32(pixels) / 255.0
        # flip y axis ass backwards
        pixels.shape = (h, pixels.size // h)
        pixels = pixels[::-1,:].ravel()

        for img in bpy.data.images:
            if name == img.sb_props.sync_name:

                if image_nodata(img):
                    # load *some* data so that the image can be updated
                    util.pack_empty_png(img)

                if img.size != (w, h):
                    img.scale(w, h)

                if frame != -1:
                    img.sb_props.frame = frame

                resend_uv = ('SHOW_UV' not in img.sb_props.sync_flags and 'SHOW_UV' in flags) and addon.watch
                    
                img.sb_props.sync_flags = flags

                if resend_uv:
                    addon.watch.resend() # call after changing the flags

                # change blender data
                try:
                    # version >= 2.83; this is much faster
                    img.pixels.foreach_set(pixels)
                except AttributeError:
                    # version < 2.83
                    img.pixels[:] = pixels

                img.update()
                # [#12] for some users viewports do not update from update() alone
                img.update_tag()

                if addon.prefs.save_after_sync or img.sb_props.needs_save:
                    if bpy.app.version >= (4, 0, 0): # fuck whoever on blender team keeps changing call signatures
                        cor = context.copy()
                        cor["edit_image"] = img
                        with context.temp_override(**cor):
                            bpy.ops.image.save()
                            bpy.ops.image.reload()
                    else:
                        bpy.ops.image.save({"edit_image": img})
                        bpy.ops.image.reload({"edit_image": img})
                    img.sb_props.needs_save = False

        util.refresh()

        self.args = None
        global _update_image_args
        _update_image_args = None

        return {'FINISHED'}


    def execute(self, context):
        self.args = _update_image_args
        return ModalExecuteMixin.execute(self, context)


_update_layers_args = None
def image_layers(width, height, name, flags, groups, layers):
    # NOTE this operator removes animation flag from image
    global _update_layers_args
    _update_layers_args = width, height, name, flags, groups, layers
    bpy.ops.pribambase.update_image_layers()

class SB_OT_update_image_layers(bpy.types.Operator, ModalExecuteMixin):
    bl_idname = "pribambase.update_image_layers"
    bl_label = "Update Image (Layers)"
    bl_description = ""
    bl_options = {'UNDO_GROUPED', 'INTERNAL'}
    bl_undo_group = "pribambase.update_image_layers"

    def modal_execute(self, context):
        """Replace the image with pixel data"""
        width, height, name, flags, groups, layers = self.args

        tree:bpy.types.ShaderNodeTree = None
        try:
            tree = next(g for g in bpy.data.node_groups if g.type == 'SHADER' and g.sb_props.source_abs == name)
        except StopIteration:
            tree = bpy.data.node_groups.new(bpy.path.basename(name), 'ShaderNodeTree')
            tree.sb_props.source_set(name)

        tree.sb_props.sync_flags = flags
        tree.sb_props.size = (width, height)
        
        update_layers(tree, name, width, height, groups, layers)
        util.refresh()

        self.args = None
        global _update_layers_args
        _update_layers_args = None

        return {'FINISHED'}


    def execute(self, context):
        self.args = _update_layers_args
        return ModalExecuteMixin.execute(self, context)


def sheet_animation(obj, img):
    assert img

    if "UV Frame (Pribambase)" not in obj.modifiers or "pribambase_frame" not in obj:
        # it's strange if either is removed manually, to be safe let's assume the user no longer wants that animation
        obj.sb_props.animation = None

    elif img.sb_props.sheet:
        sheet = img.sb_props.sheet

        start,nframes = sheet.sb_props.sheet_start, sheet.sb_props.animation_length
        try:
            # version 3.0 and onwards
            obj.id_properties_ui("pribambase_frame").update(min=start, soft_min=start, max=start + nframes - 1, soft_max=start + nframes - 1)
        except AttributeError:
            # 2.8x and 2.9x
            rna_ui = obj["_RNA_UI"]["pribambase_frame"]
            rna_ui["min"] = rna_ui["soft_min"] = start
            rna_ui["max"] = rna_ui["soft_max"] = start + nframes - 1
        obj["pribambase_frame"] = max(start, min(obj["pribambase_frame"], start + nframes - 1))

        w,h = sheet.sb_props.sheet_size
        iw, ih = img.size
        ofs_obj:bpy.types.Object = obj.modifiers["UV Frame (Pribambase)"].object_to
        ofs_obj.scale = (sheet.size[0]/iw, sheet.size[1]/ih, 1)

        if not ofs_obj.animation_data:
            ofs_obj.animation_data_create()
        else:
            for driver in ofs_obj.animation_data.drivers:
                # there shouldn't be any user drivers on this object
                ofs_obj.animation_data.drivers.remove(driver)

        dx, dy, _dz = ofs_obj.driver_add("location")
        for curve in (dx, dy):
            # there's a polynomial modifier by default
            curve.modifiers.remove(curve.modifiers[0])

            # curve shape
            curve.keyframe_points.add(nframes)
            for i,p in enumerate(curve.keyframe_points):
                if curve == dx:
                    p.co = (start + i - 0.5, -(i % w) * (1 + 2 / iw) - 1 / iw)
                else:
                    p.co = (start + i - 0.5, (i // w) * (1 + 2 / ih) + 1 / ih)
                p.interpolation = 'CONSTANT'

            # add variable
            driver = curve.driver
            driver.type = 'SUM'
            fv = driver.variables.new()
            fv.name = "frame"
            tgt = fv.targets[0]
            tgt.id_type = 'OBJECT'
            tgt.id = obj
            tgt.data_path = '["pribambase_frame"]'

            curve.update()


def _update_action_range(scene):
    # change nla strip action start/end
    for obj in bpy.data.objects:
        if obj.sb_props.animation and obj.animation_data:
            for track in obj.animation_data.nla_tracks:
                for strip in track.strips:
                    if strip.action.sb_props.sprite and strip.use_sync_length:
                        strip.action_frame_start, strip.action_frame_end = strip.action.frame_range

    if addon.state.action_preview_enabled:
        obj = addon.state.action_preview
        if obj and obj.animation_data and obj.animation_data.action:
            scene.frame_preview_start, scene.frame_preview_end = obj.animation_data.action.frame_range
        else:
            addon.state.action_preview_enabled = False


_update_spritesheet_args = None
def spritesheet(size, count, name, start, frames, tags, current_frame, current_tag, pixels):
    # NOTE this function sets animation flag
    global _update_spritesheet_args
    _update_spritesheet_args = size, count, name, start, frames, tags, current_frame, current_tag, pixels
    bpy.ops.pribambase.update_spritesheet()

class SB_OT_update_spritesheet(bpy.types.Operator, ModalExecuteMixin):
    bl_idname = "pribambase.update_spritesheet"
    bl_label = "Update Spritesheet"
    bl_description = ""
    bl_options = {'UNDO_GROUPED', 'INTERNAL'}
    bl_undo_group = "pribambase.update_spritesheet"


    def update_actions(self, context, img:bpy.types.Image, start:int, frames:Collection[int], current_frame:int, tags:Collection[Tuple[str, int, int, int]], current_tag:str):
        fps = context.scene.render.fps / context.scene.render.fps_base

        # loop tag is the current playing part of the timeline in aseprite
        tag_editor = ("__loop__",)
        if current_tag:
            tag_editor += next((t for t in tags if t[0] == current_tag))[1:]
        else:
            tag_editor += (0, len(frames) - 1, 0, 0)

        # current frame tag just shows the current frame, to allow drawing with spritesheet materials same way as if without animation
        tag_frame = ("__view__", current_frame, current_frame, 0, 0)

        # purge actions for removed tags
        tag_names = ["__loop__"] + [tag[0] for tag in tags]
        for action in bpy.data.actions:
            if action.sb_props.sprite == img and action.sb_props.tag not in tag_names:
                bpy.data.actions.remove(action)

        for tag, tag_first, tag_last, repeats, ani_dir in (tag_editor, tag_frame, *tags):
            try:
                action = next(a for a in bpy.data.actions if a.sb_props.sprite == img and a.sb_props.tag == tag)
            except StopIteration:
                action_name = f"{img.name}: {tag}"
                if tag == "__loop__":
                    action_name = f"{img.name} *Loop*"
                elif tag == "__view__":
                    action_name = f"{img.name} *View*"

                action = bpy.data.actions.new(action_name)
                action.id_root = 'OBJECT'
                action.use_fake_user = addon.prefs.use_fake_users
                action.sb_props.tag = tag
                action.sb_props.sprite = img

            first = context.scene.frame_start

            if ani_dir == 1 or ani_dir == 3:
                tag_frames = frames[tag_last:tag_first - 1:-1]
            else:
                tag_frames = frames[tag_first:tag_last + 1]

            if ani_dir == 2 or ani_dir == 3: # pingpong or reverse pingpong
                if repeats == 0:
                    tag_frames = tag_frames + tag_frames[-2:0:-1]
                else:
                    forth = tag_frames[:]
                    back = tag_frames[-2:0:-1]
                    for i in range(1, repeats):
                        tag_frames += forth if i % 2 == 0 else back

            else: # forward, or unsupported
                if repeats > 1:
                    tag_frames *= repeats
            
            tag_frames.append(tag_frames[-1]) # one more keyframe to keep the last frame duration inside in the action

            if not action.fcurves:
                fcurve = action.fcurves.new('["pribambase_frame"]')
                fcurve.modifiers.new('CYCLES').mute = True # to be consistent with old behavior
                fcurve.lock = True

            for fcurve in action.fcurves:
                if not fcurve.data_path == '["pribambase_frame"]':
                    # Only update curves for all custom properties
                    # For multiple animations on one object, the user might need to change path on some curves
                    #    so we can't be certain that the name is same as default and update all of them
                    continue

                points = fcurve.keyframe_points
                npoints = len(points)
                nframes = len(tag_frames)
                if npoints < nframes:
                    points.add(nframes - npoints)
                elif npoints > nframes:
                    for _ in range(npoints - nframes):
                        points.remove(points[0], fast=True)

                time = 0
                for point,(y, dt) in zip(points, tag_frames):
                    x = first + time * fps / 1000
                    if addon.prefs.whole_frames:
                        x = round(x)
                    point.co = (x, start + y)
                    point.select_control_point = point.select_left_handle = point.select_right_handle = False
                    point.interpolation = 'CONSTANT'
                    time += dt

                # modifiers. there can be only one cycles modifier
                mod = next((m for m in fcurve.modifiers if m.type == 'CYCLES'))
                mod.mute = (repeats > 0)

                fcurve.update()
            action.update_tag()

        _update_action_range(context.scene)
    

    def update_armory(self, name:str, count:Tuple[int, int], frames:Collection[int], tags:Collection[Tuple[str, int, int, int]]):
        # Update tilesheet data for armory engine. There they are separate entities invoked by code,
        # not associated with objects in the scene.
        armory = bpy.data.worlds["Arm"]

        try:
            sheet = armory.arm_tilesheetlist[name]
        except KeyError:
            sheet = armory.arm_tilesheetlist.add()
            sheet.name = name
            
        sheet.tilesx_prop, sheet.tilesy_prop = count
        framerate = frames[0][1]
        sheet.framerate_prop = 1000.0 / framerate 

        if next((True for f in frames if f[1] != framerate), False):
            self.report({'WARNING'}, f"Sprite sheet \"{name}\": variable framerate is not supported by Armory")
        
        # create/update actions
        actions = sheet.arm_tilesheetactionlist
        # make one extra action for the entire timeline.
        tl = (f"({name})", 0, len(frames) - 1, 0)
        for (aname, start, end, repeats, ani_dir) in (tl, *tags):
            try:
                action = actions[aname]
            except KeyError:
                action = actions.add()
                action.name = aname
            
            action.start_prop = start
            action.end_prop = end
            action.loop_prop = (repeats == 0)
            
            if (ani_dir == 1 and repeats > 1) or repeats > 2:
                self.report({'WARNING'}, f"Sprite action \"{name}:{aname}\": Repeats are not supported by Armory")

            if ani_dir == 1:
                self.report({'WARNING'}, f"Sprite action \"{name}:{aname}\": Reverse flag is not supported by Armory")
            if ani_dir == 2:
                self.report({'WARNING'}, f"Sprite action \"{name}:{aname}\": Ping-Pong flag is not supported by Armory")
            if ani_dir == 3:
                self.report({'WARNING'}, f"Sprite action \"{name}:{aname}\": Reverse Ping-Pong flag is not supported by Armory")


    def modal_execute(self, context):
        size, count, name, start, frames, tags, current_frame, current_tag, pixels = self.args
        tex_w, tex_h = (size[0] + 2) * count[0], (size[1] + 2) * count[1]

        # find or prepare sheet image; pixels update will fix its size
        for img in bpy.data.images:
            if name == img.sb_props.sync_name:
                try:
                    sheet = img.sb_props.sheet
                    tex_name = sheet.name
                except AttributeError:
                    tex_name = img.name + " *Sheet*"
                    with util.pause_depsgraph_updates():
                        if tex_name not in bpy.data.images:
                            tex = bpy.data.images.new(tex_name, tex_w, tex_h, alpha=True)
                            tex.sb_props.needs_save = True
                            util.pack_empty_png(tex)
                    sheet = img.sb_props.sheet = bpy.data.images[tex_name]

                sheet.sb_props.is_sheet = True
                sheet.sb_props.origin = img
                sheet.sb_props.animation_length = len(frames)
                sheet.sb_props.sheet_size = count
                sheet.sb_props.sheet_start = start

                self.update_actions(context, img, start, frames, current_frame, tags, current_tag)

                if addon.state.use_sync_armory and ("Arm" in bpy.data.worlds):
                    try:
                        self.update_armory(img.name, count, frames, tags)
                    except:
                        self.report({'WARNING'}, "Failed to update Armory data. Make sure the addon is enabled and set up.")

                self.args = tex_w, tex_h, tex_name, -1, set(), pixels
                SB_OT_update_image.modal_execute(self, context) # clears self.args

                # cut out the current frame and copy to view image
                flags = set((*img.sb_props.sync_flags, 'SHEET'))
                frame_x = current_frame % count[0]
                frame_y = current_frame // count[0]
                frame_pixels = np.ravel(pixels[frame_y * (size[1] + 2) + 1 : (frame_y + 1) * (size[1] + 2) - 1, frame_x * (size[0] + 2) * 4 + 4 : (frame_x + 1) * (size[0] + 2) * 4 - 4])
                self.args = *size, name, current_frame, flags, frame_pixels
                SB_OT_update_image.modal_execute(self, context) # clears self.args and animation flag

                # update rig
                for obj in bpy.data.objects:
                    if obj.sb_props.animation == img:
                        sheet_animation(obj, obj.sb_props.animation)

                    obj.update_tag

        # clean up
        global _update_spritesheet_args
        _update_spritesheet_args = None

    def execute(self, context):
        self.args = _update_spritesheet_args
        return ModalExecuteMixin.execute(self, context)


_update_frame_args = None
def frame(name, frame, start, frames):
    # NOTE this operator removes animation flag from image
    global _update_frame_args
    _update_frame_args = name, frame, start, frames
    bpy.ops.pribambase.update_frame()

class SB_OT_update_frame(bpy.types.Operator, ModalExecuteMixin):
    bl_idname = "pribambase.update_frame"
    bl_label = "Update Frame"
    bl_description = ""
    bl_options = {'UNDO_GROUPED', 'INTERNAL'}
    bl_undo_group = "pribambase.update_frame"

    def modal_execute(self, context):
        """Copy the frame from spritesheet to the image"""
        name, frame, start, frames = self.args

        try:
            img = next(i for i in bpy.data.images if name == i.sb_props.sync_name)
        except StopIteration:
            # to avoid accidentally reviving deleted images, we ignore anything doesn't exist already
            return

        # TODO getting data from the image might be a pain (it's that opengl thing)
        # might just wait until implementing DNA access

        for action in bpy.data.actions:
            if action.sb_props.sprite == img and action.sb_props.tag == "__view__":
                for fcurve in action.fcurves:
                    if not fcurve.data_path.startswith('["'):
                        continue

                    for point in fcurve.keyframe_points:
                        point.co = (point.co.x, frame)
                    fcurve.update()

            elif action.sb_props.sprite == img and action.sb_props.tag == "__loop__":
                fps = context.scene.render.fps / context.scene.render.fps_base
                frames.append(frames[-1])

                for fcurve in action.fcurves:
                    if not fcurve.data_path.startswith('["'):
                        continue

                    points = fcurve.keyframe_points
                    npoints = len(points)
                    nframes = len(frames)
                    if npoints < nframes:
                        points.add(nframes - npoints)
                    elif npoints > nframes:
                        for _ in range(npoints - nframes):
                            points.remove(points[0], fast=True)

                    time = 0
                    for point,(y, dt) in zip(points, frames):
                        x = start + time * fps / 1000
                        if addon.prefs.whole_frames:
                            x = round(x)
                        point.co = (x, start + y)
                        point.select_control_point = point.select_left_handle = point.select_right_handle = False
                        point.interpolation = 'CONSTANT'
                        time += dt

        _update_action_range(context.scene)

        self.args = None
        global _update_frame_args
        _update_frame_args = None

        return {'FINISHED'}


    def execute(self, context):
        self.args = _update_frame_args
        return ModalExecuteMixin.execute(self, context)


class SB_OT_new_texture(bpy.types.Operator, ModalExecuteMixin):
    bl_idname = "pribambase.new_texture"
    bl_label = "New Texture"
    bl_description = ""
    bl_options = {'UNDO', 'INTERNAL'}

    name:bpy.props.StringProperty(name="Name")
    path:bpy.props.StringProperty(name="Path")
    sheet:bpy.props.BoolProperty(name="Animated")
    layers:bpy.props.BoolProperty(name="Layers")

    def modal_execute(self, context):
        if self.path:
            bpy.ops.pribambase.sprite_open(filepath=self.path, relative=addon.prefs.use_relative_path, sheet=self.sheet, layers=self.layers)
        else:
            flags = set()
            if self.layers:
                flags.add('LAYERS')
            if self.sheet:
                flags.add('SHEET')

            with util.pause_depsgraph_updates():
                if self.layers:
                    img = bpy.data.node_groups.new(self.name, "ShaderNodeTree")
                else:
                    img = bpy.data.images.new(self.name, 1, 1, alpha=True)
                    img.sb_props.needs_save = True
                    util.pack_empty_png(img)

                img.sb_props.source=self.name
                img.sb_props.sync_flags = flags
            bpy.ops.pribambase.send_texture_list()

        return {'FINISHED'}