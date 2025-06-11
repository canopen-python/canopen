import struct

# Command, index, subindex
SDO_STRUCT = struct.Struct("<BHB")
SDO_BLOCKINIT_STRUCT = "<BHBI"  # Command + seqno, index, subindex, size
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

