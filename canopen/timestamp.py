from __future__ import annotations

import struct
import time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import canopen.network


# 1 Jan 1984
OFFSET = 441763200

ONE_DAY = 60 * 60 * 24

TIME_OF_DAY_STRUCT = struct.Struct("<LH")


class TimeProducer:
    """Produces timestamp objects."""

    #: COB-ID of the SYNC message
    cob_id = 0x100

    def __init__(self, network: canopen.network.Network):
        self.network = network

    def transmit(self, timestamp: Optional[float] = None):
        """Send out the TIME message once.

        :param float timestamp:
            Optional Unix timestamp to use, otherwise the current time is used.
        """
        delta = (timestamp or time.time()) - OFFSET
        days, seconds = divmod(delta, ONE_DAY)
        data = TIME_OF_DAY_STRUCT.pack(int(seconds * 1000), int(days))
        self.network.send_message(self.cob_id, data)
