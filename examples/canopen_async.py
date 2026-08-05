import asyncio
import logging
import canopen

# Set logging output
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


async def do_loop(network: canopen.Network, nodeid):

    # Create the node object and load the OD
    node: canopen.RemoteNode = await network.add_node(nodeid, 'eds/e35.eds')

    # Get the PDOs from the remote
    await node.tpdo.aread(from_od=False)
    await node.rpdo.aread(from_od=False)

    # Set the remote state
    node.nmt.state = 'OPERATIONAL'

    # Set SDO
    await node.sdo['something'].awrite(2)

    i = 0
    while True:
        i += 1

        # Wait for PDO
        t = await node.tpdo[1].await_for_reception(1)
        if not t:
            continue

        # Get TPDO value
        # PDO values are accessed directly, no await required
        state = node.tpdo[1]['state'].raw

        # If state send RPDO to remote
        if state == 5:

            await asyncio.sleep(0.2)

            # Set RPDO and transmit
            node.rpdo[1]['count'].phys = i
            node.rpdo[1].transmit()


async def amain():

    # Create the canopen network and connect it to the CAN bus
    async with canopen.Network().connect(
        interface='virtual', bitrate=1000000, receive_own_messages=True
    ) as network:

        # Start two instances and run them concurrently
        network.create_task(do_loop(network, 20))
        network.create_task(do_loop(network, 21))


def main():
    asyncio.run(amain())

if __name__ == '__main__':
    main()
