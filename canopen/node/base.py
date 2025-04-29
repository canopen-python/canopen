from typing import TextIO, Union, Optional

import canopen.network
from canopen.objectdictionary import ObjectDictionary, import_od


class BaseNode:
    """A CANopen node.

    :param node_id:
        Node ID (set to None or 0 if specified by object dictionary)
    :param object_dictionary:
        Object dictionary as either a path to a file, an ``ObjectDictionary``
        or a file like object.
    """

    def __init__(
        self,
        node_id: Optional[int],
        object_dictionary: Union[ObjectDictionary, str, TextIO, None],
    ):
        self.network: canopen.network.Network = canopen.network._UNINITIALIZED_NETWORK

        if not isinstance(object_dictionary, ObjectDictionary):
            object_dictionary = import_od(object_dictionary, node_id)
        self.object_dictionary = object_dictionary

        node_id = node_id or self.object_dictionary.node_id
        if node_id is None:
            raise ValueError("Node ID must be specified")
        self.id: int = node_id

    def has_network(self) -> bool:
        """Check whether the node has been associated to a network."""
        return not isinstance(self.network, canopen.network._UninitializedNetwork)
