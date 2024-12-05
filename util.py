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
Auxiliary functions
"""

import os
import tempfile
import bpy
import re
from typing import Collection
from contextlib import contextmanager

from .addon import addon

def unique_name(name:str, collection:Collection[str]) -> str:
    """Imitate blender behavior for ID names. Returns the name, possibly with a numeric suffix (e.g .001), so that it doesn't match any other strings in the collection"""
    assert name, "Name can not be empty"
    base, count = None, 0

    while name in collection:
        if not base: # do once
            # regexp always matches the first group
            base, suffix = re.match("^(.*?)(?:\.([0-9]{3}))?$", name).groups()
            if len(base) > 59: # the length of IDProperty names is limited to 63 characters
                base = base[:60]
            count = int(suffix) if suffix else 0
        count += 1
        name = f"{base}.{count:03}"
    
    return name


def refresh():
    """Tag the ui for redrawing"""
    ctx = bpy.context
    if not ctx or not ctx.window_manager:
        return
    
    for win in ctx.window_manager.windows:
        for area in win.screen.areas:
            area.tag_redraw()


def pack_empty_png(image:bpy.types.Image):
    """Load 1x1 ARGB png to the image and pack it"""
    # Do NOT optimize the png. It might set flags that break color after reloading, and they are hard to fix for users.
    contents = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x04\x00\x00\x00\xb5\x1c\x0c\x02\x00\x00\x00\x0bIDATx\xdacd`\x00\x00\x00\x06\x00\x020\x81\xd0/\x00\x00\x00\x00IEND\xaeB`\x82"
    temp = tempfile.mktemp()
    f = open(temp, "wb")
    f.write(contents)
    f.close()
    
    image.use_fake_user = addon.prefs.use_fake_users
    image.filepath = temp
    image.pack() # image.pack(contents, len(contents)) was not reliable for some reason
    image.filepath_raw = ""

    os.remove(temp)


def image_nodata(image:bpy.types.Image) -> bool:
    '''
    check if the image is empty (file doesn't exist, or it was not saved internally)
    unintuitively, `image.has_data` has a different meaning and may return True in that case
    '''
    return not image or not image.pixels


class ModalExecuteMixin:
    """
    bpy.types.Operator mixin that makes operator execute once via modal timer, allowing to modify 
    blender state from non-operator code with fewer surprizes. Uses a non-modal fallback for older
    versions. To use, define modal_execute(self, ctx) method
    """

    def modal_execute(self, context):
        raise NotImplementedError()

    def modal(self, context, event):
        if event.type == 'TIMER':
            context.window_manager.event_timer_remove(self.timer)
            self.modal_execute(context)
        return {'FINISHED'}

    def execute(self, context):
        if context and context.window:
            context.window_manager.modal_handler_add(self)
            self.timer = context.window_manager.event_timer_add(0.000001, window=context.window)
            return {'RUNNING_MODAL'}
        else:
            return self.modal_execute(context)


class SB_OT_report(bpy.types.Operator, ModalExecuteMixin):
    bl_idname = "pribambase.report"
    bl_label = "Report"
    bl_description = "Report the message"
    bl_options = {'INTERNAL'}

    message_type: bpy.props.StringProperty(name="Message Type", default='INFO')
    message: bpy.props.StringProperty(name="Message", default='Someone forgot to change the message text')

    def modal_execute(self, context):
        self.report({self.message_type}, self.message)
        return {'FINISHED'}


@contextmanager
def pause_depsgraph_updates():
    """disable depsgraph listener in the context"""
    from . import sb_on_depsgraph_update_post
    assert sb_on_depsgraph_update_post in bpy.app.handlers.depsgraph_update_post

    bpy.app.handlers.depsgraph_update_post.remove(sb_on_depsgraph_update_post)
    try:
        yield None
    finally:
        bpy.app.handlers.depsgraph_update_post.append(sb_on_depsgraph_update_post)