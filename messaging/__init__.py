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

from typing import Set, Type
from types import SimpleNamespace as MessageArgs


ID_SIZE = 1
DATA_LEN_SIZE = 4 # 4GB more than enough


class Handler:
    """A handler for a type of incoming messages. Implementation should override parse and execute methods"""

    def __init__(self, handlers):
        self._position:int = 0
        self._data:memoryview = None
        self._handlers = handlers


    async def execute(self, **kwargs):
        """Override this method with something that does the work"""
        pass


    def parse(self, args:MessageArgs):
        """Override this method with something that uses self.take_{type} to fill the provided dictionary of args.
            Those will be passed to the execute() call later"""
        pass


    def take_bool(self):
        return self.take_uint(1) != 0


    def take_uint(self, size:int) -> int:
        """Parse an unsigned integer"""
        self._position += size
        return int.from_bytes(
            bytes=self._data[self._position - size:self._position],
            byteorder='little',
            signed=False)


    def take_sint(self, size:int) -> int:
        """Parse a signed integer"""
        self._position += size
        return int.from_bytes(
            bytes=self._data[self._position - size:self._position],
            byteorder='little',
            signed=True)


    def take_data(self) -> memoryview:
        """Parse a string prefixed with its length"""
        length = self.take_uint(DATA_LEN_SIZE)
        self._position += length
        return self._data[self._position - length:self._position]


    def take_str(self, encoding='utf-8') -> str:
        """Parse and decode a string prefixed with its length"""
        return str(self.take_data(), encoding)

    
    def take_frame(self):
        cel = self.take_uint(2)
        duration = self.take_uint(2)
        return (cel,duration)
    
    def take_sync_flags(self):
        bf = self.take_uint(2)
        flags = set()
        if bf & (1 << 0):
            flags.add('SHEET')
        if bf & (1 << 1):
            flags.add('SHOW_UV')
        if bf & (1 << 2):
            flags.add('LAYERS')
        return flags


    def _parse(self, data:memoryview, args:MessageArgs):
        """Internal, use parse() instead"""
        self._position = 0
        try:
            self._data = data.toreadonly()
        except AttributeError:
            self._data = data # we're time travelling in the era before python 2.8
        self.parse(args)
        self._data.release()
        self._data = None
        data.release()


class Handlers:
    """Incoming message controller"""

    def __init__(self):
        self._messages={}


    def add(self, msg:Type[Handler]):
        assert hasattr(msg, "id"), \
            f"Message type must have a property 'id' with unique {ID_SIZE}-char string"

        assert msg.id not in self._messages, \
            f"ID {msg.id} is already registered"

        # we do not actually expect the ID to be crazy unicode
        m = msg.__new__(msg)
        m.__init__(self)
        self._messages[msg.id] = m


    async def process(self, data):
        mvdata = memoryview(data)
        id = str(mvdata[:ID_SIZE], 'utf-8')

        if id not in self._messages:
            print(f"Message {id} ({len(mvdata)} bytes) does not have handler")
            return

        msg = self._messages[id]
        args = MessageArgs()
        msg._parse(mvdata[ID_SIZE:], args)
        await msg.execute(**args.__dict__)


# API for outgoing messages
# encoding a message is one call - a function is what we need, not classes

def add_id(ba:bytearray, id:str):
    assert len(id) == ID_SIZE
    ba += id.encode()


def add_bool(ba:bytearray, val:bool):
    add_uint(ba, 1 if val else 0, 1)


def add_uint(ba:bytearray, val:int, size:int):
    ba += val.to_bytes(size, 'little', signed=False)


def add_sint(ba:bytearray, val:int, size:int):
    ba += val.to_bytes(size, 'little', signed=True)


def add_data(ba:bytearray, data):
    add_uint(ba, len(data), DATA_LEN_SIZE)
    ba += data


def add_string(ba:bytearray, s:str, encoding='utf-8'):
    data = s.encode(encoding)
    add_uint(ba, len(data), DATA_LEN_SIZE)
    ba += data


def add_sync_flags(ba:bytearray, flags:Set[str]):
    bits = 0
    bits |= ('SHEET' in flags) << 0
    bits |= ('SHOW_UV' in flags) << 1
    bits |= ('LAYERS' in flags) << 2
    add_uint(ba, bits, 2)