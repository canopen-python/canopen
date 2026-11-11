"""Check that every client-side abort retains the initiating object's address."""

import gc
import struct
import time

import pytest

import canopen


INDEX = 0x2345
SUBINDEX = 0x67
ADDRESS = struct.pack('<HB', INDEX, SUBINDEX)
PAYLOAD = bytes.fromhex('deadbeef012345')
TIMEOUT = 0x05040000
INVALID_COMMAND = 0x05040001
TOGGLE = 0x05030000
CRC = 0x05040004
GENERAL = 0x08000000


def tx(data, delay=0):
    return ('tx', data, delay)


def rx(data):
    return ('rx', data, 0)


def initial(command, tail=bytes(4), address=ADDRESS):
    return bytes([command]) + address + tail


def abort(code, index=INDEX, subindex=SUBINDEX):
    return struct.pack('<BHBL', 0x80, index, subindex, code)


def upload_start():
    return [tx(initial(0x40)), rx(initial(0x41, struct.pack('<L', 7)))]


def download_start(size=7):
    command = 0x20 if size is None else 0x21
    tail = bytes(4) if size is None else struct.pack('<L', size)
    return [tx(initial(command, tail)), rx(initial(0x60))]


def block_upload_start(crc=False, response=None):
    command = 0xa4 if crc else 0xa0
    answer = initial(0xc4 if crc else 0xc0) if response is None else response
    return [tx(initial(command, bytes.fromhex('7f000000'))), rx(answer)]


def block_download_start(response=None):
    answer = initial(0xa0, bytes.fromhex('01000000')) if response is None else response
    return [tx(initial(0xc2, struct.pack('<L', 7))), rx(answer)]


def block_download_close():
    # Existing close behavior is preserved even after a block-ACK error.
    return [tx(bytes.fromhex('c100000000000000')), rx(bytes.fromhex('a100000000000000'))]


@pytest.fixture
def wire():
    """Use the same scripted network transport as the existing SDO wire tests."""
    networks = []

    def make(frames):
        script = list(frames)
        network = canopen.Network()
        networks.append(network)

        def send_message(can_id, data, remote=False):
            assert not remote
            direction, expected, delay = script.pop(0)
            assert direction == 'tx'
            assert can_id == 0x602
            assert bytes(data) == expected
            if delay:
                time.sleep(delay)
            while script and script[0][0] == 'rx':
                _, response, _ = script.pop(0)
                network.notify(0x582, response, 0.0)

        network.send_message = send_message
        client = network.add_node(canopen.RemoteNode(2, canopen.ObjectDictionary())).sdo
        client.RESPONSE_TIMEOUT = 0.005
        return client, script

    yield make
    gc.collect()
    for network in networks:
        network.disconnect()


def use_stream(client, options, action=None):
    with client.open(INDEX, SUBINDEX, buffering=0, **options) as stream:
        if action == 'read':
            stream.read(7)
        elif action == 'write':
            stream.write(PAYLOAD)
        elif action == 'expedited':
            stream.write(PAYLOAD[:3])


@pytest.mark.parametrize('path', [
    'upload-init', 'download-init', 'block-upload-init', 'block-download-init',
    'upload-segment', 'download-expedited', 'download-segment',
    'download-close', 'block-download-close',
])
def test_timeout_context_at_all_request_response_paths(wire, path):
    """Retry exhaustion must use the stream address, including payload and close requests."""
    cleanup = []
    if path == 'upload-init':
        frames = [tx(initial(0x40))]
        options, action = {'mode': 'rb'}, None
    elif path == 'download-init':
        frames = [tx(initial(0x21, struct.pack('<L', 7)))]
        cleanup = [tx(bytes.fromhex('0f00000000000000')), rx(bytes.fromhex('2000000000000000'))]
        options, action = {'mode': 'wb', 'size': 7}, None
    elif path == 'block-upload-init':
        frames = [tx(initial(0xa0, bytes.fromhex('7f000000')))]
        options, action = {'mode': 'rb', 'block_transfer': True, 'request_crc_support': False}, None
    elif path == 'block-download-init':
        frames = [tx(initial(0xc2, struct.pack('<L', 7)))]
        options, action = {'mode': 'wb', 'size': 7, 'block_transfer': True,
                           'request_crc_support': False}, None
    elif path == 'upload-segment':
        frames = upload_start() + [tx(bytes.fromhex('6000000000000000'))]
        options, action = {'mode': 'rb'}, 'read'
    elif path == 'download-expedited':
        frames = [tx(initial(0x27, PAYLOAD[:3] + b'\x00'))]
        options, action = {'mode': 'wb', 'size': 3}, 'expedited'
    elif path == 'download-segment':
        frames = download_start() + [tx(b'\x01' + PAYLOAD)]
        options, action = {'mode': 'wb', 'size': 7}, 'write'
    elif path == 'download-close':
        frames = download_start(None) + [tx(bytes.fromhex('0f00000000000000'))]
        options, action = {'mode': 'wb'}, None
    else:
        frames = block_download_start() + [tx(b'\x81' + PAYLOAD),
                  rx(bytes.fromhex('a201010000000000')), tx(bytes.fromhex('c100000000000000'))]
        options, action = {'mode': 'wb', 'size': 7, 'block_transfer': True,
                           'request_crc_support': False}, 'write'
    client, script = wire(frames + [tx(abort(TIMEOUT))] + cleanup)
    with pytest.raises(canopen.SdoCommunicationError, match='No SDO response received'):
        use_stream(client, options, action)
    gc.collect()
    assert script == []


ERROR_SITES = [
    'upload-command', 'upload-toggle', 'download-init-command',
    'download-expedited-command', 'download-segment-command',
    'block-upload-init-command', 'block-upload-crc', 'block-upload-retransmit-timeout',
    'block-upload-end-timeout', 'block-upload-end-command', 'block-upload-end-subcommand',
    'block-download-init-command', 'block-download-init-address',
    'block-download-ack-timeout', 'block-download-ack-command', 'block-download-ack-subcommand',
]


@pytest.mark.parametrize('site', ERROR_SITES)
def test_stream_error_abort_uses_original_address(wire, site):
    """Original object context survives wrong peer fields, segment data and block errors."""
    cleanup = []
    code = INVALID_COMMAND
    if site in ('upload-command', 'upload-toggle'):
        answer = b'\x60' + PAYLOAD if site == 'upload-command' else b'\x11' + PAYLOAD
        frames = upload_start() + [tx(bytes.fromhex('6000000000000000')), rx(answer)]
        options, action = {'mode': 'rb'}, 'read'
        if site == 'upload-toggle':
            code = TOGGLE
    elif site == 'download-init-command':
        frames = [tx(initial(0x21, struct.pack('<L', 7))), rx(initial(0x40))]
        cleanup = [tx(bytes.fromhex('0f00000000000000')), rx(bytes.fromhex('2000000000000000'))]
        options, action = {'mode': 'wb', 'size': 7}, None
    elif site == 'download-expedited-command':
        frames = [tx(initial(0x27, PAYLOAD[:3] + b'\x00')), rx(initial(0x40))]
        options, action = {'mode': 'wb', 'size': 3}, 'expedited'
    elif site == 'download-segment-command':
        frames = download_start() + [tx(b'\x01' + PAYLOAD), rx(bytes.fromhex('603172b4cf098afe'))]
        options, action = {'mode': 'wb', 'size': 7}, 'write'
    elif site == 'block-upload-init-command':
        frames = block_upload_start(response=initial(0x60))
        options, action = {'mode': 'rb', 'block_transfer': True, 'request_crc_support': False}, None
    elif site.startswith('block-upload-'):
        crc = site == 'block-upload-crc'
        frames = block_upload_start(crc) + [tx(bytes.fromhex('a300000000000000'))]
        options, action = {'mode': 'rb', 'block_transfer': True, 'request_crc_support': crc}, 'read'
        if site == 'block-upload-retransmit-timeout':
            # Delay the ACK send beyond this retransmission window; no clock is mocked.
            frames += [rx(b'\x02' + PAYLOAD), tx(bytes.fromhex('a2007f0000000000'), delay=0.02)]
            code = TIMEOUT
        else:
            frames += [rx(b'\x81' + PAYLOAD), tx(bytes.fromhex('a2017f0000000000'))]
            if site == 'block-upload-end-timeout':
                code = TIMEOUT
            elif site == 'block-upload-end-command':
                frames += [rx(bytes.fromhex('6000000000000000'))]
            elif site == 'block-upload-end-subcommand':
                frames += [rx(bytes.fromhex('c000000000000000'))]
            else:
                frames += [rx(bytes.fromhex('c100000000000000'))]
                code = CRC
    elif site in ('block-download-init-command', 'block-download-init-address'):
        response = initial(0x60) if site.endswith('command') else initial(
            0xa0, bytes.fromhex('01000000'), address=bytes.fromhex('efbe91'))
        frames = block_download_start(response)
        options, action = {'mode': 'wb', 'size': 7, 'block_transfer': True,
                           'request_crc_support': False}, None
        if site.endswith('address'):
            code = GENERAL
    else:
        frames = block_download_start() + [tx(b'\x81' + PAYLOAD)]
        options, action = {'mode': 'wb', 'size': 7, 'block_transfer': True,
                           'request_crc_support': False}, 'write'
        cleanup = block_download_close()
        if site == 'block-download-ack-timeout':
            code = TIMEOUT
        elif site == 'block-download-ack-command':
            frames += [rx(bytes.fromhex('6001010000000000'))]
        else:
            frames += [rx(bytes.fromhex('a001010000000000'))]
    client, script = wire(frames + [tx(abort(code))] + cleanup)
    with pytest.raises(canopen.SdoCommunicationError):
        use_stream(client, options, action)
    gc.collect()
    assert script == []


@pytest.mark.parametrize('args,code', [((), GENERAL), ((TIMEOUT,), TIMEOUT)])
def test_direct_abort_legacy_forms(wire, args, code):
    client, script = wire([tx(abort(code, 0, 0))])
    client.abort(*args)
    assert script == []


@pytest.mark.parametrize('index,subindex', [(0, 0), (1, 1), (0xffff, 0xff)])
def test_direct_abort_explicit_address_bounds(wire, index, subindex):
    client, script = wire([tx(abort(0xffffffff, index, subindex))])
    client.abort(0xffffffff, index=index, subindex=subindex)
    assert script == []


@pytest.mark.parametrize('index,subindex', [
    (-1, SUBINDEX), (0x10000, SUBINDEX), (INDEX, -1), (INDEX, 0x100),
])
def test_invalid_abort_address_is_rejected_before_sending(wire, index, subindex):
    client, script = wire([])
    with pytest.raises(struct.error):
        client.abort(TIMEOUT, index=index, subindex=subindex)
    assert script == []


@pytest.mark.parametrize('explicit_context', [False, True])
def test_direct_request_response_keeps_no_context_fallback(wire, explicit_context):
    expected = abort(TIMEOUT) if explicit_context else abort(TIMEOUT, 0, 0)
    client, script = wire([tx(initial(0x40)), tx(expected)])
    keywords = {'index': INDEX, 'subindex': SUBINDEX} if explicit_context else {}
    with pytest.raises(canopen.SdoCommunicationError, match='No SDO response received'):
        client.request_response(initial(0x40), **keywords)
    assert script == []


@pytest.mark.parametrize('success_on_retry', [False, True])
def test_retry_policy_preserves_count_and_abort(wire, success_on_retry):
    frames = [tx(initial(0x40)), tx(initial(0x40))]
    if success_on_retry:
        frames += [rx(initial(0x43, PAYLOAD[:4]))]
    else:
        frames += [tx(abort(TIMEOUT))]
    client, script = wire(frames)
    client.MAX_RETRIES = 2
    if success_on_retry:
        assert client.upload(INDEX, SUBINDEX) == PAYLOAD[:4]
    else:
        with pytest.raises(canopen.SdoCommunicationError, match='No SDO response received'):
            client.upload(INDEX, SUBINDEX)
    assert script == []


@pytest.mark.parametrize('kind', ['upload', 'block-upload', 'block-download'])
def test_remote_abort_is_not_echoed(wire, kind):
    if kind == 'upload':
        request, options = initial(0x40), {'mode': 'rb'}
    elif kind == 'block-upload':
        request = initial(0xa0, bytes.fromhex('7f000000'))
        options = {'mode': 'rb', 'block_transfer': True, 'request_crc_support': False}
    else:
        request = initial(0xc2, struct.pack('<L', 7))
        options = {'mode': 'wb', 'size': 7, 'block_transfer': True, 'request_crc_support': False}
    client, script = wire([tx(request), rx(abort(0x06020000))])
    with pytest.raises(canopen.SdoAbortedError) as error:
        use_stream(client, options)
    assert error.value.code == 0x06020000
    assert script == []


@pytest.mark.parametrize('kind', ['upload', 'block-upload'])
def test_existing_wrong_address_response_does_not_add_abort(wire, kind):
    wrong_address = bytes.fromhex('efbe91')
    if kind == 'upload':
        frames = [tx(initial(0x40)), rx(initial(0x41, struct.pack('<L', 7), wrong_address))]
        options = {'mode': 'rb'}
    else:
        frames = block_upload_start(response=initial(0xc0, address=wrong_address))
        options = {'mode': 'rb', 'block_transfer': True, 'request_crc_support': False}
    client, script = wire(frames)
    with pytest.raises(canopen.SdoCommunicationError, match='Node returned a value'):
        use_stream(client, options)
    assert script == []


def test_success_then_timeout_uses_new_stream_and_direct_abort_stays_unset(wire):
    second = struct.pack('<HB', 0x4567, 0x89)
    frames = [tx(initial(0x40)), rx(initial(0x43, PAYLOAD[:4])),
              tx(b'\x40' + second + bytes(4)), tx(abort(TIMEOUT, 0x4567, 0x89)),
              tx(abort(GENERAL, 0, 0))]
    client, script = wire(frames)
    assert client.upload(INDEX, SUBINDEX) == PAYLOAD[:4]
    with pytest.raises(canopen.SdoCommunicationError, match='No SDO response received'):
        client.upload(0x4567, 0x89)
    client.abort()
    assert script == []
