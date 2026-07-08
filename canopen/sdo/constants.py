import struct
from typing import Final


# Command, index, subindex
SDO_STRUCT = struct.Struct("<BHB")
SDO_BLOCKACK_STRUCT = struct.Struct("<BBB") # c + ackseq + new blocksize
SDO_BLOCKEND_STRUCT = struct.Struct("<BH") # c + CRC
SDO_ABORT_STRUCT = struct.Struct("<BHBI") # c +i + si + Abort code

# Command[5-7]
REQUEST_SEGMENT_DOWNLOAD = 0 << 5
REQUEST_DOWNLOAD = 1 << 5
REQUEST_UPLOAD = 2 << 5
REQUEST_SEGMENT_UPLOAD = 3 << 5
REQUEST_ABORTED = 4 << 5
REQUEST_BLOCK_UPLOAD = 5 << 5
REQUEST_BLOCK_DOWNLOAD = 6 << 5

RESPONSE_SEGMENT_UPLOAD = 0 << 5
RESPONSE_SEGMENT_DOWNLOAD = 1 << 5
RESPONSE_UPLOAD = 2 << 5
RESPONSE_DOWNLOAD = 3 << 5
RESPONSE_ABORTED = 4 << 5
RESPONSE_BLOCK_DOWNLOAD = 5 << 5
RESPONSE_BLOCK_UPLOAD = 6 << 5

# Block transfer sub-commands, Command[0-1]
SUB_COMMAND_MASK = 0x3
INITIATE_BLOCK_TRANSFER = 0
END_BLOCK_TRANSFER = 1
BLOCK_TRANSFER_RESPONSE = 2
START_BLOCK_UPLOAD = 3

EXPEDITED = 0x2             # Expedited and segmented
SIZE_SPECIFIED = 0x1        # All transfers
BLOCK_SIZE_SPECIFIED = 0x2  # Block transfer: size specified in message
CRC_SUPPORTED = 0x4         # client/server CRC capable
NO_MORE_DATA = 0x1          # Segmented: last segment
NO_MORE_BLOCKS = 0x80       # Block transfer: last segment
TOGGLE_BIT = 0x10           # segmented toggle mask

# Block states
BLOCK_STATE_NONE = -1
BLOCK_STATE_INIT = 0        # state when entering
BLOCK_STATE_UPLOAD = 0x10   # delimiter, used for block type check
BLOCK_STATE_UP_INIT_RESP = 0x11 # state when entering, response during upload
BLOCK_STATE_UP_DATA = 0x12     # Upload Data transfer state
BLOCK_STATE_UP_END = 0x13      # End of Upload block transfers
BLOCK_STATE_DOWNLOAD = 0x20 # delimiter, used for block type check
BLOCK_STATE_DL_DATA = 0x24     # Download Data transfer state
BLOCK_STATE_DL_END = 0x25      # End of Download block transfers

# Abort codes
ABORT_TOGGLE_NOT_ALTERNATED: Final[int] = 0x0503_0000
ABORT_TIMED_OUT: Final[int] = 0x0504_0000
ABORT_INVALID_COMMAND_SPECIFIER: Final[int] = 0x0504_0001
ABORT_INVALID_BLOCK_SIZE: Final[int] = 0x0504_0002
ABORT_INVALID_SEQUENCE_NUMBER: Final[int] = 0x0504_0003
ABORT_CRC_ERROR: Final[int] = 0x0504_0004
ABORT_OUT_OF_MEMORY: Final[int] = 0x0504_0005
ABORT_UNSUPPORTED_ACCESS: Final[int] = 0x0601_0000
ABORT_READ_WRITEONLY: Final[int] = 0x0601_0001
ABORT_WRITE_READONLY: Final[int] = 0x0601_0002
ABORT_NOT_IN_OD: Final[int] = 0x0602_0000
ABORT_PDO_CANNOT_MAP: Final[int] = 0x0604_0041
ABORT_PDO_LENGTH_EXCEEDED: Final[int] = 0x0604_0042
ABORT_PARAMETER_INCOMPATIBLE: Final[int] = 0x0604_0043
ABORT_INTERNAL_INCOMPATIBILITY: Final[int] = 0x0604_0047
ABORT_HARDWARE_ERROR: Final[int] = 0x0606_0000
ABORT_LENGTH_NOT_MATCHED: Final[int] = 0x0607_0010
ABORT_LENGTH_TOO_HIGH: Final[int] = 0x0607_0012
ABORT_LENGTH_TOO_LOW: Final[int] = 0x0607_0013
ABORT_NO_SUBINDEX: Final[int] = 0x0609_0011
ABORT_INVALID_VALUE: Final[int] = 0x0609_0030  # download only
ABORT_VALUE_TOO_HIGH: Final[int] = 0x0609_0031  # download only
ABORT_VALUE_TOO_LOW: Final[int] = 0x0609_0032  # download only
ABORT_MAXIMUM_LESS_THAN_MINIMUM: Final[int] = 0x0609_0036
ABORT_NO_SDO_CONNECTION: Final[int] = 0x060A_0023
ABORT_GENERAL_ERROR: Final[int] = 0x0800_0000
ABORT_STORE_APPLICATION: Final[int] = 0x0800_0020
ABORT_APPLICATION_LOCAL_CONTROL: Final[int] = 0x0800_0021
ABORT_APPLICATION_DEVICE_STATE: Final[int] = 0x0800_0022
ABORT_OD_GENERATION: Final[int] = 0x0800_0023
ABORT_NO_DATA_AVAILABLE: Final[int] = 0x0800_0024
