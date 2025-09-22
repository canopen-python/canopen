"""Additional utility functions for canopen."""

from typing import Optional, Union
from canopen.objectdictionary import datatypes

def pretty_index(index: Optional[Union[int, str]],
                 sub: Optional[Union[int, str]] = None):
    """Format an index and subindex as a string."""

    index_str = ""
    if isinstance(index, int):
        index_str = f"0x{index:04X}"
    elif index:
        index_str = f"{index!r}"

    sub_str = ""
    if isinstance(sub, int):
        # Need 0x prefix if index is not present
        sub_str = f"{'0x' if not index_str else ''}{sub:02X}"
    elif sub:
        sub_str = f"{sub!r}"

    return ":".join(s for s in (index_str, sub_str) if s)

def signed_int_from_hex(hex_str, bit_length):
    number = int(hex_str, 0)
    max_value = (1 << (bit_length - 1)) - 1

    if number > max_value:
        return number - (1 << bit_length)
    else:
        return number
    
def calc_bit_length(data_type):
    if data_type == datatypes.INTEGER8:
        return 8
    elif data_type == datatypes.INTEGER16:
        return 16
    elif data_type == datatypes.INTEGER32:
        return 32
    elif data_type == datatypes.INTEGER64:
        return 64
    else:
        raise ValueError(f"Invalid data_type '{data_type}', expecting a signed integer data_type.")