from __future__ import annotations

import logging
from typing import Dict, Union

import canopen.network
from canopen import objectdictionary
from canopen.emcy import EmcyProducer
from canopen.nmt import NmtSlave
from canopen.node.base import BaseNode
from canopen.objectdictionary import ObjectDictionary
from canopen.pdo import PDO, RPDO, TPDO
from canopen.sdo import SdoAbortedError, SdoServer


logger = logging.getLogger(__name__)


class LocalNode(BaseNode):

    def __init__(
        self,
        node_id: int,
        object_dictionary: Union[ObjectDictionary, str],
    ):
        super(LocalNode, self).__init__(node_id, object_dictionary)

        self.data_store: Dict[int, Dict[int, bytes]] = {}
        self._read_callbacks = []
        self._write_callbacks = []

        self.sdo = SdoServer(0x600 + self.id, 0x580 + self.id, self)
        self.tpdo = TPDO(self)
        self.rpdo = RPDO(self)
        self.pdo = PDO(self, self.rpdo, self.tpdo)
        self.nmt = NmtSlave(self.id, self)
        # Let self.nmt handle writes for 0x1017
        self.add_write_callback(self.nmt.on_write)
        self.emcy = EmcyProducer(0x80 + self.id)

    def associate_network(self, network: canopen.network.Network):
        if self.has_network():
            raise RuntimeError("Node is already associated with a network")
        self.network = network
        self.sdo.network = network
        self.tpdo.network = network
        self.rpdo.network = network
        self.nmt.network = network
        self.emcy.network = network
        network.subscribe(self.sdo.rx_cobid, self.sdo.on_request)
        network.subscribe(0, self.nmt.on_command)

    def remove_network(self) -> None:
        if not self.has_network():
            return
        self.network.unsubscribe(self.sdo.rx_cobid, self.sdo.on_request)
        self.network.unsubscribe(0, self.nmt.on_command)
        self.network = canopen.network._UNINITIALIZED_NETWORK
        self.sdo.network = canopen.network._UNINITIALIZED_NETWORK
        self.tpdo.network = canopen.network._UNINITIALIZED_NETWORK
        self.rpdo.network = canopen.network._UNINITIALIZED_NETWORK
        self.nmt.network = canopen.network._UNINITIALIZED_NETWORK
        self.emcy.network = canopen.network._UNINITIALIZED_NETWORK

    def add_read_callback(self, callback):
        self._read_callbacks.append(callback)

    def add_write_callback(self, callback):
        self._write_callbacks.append(callback)

    def get_data(
        self, index: int, subindex: int, check_readable: bool = False
    ) -> bytes:
        obj = self._find_object(index, subindex)

        if check_readable and not obj.readable:
            raise SdoAbortedError(0x06010001)

        # Try callback
        for callback in self._read_callbacks:
            result = callback(index=index, subindex=subindex, od=obj)
            if result is not None:
                return obj.encode_raw(result)

        # Try stored data
        try:
            return self.data_store[index][subindex]
        except KeyError:
            # Try ParameterValue in EDS
            if obj.value is not None:
                return obj.encode_raw(obj.value)
            # Try default value
            if obj.default is not None:
                return obj.encode_raw(obj.default)

        # Resource not available
        logger.info("Resource unavailable for 0x%04X:%02X", index, subindex)
        raise SdoAbortedError(0x060A0023)

    def set_data(
        self,
        index: int,
        subindex: int,
        data: bytes,
        check_writable: bool = False,
    ) -> None:
        obj = self._find_object(index, subindex)

        if check_writable and not obj.writable:
            raise SdoAbortedError(0x06010002)

        # Check length matches type (length of od variable is in bits)
        if obj.data_type in objectdictionary.NUMBER_TYPES and (
            not 8 * len(data) == len(obj)
        ):
            raise SdoAbortedError(0x06070010)

        # Try callbacks
        for callback in self._write_callbacks:
            callback(index=index, subindex=subindex, od=obj, data=data)

        # Store data
        self.data_store.setdefault(index, {})
        self.data_store[index][subindex] = bytes(data)

    def _find_object(self, index, subindex):
        if index not in self.object_dictionary:
            # Index does not exist
            raise SdoAbortedError(0x06020000)
        obj = self.object_dictionary[index]
        if not isinstance(obj, objectdictionary.ODVariable):
            # Group or array
            if subindex not in obj:
                # Subindex does not exist
                raise SdoAbortedError(0x06090011)
            obj = obj[subindex]
        return obj
