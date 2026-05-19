import logging

from canopen.sdo.base import SdoBase
from canopen.sdo.constants import *
from canopen.sdo.exceptions import *


logger = logging.getLogger(__name__)


class SdoBlockException(SdoAbortedError):
    """Dedicated SDO Block exception."""


class SdoServer(SdoBase):
    """Creates an SDO server."""

    def __init__(self, rx_cobid, tx_cobid, node):
        """
        :param int rx_cobid:
            COB-ID that the server receives on (usually 0x600 + node ID)
        :param int tx_cobid:
            COB-ID that the server responds with (usually 0x580 + node ID)
        :param canopen.LocalNode od:
            Node object owning the server
        """
        SdoBase.__init__(self, rx_cobid, tx_cobid, node.object_dictionary)
        self._node = node
        self._buffer = None
        self._toggle = 0
        self._index = None
        self._subindex = None
        self.last_received_error = 0x00000000
        self.sdo_block = None

    def on_request(self, can_id, data, timestamp):
        logger.debug("on_request")
        if self.sdo_block and self.sdo_block.state != BLOCK_STATE_NONE:
            try:
                self.process_block(data)
            except SdoAbortedError as exc:
                self.sdo_block = None
                self.abort(exc.code)
                raise
            except Exception:
                self.sdo_block = None
                self.abort()
                raise
            return

        (command,) = struct.unpack_from("B", data, 0)
        ccs = command & 0xE0

        try:
            if ccs == REQUEST_UPLOAD:
                self.init_upload(data)
            elif ccs == REQUEST_SEGMENT_UPLOAD:
                self.segmented_upload(command)
            elif ccs == REQUEST_DOWNLOAD:
                self.init_download(data)
            elif ccs == REQUEST_SEGMENT_DOWNLOAD:
                self.segmented_download(command, data)
            elif ccs == REQUEST_BLOCK_UPLOAD:
                self.block_upload(data)
            elif ccs == REQUEST_BLOCK_DOWNLOAD:
                self.block_download(data)
            elif ccs == REQUEST_ABORTED:
                self.request_aborted(data)
            else:
                self.abort(ABORT_INVALID_COMMAND_SPECIFIER)
        except SdoAbortedError as exc:
            self.abort(exc.code)
        except KeyError as exc:
            self.abort(ABORT_NOT_IN_OD)
        except Exception as exc:
            self.abort()
            logger.exception(exc)

    def process_block(self, request):
        """
        Process a block request, using a state mechanisme from SdoBlock class
        to handle the different states of the block transfer.

        :param request:
            CAN message containing EMCY or SDO request.
        """

        logger.debug("process_block")
        command, _, _, code = SDO_ABORT_STRUCT.unpack_from(request)
        if command == 0x80:
            # Abort received
            logger.error("Abort: 0x%08X" % code)
            self.sdo_block = None
            return

        if BLOCK_STATE_UPLOAD < self.sdo_block.state < BLOCK_STATE_DOWNLOAD:
            logger.debug("BLOCK_STATE_UPLOAD")
            command, _, _ = SDO_STRUCT.unpack_from(request)

            # in upload state
            if self.sdo_block.state == BLOCK_STATE_UP_INIT_RESP:
                logger.debug("BLOCK_STATE_UP_INIT_RESP")
                # init response was sent, client required to send new request
                if (command & REQUEST_BLOCK_UPLOAD) != REQUEST_BLOCK_UPLOAD:
                    raise SdoBlockException("Unknown SDO command specified")  # pragma: no cover
                if (command & START_BLOCK_UPLOAD) != START_BLOCK_UPLOAD:
                    raise SdoBlockException("Unknown SDO command specified")  # pragma: no cover

                # now start blasting data to client from server
                self.sdo_block.update_state(BLOCK_STATE_UP_DATA)

                blocks = self.sdo_block.get_upload_blocks()
                for block in blocks:
                    self.send_response(block)

            elif self.sdo_block.state == BLOCK_STATE_UP_DATA:
                logger.debug("BLOCK_STATE_UP_DATA")
                command, ackseq, newblk = SDO_BLOCKACK_STRUCT.unpack_from(request)
                if (command & REQUEST_BLOCK_UPLOAD) != REQUEST_BLOCK_UPLOAD:
                    raise SdoBlockException("Unknown SDO command specified")
                elif (command & BLOCK_TRANSFER_RESPONSE) != BLOCK_TRANSFER_RESPONSE:
                    raise SdoBlockException("Unknown SDO command specified")
                elif ackseq != self.sdo_block.last_seqno:
                    self.sdo_block.data_uploaded = self.sdo_block.data_successful_upload
                else:
                    self.sdo_block.data_successful_upload = self.sdo_block.data_uploaded

                if self.sdo_block.size == self.sdo_block.data_uploaded:
                    logger.debug("BLOCK_STATE_UP_DATA last data")
                    self.sdo_block.update_state(BLOCK_STATE_UP_END)
                    response = bytearray(8)
                    command = RESPONSE_BLOCK_UPLOAD
                    command |= END_BLOCK_TRANSFER
                    n = self.sdo_block.last_bytes << 2
                    command |= n
                    logger.debug("Last no byte: %d, CRC: x%04X", self.sdo_block.last_bytes, self.sdo_block.crc_value)
                    SDO_BLOCKEND_STRUCT.pack_into(response, 0, command, self.sdo_block.crc_value)
                    self.send_response(response)
                else:
                    blocks = self.sdo_block.get_upload_blocks()
                    for block in blocks:
                        self.send_response(block)

            elif self.sdo_block.state == BLOCK_STATE_UP_END:
                self.sdo_block = None

        elif BLOCK_STATE_DOWNLOAD < self.sdo_block.state <= BLOCK_STATE_DL_END:
            # in download state
            logger.debug("BLOCK_STATE_DOWNLOAD")
            if self.sdo_block.state == BLOCK_STATE_DL_DATA:
                logger.debug("BLOCK_STATE_DL_DATA")
                seqno = command & 0x7F
                last_seg = bool(command & NO_MORE_BLOCKS)
                # Accumulate data bytes (bytes 1-7 of each segment)
                self.sdo_block.append_download_data(request[1:8])
                self.sdo_block.last_seqno = seqno

                if seqno >= self.sdo_block.req_blocksize or last_seg:
                    # Send block acknowledgement
                    response = bytearray(8)
                    response[0] = RESPONSE_BLOCK_DOWNLOAD | BLOCK_TRANSFER_RESPONSE
                    response[1] = seqno  # ackseq
                    response[2] = self.sdo_block.req_blocksize  # new blksize
                    self.send_response(response)
                    self.sdo_block.seqno = 0

                    if last_seg:
                        self.sdo_block.update_state(BLOCK_STATE_DL_END)

            elif self.sdo_block.state == BLOCK_STATE_DL_END:
                logger.debug("BLOCK_STATE_DL_END")
                if (command & REQUEST_BLOCK_DOWNLOAD) != REQUEST_BLOCK_DOWNLOAD:
                    raise SdoBlockException("Unknown SDO command specified") # pragma: no cover
                if (command & SUB_COMMAND_MASK) != END_BLOCK_TRANSFER:
                    raise SdoBlockException("Unknown SDO command specified") # pragma: no cover

                # n = bytes NOT used in last segment
                n = (command >> 2) & 0x7
                data = self.sdo_block.finalize_download(n)

                self._node.set_data(self.sdo_block.index, self.sdo_block.subindex, data, check_writable=True)

                response = bytearray(8)
                response[0] = RESPONSE_BLOCK_DOWNLOAD | END_BLOCK_TRANSFER
                self.send_response(response)
                self.sdo_block = None
        else:
            # in neither
            raise SdoBlockException(
                "Data can not be transferred or stored to the application because of the present device state"
            ) # pragma: no cover

    def init_upload(self, request):
        _, index, subindex = SDO_STRUCT.unpack_from(request)
        self._index = index
        self._subindex = subindex
        res_command = RESPONSE_UPLOAD | SIZE_SPECIFIED
        response = bytearray(8)

        data = self._node.get_data(index, subindex, check_readable=True)
        size = len(data)
        if size == 0:
            logger.info("No content to upload for 0x%04X:%02X", index, subindex)
            self.abort(ABORT_NO_DATA_AVAILABLE)
            return
        elif size <= 4:
            logger.info("Expedited upload for 0x%04X:%02X", index, subindex)
            res_command |= EXPEDITED
            res_command |= (4 - size) << 2
            response[4 : 4 + size] = data
        else:
            logger.info("Initiating segmented upload for 0x%04X:%02X", index, subindex)
            struct.pack_into("<L", response, 4, size)
            self._buffer = bytearray(data)
            self._toggle = 0
        SDO_STRUCT.pack_into(response, 0, res_command, index, subindex)
        self.send_response(response)

    def segmented_upload(self, command):
        if command & TOGGLE_BIT != self._toggle:
            # Toggle bit mismatch
            raise SdoAbortedError(ABORT_TOGGLE_NOT_ALTERNATED)
        data = self._buffer[:7]
        size = len(data)

        # Remove sent data from buffer
        del self._buffer[:7]

        res_command = RESPONSE_SEGMENT_UPLOAD
        # Add toggle bit
        res_command |= self._toggle
        # Add nof bytes not used
        res_command |= (7 - size) << 1
        if not self._buffer:
            # Nothing left in buffer
            res_command |= NO_MORE_DATA
        # Toggle bit for next message
        self._toggle ^= TOGGLE_BIT

        response = bytearray(8)
        response[0] = res_command
        response[1 : 1 + size] = data
        self.send_response(response)

    def block_upload(self, request):
        """
        Process an initial block upload request.
        Create a CAN response message and update the state of the SDO block.

        :param request:
            CAN message containing SDO request.
        """
        logging.debug("Enter server block upload")
        self.sdo_block = _SdoBlock(self._node, request)

        res_command = RESPONSE_BLOCK_UPLOAD
        res_command |= BLOCK_SIZE_SPECIFIED
        res_command |= self.sdo_block.crc
        res_command |= INITIATE_BLOCK_TRANSFER
        logging.debug("CMD: %02X", res_command)
        response = bytearray(8)

        struct.pack_into(
            SDO_STRUCT.format + "I",  # add size
            response,
            0,
            res_command,
            self.sdo_block.index,
            self.sdo_block.subindex,
            self.sdo_block.size,
        )
        logging.debug("response %s", response)
        self.sdo_block.update_state(BLOCK_STATE_UP_INIT_RESP)
        self.send_response(response)

    def request_aborted(self, data):
        _, index, subindex, code = struct.unpack_from("<BHBL", data)
        self.last_received_error = code
        logger.info("Received request aborted for 0x%04X:%02X with code 0x%X", index, subindex, code)

    def block_download(self, data):
        logger.debug("Enter server block download")
        command, index, subindex = SDO_STRUCT.unpack_from(data)

        self._index = index
        self._subindex = subindex

        self.sdo_block = _SdoBlock(self._node, data, is_download=True)

        res_command = RESPONSE_BLOCK_DOWNLOAD | INITIATE_BLOCK_TRANSFER
        res_command |= self.sdo_block.crc  # Echo CRC support back to client
        response = bytearray(8)
        SDO_STRUCT.pack_into(response, 0, res_command, index, subindex)
        response[4] = self.sdo_block.req_blocksize  # Server-defined block size

        self.sdo_block.update_state(BLOCK_STATE_DL_DATA)
        self.send_response(response)

    def init_download(self, request):
        # TODO: Check if writable (now would fail on end of segmented downloads)
        command, index, subindex = SDO_STRUCT.unpack_from(request)
        self._index = index
        self._subindex = subindex
        res_command = RESPONSE_DOWNLOAD
        response = bytearray(8)

        if command & EXPEDITED:
            logger.info("Expedited download for 0x%04X:%02X", index, subindex)
            if command & SIZE_SPECIFIED:
                size = 4 - ((command >> 2) & 0x3)
            else:
                size = 4
            self._node.set_data(index, subindex, request[4 : 4 + size], check_writable=True)
        else:
            logger.info("Initiating segmented download for 0x%04X:%02X", index, subindex)
            if command & SIZE_SPECIFIED:
                (size,) = struct.unpack_from("<L", request, 4)
                logger.info("Size is %d bytes", size)
            self._buffer = bytearray()
            self._toggle = 0

        SDO_STRUCT.pack_into(response, 0, res_command, index, subindex)
        self.send_response(response)

    def segmented_download(self, command, request):
        if command & TOGGLE_BIT != self._toggle:
            # Toggle bit mismatch
            raise SdoAbortedError(ABORT_TOGGLE_NOT_ALTERNATED)
        last_byte = 8 - ((command >> 1) & 0x7)
        self._buffer.extend(request[1:last_byte])

        if command & NO_MORE_DATA:
            self._node.set_data(self._index, self._subindex, self._buffer, check_writable=True)

        res_command = RESPONSE_SEGMENT_DOWNLOAD
        # Add toggle bit
        res_command |= self._toggle
        # Toggle bit for next message
        self._toggle ^= TOGGLE_BIT

        response = bytearray(8)
        response[0] = res_command
        self.send_response(response)

    def send_response(self, response):
        self.network.send_message(self.tx_cobid, response)

    def abort(self, abort_code=ABORT_GENERAL_ERROR):
        """Abort current transfer."""
        if isinstance(abort_code, SdoAbortedError):
            abort_code = abort_code.code

        data = struct.pack("<BHBL", RESPONSE_ABORTED, self._index, self._subindex, abort_code)
        self.send_response(data)
        # logger.error("Transfer aborted with code 0x%08X", abort_code)

    def upload(self, index: int, subindex: int) -> bytes:
        """May be called to make a read operation without an Object Dictionary.

        :param index:
            Index of object to read.
        :param subindex:
            Sub-index of object to read.

        :return: A data object.

        :raises canopen.SdoAbortedError:
            When node responds with an error.
        """
        return self._node.get_data(index, subindex)

    def download(
        self,
        index: int,
        subindex: int,
        data: bytes,
        force_segment: bool = False,
    ):
        """May be called to make a write operation without an Object Dictionary.

        :param index:
            Index of object to write.
        :param subindex:
            Sub-index of object to write.
        :param data:
            Data to be written.

        :raises canopen.SdoAbortedError:
            When node responds with an error.
        """
        return self._node.set_data(index, subindex, data)


class _SdoBlock:
    """
    _SdoBlock class to handle block transfer. It keeps track of the
    current state and prepares data to be transferred.
    """

    state = BLOCK_STATE_NONE
    crc = False
    data_uploaded = 0
    data_successful_upload = 0
    last_bytes = 0
    crc_value = 0
    last_seqno = 0

    def __init__(self, node, request, docrc=False, is_download=False):
        """
        :param node:
            Node object owning the server
        :param request:
            CAN message containing SDO request.
        :param docrc:
            If True, CRC is calculated and checked.
        :param is_download:
            If True, initialise for block download (server receives data).
            If False (default), initialise for block upload (server sends data).
        """
        command, index, subindex = SDO_STRUCT.unpack_from(request)
        # only do crc if crccheck lib is available _and_ if requested
        _req_crc = (command & CRC_SUPPORTED) == CRC_SUPPORTED

        # For block download, bit 1 is the size indicator (s), not a sub-command
        # bit. Only bit 0 carries the sub-command (0 = initiate). For block
        # upload the s-bit is not used in the initiate command so SUB_COMMAND_MASK
        # works there, but we must use a 1-bit mask here.
        sub_cmd_mask = 0x1 if is_download else SUB_COMMAND_MASK
        if (command & sub_cmd_mask) == INITIATE_BLOCK_TRANSFER:
            self.state = BLOCK_STATE_INIT
        else:
            # Realistically shouldnt happen since this is only called after receiving an initiate command, but check anyway
            raise SdoBlockException("Unknown SDO command specified") # pragma: no cover

        # TODO: CRC of data if requested
        self.crc = CRC_SUPPORTED if (docrc & _req_crc) else 0
        self._node = node
        self.index = index
        self.subindex = subindex
        self.seqno = 0

        if is_download:
            # Server defines the block size for download (client sends this many
            # segments per block before waiting for an acknowledgement)
            self.req_blocksize = 127
            self._data_buffer = bytearray()
            if command & BLOCK_SIZE_SPECIFIED:
                (self.size,) = struct.unpack_from("<L", request, 4)
            else:
                self.size = None  # pragma: no cover
        else:
            self.req_blocksize = request[4]
            if not 1 <= self.req_blocksize <= 127:
                raise SdoBlockException("Invalid block size")
            self.data = self._node.get_data(index, subindex, check_readable=True)
            self.size = len(self.data)

    def update_state(self, new_state):
        """
        Update the state of the SDO block transfer. The state is
        updated only if the new state is higher than the current
        state. Otherwise an exception is raised.
        """
        logging.debug("update_state %X -> %X", self.state, new_state)
        if new_state >= self.state:
            self.state = new_state
        else:
            raise SdoBlockException(
                "Data can not be transferred or stored to the application because of the present device state"
            )

    def get_upload_blocks(self):
        """
        Get the blocks of data to be sent to the client. The blocks are
        created in a messages list of bytearrays.
        """

        msgs = []

        # seq no 1 - 127, not 0 -..
        for seqno in range(1, self.req_blocksize + 1):
            logger.debug("SEQNO %d", seqno)
            response = bytearray(8)
            command = 0
            if self.size <= (self.data_uploaded + 7):
                # no more segments after this
                command |= NO_MORE_BLOCKS

            command |= seqno
            response[0] = command
            for i in range(7):
                databyte = self.get_data_byte()
                if databyte != None:
                    response[i + 1] = databyte
                else:
                    self.last_bytes = 7 - i
                    break
            msgs.append(response)
            self.last_seqno = seqno

            if self.size == self.data_uploaded:
                break
        logger.debug(msgs)
        return msgs

    def get_data_byte(self):
        """Get the next byte of data to be sent to the client."""
        if self.data_uploaded < self.size:
            self.data_uploaded += 1
            return self.data[self.data_uploaded - 1]
        return None

    def append_download_data(self, segment):
        """Append a 7-byte segment to the download data buffer.

        :param segment:
            Bytes 1-7 of the received block segment message (always 7 bytes).
        """
        self._data_buffer.extend(segment)

    def finalize_download(self, n):
        """Return the accumulated download data, trimming the last n unused bytes.

        :param int n:
            Number of bytes in the last segment that did not contain data
            (as signalled by the client in the END_BLOCK_TRANSFER command).

        :returns:
            The complete received data as bytes.
        """
        if n > 0:
            return bytes(self._data_buffer[:-n])
        return bytes(self._data_buffer)
