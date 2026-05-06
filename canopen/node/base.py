from typing import TextIO, Union

import canopen.network
from canopen.objectdictionary import ObjectDictionary, import_od


class BaseNode:
    """A CANopen node.

    :param node_id:
        Node ID (set to 0 if specified by object dictionary)
    :param object_dictionary:
        Object dictionary as either a path to a file, an ``ObjectDictionary``
        or a file like object.
    """

    def __init__(
        self,
        node_id: int,
        object_dictionary: Union[ObjectDictionary, str, TextIO],
    ):
        self.network: canopen.network.Network = canopen.network._UNINITIALIZED_NETWORK

        if not isinstance(object_dictionary, ObjectDictionary):
            object_dictionary = import_od(object_dictionary, node_id)
        self.object_dictionary = object_dictionary

        self.id = node_id or object_dictionary.node_id or 0
        if not self.id or not 1 <= self.id <= 127:
            raise ValueError("No valid Node ID provided, %r not in range 1..127")

    def has_network(self) -> bool:
        """Check whether the node has been associated to a network."""
        return not isinstance(self.network, canopen.network._UninitializedNetwork)
