import unittest

import canopen


def count_subscribers(network: canopen.Network) -> int:
    """Count the number of subscribers in the network."""
    return sum(len(n) for n in network.subscribers.values())


class TestLocalNode(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.network = canopen.Network()
        cls.network.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        cls.network.connect(interface="virtual")

        cls.node = canopen.LocalNode(2, canopen.objectdictionary.ObjectDictionary())

    @classmethod
    def tearDownClass(cls):
        cls.network.disconnect()

    def test_associate_network(self):
        # Need to store the number of subscribers before associating because the
        # network implementation automatically adds subscribers to the list
        n_subscribers = count_subscribers(self.network)

        # Associating the network with the local node
        self.node.associate_network(self.network)
        self.assertIs(self.node.network, self.network)
        self.assertIs(self.node.sdo.network, self.network)
        self.assertIs(self.node.tpdo.network, self.network)
        self.assertIs(self.node.rpdo.network, self.network)
        self.assertIs(self.node.nmt.network, self.network)
        self.assertIs(self.node.emcy.network, self.network)

        # Test that its not possible to associate the network multiple times
        with self.assertRaises(RuntimeError) as cm:
            self.node.associate_network(self.network)
        self.assertIn("already associated with a network", str(cm.exception))

        # Test removal of the network. The count of subscribers should
        # be the same as before the association
        self.node.remove_network()
        uninitalized = canopen.network._UNINITIALIZED_NETWORK
        self.assertIs(self.node.network, uninitalized)
        self.assertIs(self.node.sdo.network, uninitalized)
        self.assertIs(self.node.tpdo.network, uninitalized)
        self.assertIs(self.node.rpdo.network, uninitalized)
        self.assertIs(self.node.nmt.network, uninitalized)
        self.assertIs(self.node.emcy.network, uninitalized)
        self.assertEqual(count_subscribers(self.network), n_subscribers)

        # Test that its possible to deassociate the network multiple times
        self.node.remove_network()


class TestRemoteNode(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.network = canopen.Network()
        cls.network.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        cls.network.connect(interface="virtual")

        cls.node = canopen.RemoteNode(2, canopen.objectdictionary.ObjectDictionary())

    @classmethod
    def tearDownClass(cls):
        cls.network.disconnect()

    def test_associate_network(self):
        # Need to store the number of subscribers before associating because the
        # network implementation automatically adds subscribers to the list
        n_subscribers = count_subscribers(self.network)

        # Associating the network with the local node
        self.node.associate_network(self.network)
        self.assertIs(self.node.network, self.network)
        self.assertIs(self.node.sdo.network, self.network)
        self.assertIs(self.node.tpdo.network, self.network)
        self.assertIs(self.node.rpdo.network, self.network)
        self.assertIs(self.node.nmt.network, self.network)

        # Test that its not possible to associate the network multiple times
        with self.assertRaises(RuntimeError) as cm:
            self.node.associate_network(self.network)
        self.assertIn("already associated with a network", str(cm.exception))

        # Test removal of the network. The count of subscribers should
        # be the same as before the association
        self.node.remove_network()
        uninitalized = canopen.network._UNINITIALIZED_NETWORK
        self.assertIs(self.node.network, uninitalized)
        self.assertIs(self.node.sdo.network, uninitalized)
        self.assertIs(self.node.tpdo.network, uninitalized)
        self.assertIs(self.node.rpdo.network, uninitalized)
        self.assertIs(self.node.nmt.network, uninitalized)
        self.assertEqual(count_subscribers(self.network), n_subscribers)

        # Test that its possible to deassociate the network multiple times
        self.node.remove_network()
