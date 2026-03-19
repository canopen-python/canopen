"""Object codes, as defined by CiA 301, not to be confused with data type."""

NULL = 0x00
DOMAIN = 0x02
DEFTYPE = 0x05
DEFSTRUCT = 0x06
VAR = 0x07
ARRAY = 0x08
RECORD = 0x09


def code2str(code: int) -> str:
    """Return the constant name for the given value, empty if not found."""
    for k, v in globals().items():
        if k.isupper() and v == code:
            return k
    return ""
