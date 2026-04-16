from __future__ import annotations

import logging
from typing import TextIO, Union

import canopen.network
from canopen.emcy import EmcyConsumer
from canopen.nmt import NmtMaster
from canopen.node.base import BaseNode
from canopen.objectdictionary import ODArray, ODRecord, ODVariable, ObjectDictionary
from canopen.pdo import PDO, RPDO, TPDO
from canopen.sdo import SdoAbortedError, SdoClient, SdoCommunicationError


logger = logging.getLogger(__name__)


class RemoteNode(BaseNode):
    """A CANopen remote node.

    :param node_id:
        Node ID (set to None or 0 if specified by object dictionary)
    :param object_dictionary:
        Object dictionary as either a path to a file, an ``ObjectDictionary``
        or a file like object.
    :param load_od:
        Enable the Object Dictionary to be sent through SDO's to the remote
        node at startup.
    """

    def __init__(
        self,
        node_id: int,
        object_dictionary: Union[ObjectDictionary, str, TextIO],
        load_od: bool = False,
    ):
        super(RemoteNode, self).__init__(node_id, object_dictionary)

        #: Enable WORKAROUND for reversed PDO mapping entries
        self.curtis_hack = False

        self.sdo_channels = []
        self.sdo = self.add_sdo(0x600 + self.id, 0x580 + self.id)
        self.tpdo = TPDO(self)
        self.rpdo = RPDO(self)
        self.pdo = PDO(self, self.rpdo, self.tpdo)
        self.nmt = NmtMaster(self.id)
        self.emcy = EmcyConsumer()

        if load_od:
            self.load_configuration()

    def associate_network(self, network: canopen.network.Network):
        if self.has_network():
            raise RuntimeError("Node is already associated with a network")
        self.network = network
        self.sdo.network = network
        self.pdo.network = network
        self.tpdo.network = network
        self.rpdo.network = network
        self.nmt.network = network
        for sdo in self.sdo_channels:
            network.subscribe(sdo.tx_cobid, sdo.on_response)
        network.subscribe(0x700 + self.id, self.nmt.on_heartbeat)
        network.subscribe(0x80 + self.id, self.emcy.on_emcy)
        network.subscribe(0, self.nmt.on_command)

    def remove_network(self) -> None:
        if not self.has_network():
            return
        for sdo in self.sdo_channels:
            self.network.unsubscribe(sdo.tx_cobid, sdo.on_response)
        self.network.unsubscribe(0x700 + self.id, self.nmt.on_heartbeat)
        self.network.unsubscribe(0x80 + self.id, self.emcy.on_emcy)
        self.network.unsubscribe(0, self.nmt.on_command)
        self.network = canopen.network._UNINITIALIZED_NETWORK
        self.sdo.network = canopen.network._UNINITIALIZED_NETWORK
        self.pdo.network = canopen.network._UNINITIALIZED_NETWORK
        self.tpdo.network = canopen.network._UNINITIALIZED_NETWORK
        self.rpdo.network = canopen.network._UNINITIALIZED_NETWORK
        self.nmt.network = canopen.network._UNINITIALIZED_NETWORK

    def add_sdo(self, rx_cobid, tx_cobid):
        """Add an additional SDO channel.

        The SDO client will be added to :attr:`sdo_channels`.

        :param int rx_cobid:
            COB-ID that the server receives on
        :param int tx_cobid:
            COB-ID that the server responds with

        :return: The SDO client created
        :rtype: canopen.sdo.SdoClient
        """
        client = SdoClient(rx_cobid, tx_cobid, self.object_dictionary)
        self.sdo_channels.append(client)
        if self.has_network():
            self.network.subscribe(client.tx_cobid, client.on_response)
        return client

    def store(self, subindex=1):
        """Store parameters in non-volatile memory.

        :param int subindex:
            1 = All parameters\n
            2 = Communication related parameters\n
            3 = Application related parameters\n
            4 - 127 = Manufacturer specific
        """
        self.sdo.download(0x1010, subindex, b"save")

    def restore(self, subindex=1):
        """Restore default parameters.

        :param int subindex:
            1 = All parameters\n
            2 = Communication related parameters\n
            3 = Application related parameters\n
            4 - 127 = Manufacturer specific
        """
        self.sdo.download(0x1011, subindex, b"load")

    def __load_configuration_helper(self, index, subindex, name, value):
        """Helper function to send SDOs to the remote node
        :param index: Object index
        :param subindex: Object sub-index (if it does not exist e should be None)
        :param name: Object name
        :param value: Value to set in the object
        """
        try:
            if subindex is not None:
                logger.info('SDO [0x%04X][0x%02X]: %s: %#06x',
                            index, subindex, name, value)
                self.sdo[index][subindex].raw = value
            else:
                self.sdo[index].raw = value
                logger.info('SDO [0x%04X]: %s: %#06x',
                            index, name, value)
        except SdoCommunicationError as e:
            logger.warning(str(e))
        except SdoAbortedError as e:
            # WORKAROUND for broken implementations: the SDO is set but the error
            # "Attempt to write a read-only object" is raised any way.
            if e.code != 0x06010002:
                # Abort codes other than "Attempt to write a read-only object"
                # should still be reported.
                logger.warning('[ERROR SETTING object 0x%04X:%02X] %s',
                               index, subindex, e)
                raise

    def load_configuration(self) -> None:
        """Load the configuration of the node from the Object Dictionary.

        Iterate through all objects in the Object Dictionary and download the
        values to the remote node via SDO.
        To avoid PDO mapping conflicts, PDO-related objects are handled through
        the methods :meth:`canopen.pdo.PdoBase.read` and
        :meth:`canopen.pdo.PdoBase.save`.

        """
        # First apply PDO configuration from object dictionary
        self.pdo.read(from_od=True)
        self.pdo.save()

        # Now apply all other records in object dictionary
        for obj in self.object_dictionary.values():
            if 0x1400 <= obj.index < 0x1c00:
                # Ignore PDO related objects
                continue
            if isinstance(obj, ODRecord) or isinstance(obj, ODArray):
                for subobj in obj.values():
                    if isinstance(subobj, ODVariable) and subobj.writable and (subobj.value is not None):
                        self.__load_configuration_helper(subobj.index, subobj.subindex, subobj.name, subobj.value)
            elif isinstance(obj, ODVariable) and obj.writable and (obj.value is not None):
                self.__load_configuration_helper(obj.index, None, obj.name, obj.value)
