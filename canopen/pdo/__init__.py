import logging

from canopen import node
from canopen.pdo.base import PdoBase, PdoMap, PdoMaps, PdoVariable
from canopen.sdo import SdoAbortedError

__all__ = [
    "PdoBase",
    "PdoMap",
    "PdoMaps",
    "PdoVariable",
    "PDO",
    "RPDO",
    "TPDO",
]

logger = logging.getLogger(__name__)


class PDO(PdoBase):
    """PDO Class for backwards compatibility.

    :param rpdo: RPDO object holding the Receive PDO mappings
    :param tpdo: TPDO object holding the Transmit PDO mappings
    """

    def __init__(self, node, rpdo, tpdo):
        super(PDO, self).__init__(node)
        self.rx = rpdo.map
        self.tx = tpdo.map

        self.map = {}
        # the object 0x1A00 equals to key '1' so we remove 1 from the key
        for key, value in self.rx.items():
            self.map[0x1A00 + (key - 1)] = value
        for key, value in self.tx.items():
            self.map[0x1600 + (key - 1)] = value


class RPDO(PdoBase):
    """Receive PDO to transfer data from somewhere to the represented node.

    Properties 0x1400 to 0x1403 | Mapping 0x1600 to 0x1603.
    :param object node: Parent node for this object.
    """

    def __init__(self, node):
        super(RPDO, self).__init__(node)
        self.map = PdoMaps(0x1400, 0x1600, self, 0x200)
        logger.debug('RPDO Map as %d', len(self.map))

    def stop(self):
        """Stop transmission of all RPDOs.

        :raise TypeError: Exception is thrown if the node associated with the PDO does not
        support this function.
        """
        if isinstance(self.node, node.RemoteNode):
            for pdo in self.map.values():
                pdo.stop()
        else:
            raise TypeError('The node type does not support this function.')


class TPDO(PdoBase):
    """Transmit PDO to broadcast data from the represented node to the network.

    Properties 0x1800 to 0x1803 | Mapping 0x1A00 to 0x1A03.
    :param object node: Parent node for this object.
    """

    def __init__(self, node):
        super(TPDO, self).__init__(node)
        self.map = PdoMaps(0x1800, 0x1A00, self, 0x180)
        logger.debug('TPDO Map as %d', len(self.map))

    def start(self, period: float):
        """Start transmission of all TPDOs.

        :param float period: Transmission period in seconds.
        :raises TypeError: Exception is thrown if the node associated with the PDO does not
        support this function.
        """
        if isinstance(self.node, node.LocalNode):
            for pdo in self.map.values():
                pdo.start(period)
        else:
            raise TypeError("The node type does not support this function.")

    def pack_data(self, data: bytearray, variable: PdoVariable):
        """Pack new data into data array if new data is available. 

        :param list data: List of data to pack.
        :param PdoVariable variable: Variable to pack.
        """
        length_bytes = variable.length // 8
        offset_bytes = variable.offset // 8
        if length_bytes > 8:
            raise ValueError("Data length is greater than 64 bits.")

        if length_bytes == 0:
            return data

        if (
            self.node.data_store.get(variable.index, {}).get(variable.subindex)
            is not None
        ):
            try:
                variable_data = self.node.get_data(variable.index, variable.subindex)
                # reverse list to be able to be transmitted properly
                sanitized_data = variable_data[::-1]
                # pack new data into data array
                for i in range(length_bytes):
                    data[offset_bytes + i] = sanitized_data[i]
            except SdoAbortedError:
                logger.warning(
                    "Failed to get data from index: 0x%X, subindex: 0x%X",
                    variable.index,
                    variable.subindex,
                )

        return data

    def update(self):
        """Update the data of all TPDOs.

        :raises TypeError: Exception is thrown if the node associated with the PDO does not
        support this function.
        """
        if isinstance(self.node, node.LocalNode):
            for pdo in self.map.values():
                for variable in pdo:
                    self.pack_data(pdo.data, variable)
                pdo.update()
        else:
            raise TypeError("The node type does not support this function.")

    def stop(self):
        """Stop transmission of all TPDOs.

        :raise TypeError: Exception is thrown if the node associated with the PDO does not
        support this function.
        """
        if isinstance(self.node, node.LocalNode):
            for pdo in self.map.values():
                pdo.stop()
        else:
            raise TypeError('The node type does not support this function.')


# Compatibility
Variable = PdoVariable
