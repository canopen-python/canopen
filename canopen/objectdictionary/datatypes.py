import struct

BOOLEAN = 0x1
INTEGER8 = 0x2
INTEGER16 = 0x3
INTEGER32 = 0x4
UNSIGNED8 = 0x5
UNSIGNED16 = 0x6
UNSIGNED32 = 0x7
REAL32 = 0x8
VISIBLE_STRING = 0x9
OCTET_STRING = 0xA
UNICODE_STRING = 0xB
TIME_OF_DAY = 0xC
TIME_DIFFERENCE = 0xD
DOMAIN = 0xF
INTEGER24 = 0x10
REAL64 = 0x11
INTEGER40 = 0x12
INTEGER48 = 0x13
INTEGER56 = 0x14
INTEGER64 = 0x15
UNSIGNED24 = 0x16
UNSIGNED40 = 0x18
UNSIGNED48 = 0x19
UNSIGNED56 = 0x1A
UNSIGNED64 = 0x1B
PDO_COMMUNICATION_PARAMETER = 0x1C
PDO_MAPPING = 0x1D
SDO_PARAMETER = 0x1E

SIGNED_TYPES = (INTEGER8, INTEGER16, INTEGER24, INTEGER32, INTEGER40, INTEGER48, INTEGER56, INTEGER64)
UNSIGNED_TYPES = (UNSIGNED8, UNSIGNED16, UNSIGNED24, UNSIGNED32, UNSIGNED40, UNSIGNED48, UNSIGNED56, UNSIGNED64)
INTEGER_TYPES = SIGNED_TYPES + UNSIGNED_TYPES
FLOAT_TYPES = (REAL32, REAL64)
NUMBER_TYPES = INTEGER_TYPES + FLOAT_TYPES
DATA_TYPES = (VISIBLE_STRING, OCTET_STRING, UNICODE_STRING, DOMAIN)


class UnsignedN:
    """ struct-like class for packing and unpacking unsigned integers of arbitrary width.
    The width must be a multiple of 8 and must be between 8 and 64.
    """
    def __init__(self, width: int):
        self.width = width
        if width % 8 != 0:
            raise ValueError("Width must be a multiple of 8")
        if width <= 0 or width > 64:
            raise ValueError("Invalid width for UnsignedN")
        elif width <= 8:
            self.struct = struct.Struct("B")
        elif width <= 16:
            self.struct = struct.Struct("<H")
        elif width <= 32:
            self.struct = struct.Struct("<L")
        else:
            self.struct = struct.Struct("<Q")

    def unpack(self, buffer):
        return self.struct.unpack(buffer + b'\x00' * (self.struct.size - self.size))

    def pack(self, *v):
        return self.struct.pack(*v)[:self.size]

    @property
    def size(self):
        return self.width // 8


class IntegerN:
    """ struct-like class for packing and unpacking integers of arbitrary width.
    The width must be a multiple of 8 and must be between 8 and 64.
    """
    def __init__(self, width: int):
        self.width = width
        if width % 8 != 0:
            raise ValueError("Width must be a multiple of 8")
        if width <= 0 or width > 64:
            raise ValueError("Invalid width for IntegerN")
        elif width <= 8:
            self.struct = struct.Struct("b")
        elif width <= 16:
            self.struct = struct.Struct("<h")
        elif width <= 32:
            self.struct = struct.Struct("<l")
        else:
            self.struct = struct.Struct("<q")

    def unpack(self, buffer):
        mask = 0x80
        neg = (buffer[self.size - 1] & mask) > 0
        return self.struct.unpack(buffer + (b'\xff' if neg else b'\x00') * (self.struct.size - self.size))

    def pack(self, *v):
        return self.struct.pack(*v)[:self.size]

    @property
    def size(self):
        return self.width // 8
