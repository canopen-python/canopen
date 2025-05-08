import asyncio
import logging
import can
import canopen

# Set logging output
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


async def do_loop(network: canopen.Network, nodeid):

    # Create the node object and load the OD
    node: canopen.RemoteNode = network.add_node(nodeid, 'eds/e35.eds')

    # Get the PDOs from the remote
    await node.tpdo.aread()
    await node.rpdo.aread()

    # Set the remote state
    node.nmt.set_state('OPERATIONAL')

    # Set SDO
    await node.sdo['something'].aset_raw(2)

    i = 0
    while True:
        i += 1

        # Wait for PDO
        t = await node.tpdo[1].await_for_reception(1)
        if not t:
            continue

        # Get TPDO value
        # FIXME: Is this ok?
        state = node.tpdo[1]['state'].get_raw()

        # If state send RPDO to remote
        if state == 5:

            await asyncio.sleep(0.2)

            # Set RPDO and transmit
            # FIXME: Using set_phys() ok?
            node.rpdo[1]['count'].set_phys(i)
            node.rpdo[1].transmit()


async def amain():

    bus = can.Bus(interface='pcan', bitrate=1000000, recieve_own_messages=True)

    network = canopen.Network()
    network.bus = bus

    # Start the notifier
    loop = asyncio.get_event_loop()
    can.Notifier(bus, network.listeners, loop=loop)

    # Start two instances and run them concurrently
    await asyncio.gather(
        asyncio.create_task(do_loop(network, 20)),
        asyncio.create_task(do_loop(network, 21)),
    )


def main():
    asyncio.run(amain())

if __name__ == '__main__':
    main()
