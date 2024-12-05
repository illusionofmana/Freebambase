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
import asyncio
import re
import math
from typing import Set, Union, List, Tuple, Iterable
from . import Handler
import numpy as np
# TODO move into local methods
from .. import modify
from ..addon import addon
from .. import ase


class Batch(Handler):
    """Process batch messages"""
    id = "["

    def parse(self, args):
        count = self.take_uint(2)
        args.messages = [self.take_data() for _ in range(count)]


    async def execute(self, messages:Iterable[memoryview]):
        for m in messages:
            await self._handlers.process(m)


class Image(Handler):
    id = "I"

    def parse(self, args):
        args.size = self.take_uint(2), self.take_uint(2)
        args.frame = self.take_uint(2)
        args.flags = self.take_sync_flags()
        args.name = self.take_str()
        args.data = np.frombuffer(self.take_data(), dtype=np.ubyte)

    async def execute(self, *, size:Tuple[int, int], frame:int, flags:Set[str], name:str, data:np.array):
        try:
            # TODO separate cases for named and anonymous sprites
            if not bpy.context.window_manager.is_interface_locked:
                modify.image(size[0], size[1], name, frame, flags, data)
            else:
                bpy.ops.pribambase.report(message_type='WARNING', message="UI is locked, image update skipped")
        except AttributeError:
            # blender 2.80... if it crashes, it crashes :\
            modify.image(size[0], size[1], name, frame, flags, data)


class Spritesheet(Handler):
    """Change textures' sources when aseprite saves the file under a new name"""
    id = 'G'

    def take_tag(self):
        name = self.take_str()
        start = self.take_uint(2)
        end = self.take_uint(2)
        repeats = self.take_uint(2)
        ani_dir = self.take_uint(1)
        return (name, start, end, repeats, ani_dir)


    def parse(self, args):
        args.size = self.take_uint(2), self.take_uint(2)
        args.name = self.take_str()
        args.start = self.take_sint(4)
        args.length = self.take_uint(4)
        args.current_frame = self.take_uint(4)
        args.frames = [self.take_frame() for _ in range(args.length)]
        _ntags = self.take_uint(4)
        args.current_tag = self.take_str()
        args.tags = [self.take_tag() for _ in range(_ntags)]
        args.images = [self.take_data() for _ in range(args.length)]


    async def execute(self, *, size:Tuple[int, int], name:str, start:int, length:int, frames:List[int], tags:List[Tuple], current_frame:int, current_tag:str, images:List[np.array]):
        count_x = math.ceil(length ** 0.5)
        count_y = math.ceil(length / count_x)
        w, h = size
        stride = (w + 2) * 4

        # TODO profile if changing to .empty gives significant perf (at cost of messy look)
        # copying with 1px padding on each side (so there's 1px space on the edge, 2px between tiles)
        sheet_data = np.zeros(((h + 2) * count_y, stride * count_x), dtype=np.ubyte)

        for n,frame in enumerate(images):
            # TODO is there a way to just swap the nparray's buffer? 
            x, y = n % count_x, n // count_x
            fd = np.frombuffer(frame, dtype=np.ubyte)
            fd.shape = (h, w * 4)
            dst = sheet_data[y * (h + 2) + 1: (y + 1) * (h + 2) - 1, x * stride + 4: (x + 1) * stride - 4]
            np.copyto(dst, fd, casting='no')

        sheet_data.shape = (count_x * count_y * (h + 2), stride) # turn sheet into a single column
        np.copyto(sheet_data[:, :4],sheet_data[:, 4:8], casting='no') # left
        np.copyto(sheet_data[:, -4:],sheet_data[:, -8:-4], casting='no') # right

        wstride = count_x * stride
        sheet_data.shape = (count_y, (h + 2) * wstride) # turn sheet into a asjhdaskjdhajf
        np.copyto(sheet_data[:, :wstride],sheet_data[:, wstride:2 * wstride], casting='no') # top
        np.copyto(sheet_data[:, -wstride:],sheet_data[:, -2 * wstride:-wstride], casting='no') # bottom

        sheet_data.shape = ((h + 2) * count_y, stride * count_x) # turn sheet back

        try:
            if not bpy.context.window_manager.is_interface_locked:
                modify.spritesheet(size, (count_x, count_y), name, start, frames, tags, current_frame, current_tag, sheet_data)
            else:
                bpy.ops.pribambase.report(message_type='WARNING', message="UI is locked, image update skipped")
        except AttributeError:
            # version 2.80... caveat emptor
            modify.spritesheet(size, (count_x, count_y), name, start, frames, tags, current_frame, current_tag, sheet_data)


class Frame(Handler):
    """Change sprite frame without changing data"""
    id = "F"

    def parse(self, args):
        args.frame = self.take_uint(4)
        args.name = self.take_str()
        args.start = self.take_uint(2)
        nframes = self.take_uint(4)
        args.frames = [self.take_frame() for _ in range(nframes)]


    async def execute(self, frame:int, name:str, start:int, frames:List[Tuple[int, int]]):
        try:
            if not bpy.context.window_manager.is_interface_locked:
                modify.frame(name, frame, start, frames)
            else:
                bpy.ops.pribambase.report(message_type='WARNING', message="UI is locked, frame flip skipped")
        except AttributeError:
            # version 2.80... caveat emptor
            modify.frame(name, frame, start, frames)


class ImageLayers(Handler):
    """static image with separate layers"""
    id = "L"

    def take_group(self):
        name = self.take_str()
        return (name,)
    

    def take_layer(self):
        idx = self.take_uint(2)
        blend = ase.BlendMode(self.take_uint(2))
        opacity = self.take_uint(2)
        group = self.take_uint(2)
        x = self.take_sint(2)
        y = self.take_sint(2)
        w = self.take_uint(2)
        h = self.take_uint(2)
        name = self.take_str()
        pixels = self.take_data()
        return (idx, blend, opacity, group, x, y, w, h, name, pixels)


    def parse(self, args):
        args.width = self.take_uint(2)
        args.height = self.take_uint(2)
        args.name = self.take_str()
        args.flags = self.take_sync_flags()
        ngroups = self.take_uint(4)
        nlayers = self.take_uint(4)
        args.groups = [self.take_group() for _ in range(ngroups)]
        args.layers = [self.take_layer() for _ in range(nlayers)]
    

    async def execute(self, width:int, height:int, name:str, flags:Set[str], groups:List[Tuple], layers:List[Tuple]):
        try:
            if not bpy.context.window_manager.is_interface_locked:
                modify.image_layers(width, height, name, flags, groups, layers)
            else:
                bpy.ops.pribambase.report(message_type='WARNING', message="UI is locked, image update skipped")
        except AttributeError:
            # version 2.80... caveat emptor
            modify.image_layers(width, height, name, flags, groups, layers)


class ChangeName(Handler):
    """Change textures' sources when aseprite saves the file under a new name"""
    id = "C"

    def parse(self, args):
        args.old_name = self.take_str()
        args.new_name = self.take_str()


    async def execute(self, *, old_name, new_name):
        try:
            # FIXME there's a risk of race condition but it's pretty bad if the rename doesn't happen
            while bpy.context.window_manager.is_interface_locked:
                bpy.ops.pribambase.report(message_type='WARNING', message="UI is locked, waiting to update image source..")
                asyncio.sleep(0.1)
        except AttributeError:
            # version 2.80... caveat emptor
            pass

        # avoid having identical sb_source on several images
        for img in bpy.data.images:
            if old_name in (img.sb_props.source_abs, img.filepath, img.name):
                img.sb_props.source_set(new_name)

                if re.search(r"\.(?:png|jpg|jpeg|bmp|tga)$", new_name):
                    img.filepath_raw = new_name
                else:
                    img.filepath_raw = ""

        bpy.ops.pribambase.send_texture_list()


class NewTexture(Handler):
    id = "O"

    def parse(self, args):
        args.name = self.take_str()
        args.path = self.take_str()
        flags = self.take_sync_flags()
        args.sheet = 'SHEET' in flags
        args.layers = 'LAYERS' in flags

    async def execute(self, *, name:str, path:str, sheet:bool, layers:bool):
        try:
            if not bpy.context.window_manager.is_interface_locked:
                bpy.ops.pribambase.new_texture(name=name, path=path, sheet=sheet, layers=layers)
            else:
                bpy.ops.pribambase.report(message_type='WARNING', message="UI is locked, image update skipped")
        except AttributeError:
            # blender 2.80... if it crashes, it crashes :\
            bpy.ops.pribambase.new_texture(name=name, path=path, sheet=sheet, layers=layers)


class ActiveSprite(Handler):
    """Aseprite's workspace state"""
    id = "A"

    def parse(self, args):
        name = self.take_str()
        args.name = name and name or None

    async def execute(self, name:Union[str, None]):
        addon.active_sprite = name
        if addon.watch:
            addon.watch.resend()