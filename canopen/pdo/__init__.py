import itertools
import logging
from collections.abc import Iterator, Mapping
from typing import Union

from canopen import node
from canopen.pdo.base import PdoBase, PdoMap, PdoMaps, PdoVariable


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


class _CombinedPdoMaps(Mapping[int, PdoMap]):
    """Combine RPDO and TPDO :class:`PdoMaps` without dummy zero offsets.

    Avoids ``PdoMaps(0, 0, …)`` where ``__getitem__`` fallbacks would alias
    ``key`` to ``key + 1`` (see discussion on PR #613).
    """

    def __init__(self, rx: PdoMaps, tx: PdoMaps):
        self.rx = rx
        self.tx = tx

    def __getitem__(self, key: int) -> PdoMap:
        for maps in (self.rx, self.tx):
            try:
                return maps[key]
            except KeyError:
                continue
        raise KeyError(key)

    def __iter__(self) -> Iterator[int]:
        return itertools.chain(
            (self.rx.map_offset + i - 1 for i in self.rx),
            (self.tx.map_offset + i - 1 for i in self.tx),
        )

    def __len__(self) -> int:
        return len(self.rx) + len(self.tx)


class PDO(PdoBase):
    """PDO Class for backwards compatibility.

    :param rpdo: RPDO object holding the Receive PDO mappings
    :param tpdo: TPDO object holding the Transmit PDO mappings
    """

    def __init__(self, node, rpdo, tpdo):
        super(PDO, self).__init__(node)
        self.rx = rpdo.map
        self.tx = tpdo.map
        self.map = _CombinedPdoMaps(self.rx, self.tx)

    def __getitem__(self, key: Union[int, str]):
        if isinstance(key, int):
            if key == 0:
                raise KeyError("PDO index zero requested for 1-based sequence")
            if 0 < key <= 512:
                return self.map[key]
            if 0x1400 <= key <= 0x17FF:
                return self.rx[key]
            if 0x1800 <= key <= 0x1BFF:
                return self.tx[key]
        for pdo_map in self.map.values():
            try:
                return pdo_map[key]
            except KeyError:
                continue
        raise KeyError(f"PDO: {key} was not found in any map")


class RPDO(PdoBase):
    """Receive PDO to transfer data from somewhere to the represented node.

    Properties 0x1400 to 0x15FF | Mapping 0x1600 to 0x17FF.
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

    Properties 0x1800 to 0x19FF | Mapping 0x1A00 to 0x1BFF.
    :param object node: Parent node for this object.
    """

    def __init__(self, node):
        super(TPDO, self).__init__(node)
        self.map = PdoMaps(0x1800, 0x1A00, self, 0x180)
        logger.debug('TPDO Map as %d', len(self.map))

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
