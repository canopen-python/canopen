Network and nodes
=================

The :class:`canopen.Network` represents a collection of nodes connected to the
same CAN bus. This handles the sending and receiving of messages and dispatches
messages to the nodes it knows about.

Each node is represented using the :class:`canopen.RemoteNode` or
:class:`canopen.LocalNode` class. It is usually associated with an
object dictionary and each service has its own attribute owned by this node.


Examples
--------

Create one network per CAN bus::

    import canopen

    network = canopen.Network()

By default this library uses python-can_ for the actual communication.
See its documentation for specifics on how to configure your specific interface.

Call the :meth:`~canopen.Network.connect` method to start the communication, optionally providing
arguments passed to a the :class:`can.BusABC` constructor::

    network.connect(channel='can0', interface='socketcan')
    # network.connect(interface='kvaser', channel=0, bitrate=250000)
    # network.connect(interface='pcan', channel='PCAN_USBBUS1', bitrate=250000)
    # network.connect(interface='ixxat', channel=0, bitrate=250000)
    # network.connect(interface='nican', channel='CAN0', bitrate=250000)

Add nodes to the network using the :meth:`~canopen.Network.add_node` method::

    node = network.add_node(6, '/path/to/object_dictionary.eds')

    local_node = canopen.LocalNode(1, '/path/to/master_dictionary.eds')
    network.add_node(local_node)

Nodes can also be accessed using the ``Network`` object as a Python dictionary::

    for node_id in network:
        print(network[node_id])

To automatically detect which nodes are present on the network, there is the
:attr:`~canopen.Network.scanner` attribute available for this purpose::

    # This will attempt to read an SDO from nodes 1 - 127
    network.scanner.search()
    # We may need to wait a short while here to allow all nodes to respond
    time.sleep(0.05)
    for node_id in network.scanner.nodes:
        print(f"Found node {node_id}!")

Finally, make sure to disconnect after you are done::

    network.disconnect()


API
---

.. autoclass:: canopen.Network
   :members:

   .. py:attribute:: nmt

      The broadcast :class:`canopen.nmt.NmtMaster` which will affect all nodes.

   .. py:attribute:: sync

      The :class:`canopen.sync.SyncProducer` for this network.

   .. py:attribute:: time

      The :class:`canopen.timestamp.TimeProducer` for this network.

   .. describe:: network[node_id]

      Return the :class:`canopen.RemoteNode` or :class:`canopen.LocalNode` for
      the specified node ID.

   .. describe:: iter(network)

      Return an iterator over the handled node IDs.

   .. describe:: node_id in network

      Return ``True`` if the node ID exists is handled by this network.

   .. describe:: del network[node_id]

      Delete the node ID from the network.

   .. method:: values()

      Return a list of :class:`canopen.RemoteNode` or :class:`canopen.LocalNode`
      handled by this network.


.. autoclass:: canopen.RemoteNode
    :members:

    .. py:attribute:: id

       The node id (1 - 127). Changing this after initializing the object
       will not have any effect.

    .. py:attribute:: sdo

       The :class:`canopen.sdo.SdoClient` associated with the node.

    .. py:attribute:: sdo_channels

       List of available SDO channels (added with :meth:`add_sdo`).

    .. py:attribute:: tpdo

       The :class:`canopen.pdo.PdoBase` for TPDO associated with the node.

    .. py:attribute:: rpdo

       The :class:`canopen.pdo.PdoBase` for RPDO associated with the node.

    .. py:attribute:: nmt

       The :class:`canopen.nmt.NmtMaster` associated with the node.

    .. py:attribute:: emcy

       The :class:`canopen.emcy.EmcyConsumer` associated with the node.

    .. py:attribute:: object_dictionary

       The :class:`canopen.ObjectDictionary` associated with the node

    .. py:attribute:: network

       The :class:`canopen.Network` owning the node


.. autoclass:: canopen.LocalNode
    :members:

    .. py:attribute:: id

       The node id (1 - 127). Changing this after initializing the object
       will not have any effect.

    .. py:attribute:: sdo

       The :class:`canopen.sdo.SdoServer` associated with the node.

    .. py:attribute:: object_dictionary

       The :class:`canopen.ObjectDictionary` associated with the node

    .. py:attribute:: network

       The :class:`canopen.Network` owning the node


.. autoclass:: canopen.network.MessageListener
   :show-inheritance:
   :members:


.. autoclass:: canopen.network.NodeScanner
   :members:


.. autoclass:: canopen.network.PeriodicMessageTask
   :members:


.. _python-can: https://python-can.readthedocs.org/en/stable/
