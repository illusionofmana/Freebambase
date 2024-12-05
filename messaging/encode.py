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

from typing import Any, Iterable, Sequence, Tuple
from . import *


def batch(messages:Sequence[bytearray]) -> bytearray:
    data = bytearray()
    add_id(data, '[')
    add_uint(data, len(messages), 2)

    for msg in messages:
        add_data(data, msg)

    return data


def texture_list(blendfile:str, images:Iterable[Tuple[str, Set[str]]]) -> bytearray:
    data = bytearray()
    add_id(data, 'L')
    add_string(data, blendfile)

    for img,flags in images:
        add_string(data, img)
        add_sync_flags(data, flags)

    return data


def uv_map(size:Tuple[int, int], pixels:bytes, opacity:int, layer:str) -> bytearray:
    data = bytearray()
    add_id(data, 'M')
    add_uint(data, opacity, 1)
    add_uint(data, size[0], 2)
    add_uint(data, size[1], 2)
    add_string(data, layer)
    add_data(data, pixels)
    return data


def image(name:str, size:Tuple[int, int], pixels:bytes) -> bytearray:
    data = bytearray()
    add_id(data, 'I')
    add_uint(data, size[0], 2)
    add_uint(data, size[1], 2)
    add_string(data, name)
    add_data(data, pixels)
    return data


def sprite_new(name:str, mode:int, size: Tuple[int, int], flags:Set[str]) -> bytearray:
    data = bytearray()
    add_id(data, 'S')
    add_uint(data, mode, 1)
    add_uint(data, size[0], 2)
    add_uint(data, size[1], 2)
    add_sync_flags(data, flags)
    add_string(data, name)
    return data


def sprite_open(name:str, flags:Set[str]) -> bytearray:
    data = bytearray()
    add_id(data, 'O')
    add_sync_flags(data, flags)
    add_string(data, name)
    return data


def sprite_focus(name:str) -> bytearray:
    data = bytearray()
    add_id(data, 'F')
    add_string(data, name)
    return data


def peek(images:Iterable[Tuple[str, Set[str]]]) -> bytearray:
    data = bytearray()
    add_id(data, 'P')
    add_uint(data, len(images), 2)

    for img,flags in images:
        add_string(data, img)
        add_sync_flags(data, flags)

    return data