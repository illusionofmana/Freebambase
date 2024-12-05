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

"""Work woth .ase files directly"""

import struct
import enum
from typing import Tuple

class ColorMode(enum.Enum):
    RGBA = 32
    GRAYSCALE = 16
    INDEXED = 8


@enum.unique
class BlendMode(enum.Enum):
    NORMAL = 0
    MULTIPLY = 1
    SCREEN = 2
    OVERLAY = 3
    DARKEN = 4
    LIGHTEN = 5
    COLOR_DODGE = 6
    COLOR_BURN = 7
    HARD_LIGHT = 8
    SOFT_LIGHT = 9
    DIFFERENCE = 10
    EXCLUSION = 11
    HSL_HUE = 12
    HSL_SATURATION = 13
    HSL_COLOR = 14
    HSL_LUMINOSITY = 15
    ADDITION = 16
    SUBTRACT = 17
    DIVIDE = 18

    def toMix(self):
        """Corresponding blender's string identifier for the BlendMode (when exists)"""
        return BLEND_MODES[self.value]

# blender enum (identifier, name, description, number)
BLEND_MODES = (
    'MIX', # 0
    'MULTIPLY', # 1
    'SCREEN', # 2
    'OVERLAY', # 3
    'DARKEN', # 4
    'LIGHTEN', # 5
    'DODGE', # 6
    'BURN', # 7
    'LINEAR_LIGHT', # 8
    'SOFT_LIGHT', # 9
    'DIFFERENCE', # 10
    'EXCLUSION', # 11
    'HUE', # 12
    'SATURATION', # 13
    'COLOR', # 14
    'VALUE', # 15
    'ADD', # 16
    'SUBTRACT', # 17
    'DIVIDE' # 18
)


def info(filepath) -> Tuple[Tuple[int, int], ColorMode]:
    """read and parse ase file header. return (size, color_mode)"""
    with open(filepath, "rb") as f:
        header = f.read(struct.calcsize("<I5H"))
        _, magic, _, w, h, cmode = struct.unpack("<I5H", header)
        assert magic == 0xA5E0, "Not a valid .ase file"
        return (w, h), ColorMode(cmode)