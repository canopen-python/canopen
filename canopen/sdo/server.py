import logging

from canopen.sdo.base import SdoBase
from canopen.sdo.constants import *
from canopen.sdo.exceptions import *


logger = logging.getLogger(__name__)


class SdoBlockException(SdoAbortedError):
    def __init__(self, code: int):
        super.__init__(self, code)

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
        logger.debug('on_request')
        if self.sdo_block and self.sdo_block.state != BLOCK_STATE_NONE:
            self.process_block(data)
            return

        command, = struct.unpack_from("B", data, 0)
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
                self.abort(0x05040001)
        except SdoAbortedError as exc:
            self.abort(exc.code)
        except KeyError as exc:
            self.abort(0x06020000)
        except Exception as exc:
            self.abort()
            logger.exception(exc)

    def process_block(self, request):
        logger.debug('process_block')
        command, _, _, code = SDO_ABORT_STRUCT.unpack_from(request)
        if command == 0x80:
            # Abort received
            logger.error('Abort: 0x%08X' % code)
            self.sdo_block = None
            return

        if BLOCK_STATE_UPLOAD < self.sdo_block.state < BLOCK_STATE_DOWNLOAD:
            logger.debug('BLOCK_STATE_UPLOAD')
            command, _, _= SDO_STRUCT.unpack_from(request)
            # in upload state
            if self.sdo_block.state == BLOCK_STATE_UP_INIT_RESP:
                logger.debug('BLOCK_STATE_UP_INIT_RESP')
                #init response was sent, client required to send new request
                if (command & REQUEST_BLOCK_UPLOAD) != REQUEST_BLOCK_UPLOAD:
                    raise SdoBlockException(0x05040001)
                if (command & START_BLOCK_UPLOAD) != START_BLOCK_UPLOAD:
                    raise SdoBlockException(0x05040001)
                # self.sdo_block.update_state(BLOCK_STATE_UP_DATA)

                # now start blasting data to client from server
                self.sdo_block.update_state(BLOCK_STATE_UP_DATA)
                #self.data_succesfull_upload = self.data_uploaded

                blocks = self.sdo_block.get_upload_blocks()
                for block in blocks:
                    self.send_response(block)

            elif self.sdo_block.state == BLOCK_STATE_UP_DATA:
                logger.debug('BLOCK_STATE_UP_DATA')
                command, ackseq, newblk = SDO_BLOCKACK_STRUCT.unpack_from(request)
                if (command & REQUEST_BLOCK_UPLOAD) != REQUEST_BLOCK_UPLOAD:
                    raise SdoBlockException(0x05040001)
                elif (command & BLOCK_TRANSFER_RESPONSE) != BLOCK_TRANSFER_RESPONSE:
                    raise SdoBlockException(0x05040001)
                elif (ackseq != self.sdo_block.last_seqno):
                    self.sdo_block.data_uploaded = self.sdo_block.data_succesfull_upload


                if self.sdo_block.size == self.sdo_block.data_uploaded:
                    logger.debug('BLOCK_STATE_UP_DATA last data')
                    self.sdo_block.update_state(BLOCK_STATE_UP_END)
                    response = bytearray(8)
                    command = RESPONSE_BLOCK_UPLOAD
                    command |= END_BLOCK_TRANSFER
                    n = self.sdo_block.last_bytes << 2
                    command |= n
                    logger.debug('Last no byte: %d, CRC: x%04X',
                                 self.sdo_block.last_bytes,
                                 self.sdo_block.crc_value)
                    SDO_BLOCKEND_STRUCT.pack_into(response, 0, command,
                                                  self.sdo_block.crc_value)
                    self.send_response(response)
                else:
                    blocks = self.sdo_block.get_upload_blocks()
                    for block in blocks:
                        self.send_response(block)

            elif self.sdo_block.state == BLOCK_STATE_UP_END:
                self.sdo_block = None

        elif BLOCK_STATE_DOWNLOAD < self.sdo_block.state:
            logger.debug('BLOCK_STATE_DOWNLOAD')
            # in download state
            pass
        else:
            # in neither
            raise SdoBlockException(0x08000022)

    def init_upload(self, request):
        _, index, subindex = SDO_STRUCT.unpack_from(request)
        self._index = index
        self._subindex = subindex
        res_command = RESPONSE_UPLOAD | SIZE_SPECIFIED
        response = bytearray(8)

        data = self._node.get_data(index, subindex, check_readable=True)
        size = len(data)
        if size <= 4:
            logger.info("Expedited upload for 0x%04X:%02X", index, subindex)
            res_command |= EXPEDITED
            res_command |= (4 - size) << 2
            response[4:4 + size] = data
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
            raise SdoAbortedError(0x05030000)
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
        response[1:1 + size] = data
        self.send_response(response)

    def block_upload(self, request):
        logging.debug('Enter server block upload')
        self.sdo_block = SdoBlock(self._node, request)

        res_command = RESPONSE_BLOCK_UPLOAD
        res_command |= BLOCK_SIZE_SPECIFIED
        res_command |= self.sdo_block.crc
        res_command |= INITIATE_BLOCK_TRANSFER
        logging.debug('CMD: %02X', res_command)
        response = bytearray(8)

        struct.pack_into(SDO_STRUCT.format+'I',  # add size
                         response, 0,
                         res_command,
                         self.sdo_block.index,
                         self.sdo_block.subindex,
                         self.sdo_block.size)
        logging.debug('response %s', response)
        self.sdo_block.update_state(BLOCK_STATE_UP_INIT_RESP)
        self.send_response(response)

    def request_aborted(self, data):
        _, index, subindex, code = struct.unpack_from("<BHBL", data)
        self.last_received_error = code
        logger.info("Received request aborted for 0x%04X:%02X with code 0x%X", index, subindex, code)

    def block_download(self, data):
        # We currently don't support BLOCK DOWNLOAD
        logger.error("Block download is not supported")
        self.abort(0x05040001)

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
            self._node.set_data(index, subindex, request[4:4 + size], check_writable=True)
        else:
            logger.info("Initiating segmented download for 0x%04X:%02X", index, subindex)
            if command & SIZE_SPECIFIED:
                size, = struct.unpack_from("<L", request, 4)
                logger.info("Size is %d bytes", size)
            self._buffer = bytearray()
            self._toggle = 0

        SDO_STRUCT.pack_into(response, 0, res_command, index, subindex)
        self.send_response(response)

    def segmented_download(self, command, request):
        if command & TOGGLE_BIT != self._toggle:
            # Toggle bit mismatch
            raise SdoAbortedError(0x05030000)
        last_byte = 8 - ((command >> 1) & 0x7)
        self._buffer.extend(request[1:last_byte])

        if command & NO_MORE_DATA:
            self._node.set_data(self._index,
                                self._subindex,
                                self._buffer,
                                check_writable=True)

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

    def abort(self, abort_code=0x08000000):
        """Abort current transfer."""
        data = struct.pack("<BHBL", RESPONSE_ABORTED,
                           self._index, self._subindex, abort_code)
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

class SdoBlock():
    state = BLOCK_STATE_NONE
    crc = False
    data_uploaded = 0
    data_succesfull_upload = 0
    last_bytes = 0
    crc_value = 0
    last_seqno = 0

    def __init__(self, node, request, docrc=False):

        command, index, subindex = SDO_STRUCT.unpack_from(request)
        # only do crc if crccheck lib is available _and_ if requested
        _req_crc = (command & CRC_SUPPORTED) == CRC_SUPPORTED

        if (command & SUB_COMMAND_MASK) == INITIATE_BLOCK_TRANSFER:
            self.state = BLOCK_STATE_INIT
        else:
            raise SdoBlockException(SdoAbortedError.from_string("Unknown SDO command specified"))

        self.crc = CRC_SUPPORTED if (docrc & _req_crc)  else 0
        self._node = node
        self.index = index
        self.subindex = subindex
        self.req_blocksize = request[4]
        self.seqno = 0
        if not 1 <= self.req_blocksize <= 127:
            raise SdoBlockException(SdoAbortedError.from_string("Invalid block size"))

        self.data = self._node.get_data(index,
                                        subindex,
                                        check_readable=True)
        self.size = len(self.data)

        # TODO: add PST if needed
        # self.pst = data[5]

    def update_state(self, new_state):
        logging.debug('update_state %X -> %X', self.state, new_state)
        if new_state >= self.state:
            self.state = new_state
        else:
            raise SdoBlockException(0x08000022)

    def get_upload_blocks(self):
        msgs = []

        # seq no 1 - 127, not 0 -..
        for seqno in range(1,self.req_blocksize+1):
            logger.debug('SEQNO %d', seqno)
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
                    response[i+1] = databyte
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
        if self.data_uploaded < self.size:
            self.data_uploaded += 1
            return self.data[self.data_uploaded-1]
        return None

