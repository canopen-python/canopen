import canopen
import sys
import os
import traceback

import time

try:

    # Start with creating a network representing one CAN bus
    network = canopen.Network()

    # Connect to the CAN bus
    network.connect(bustype='kvaser', channel=0, bitrate=1000000)

    network.check()

    # Add some nodes with corresponding Object Dictionaries
    node = canopen.BaseNode402(35, '/home/andre/Code/test/jupiter.eds')
    network.add_node(node)
    # network.add_node(34, '/home/andre/Code/test/jupiter.eds')
    # node = network[34]

    # Reset network
    node.nmt.state = 'RESET COMMUNICATION'

    node.nmt.wait_for_bootup(15)

    print 'node state 1) = {0}'.format(node.nmt.state)

    # Iterate over arrays or records
    error_log = node.sdo[0x1003]
    for error in error_log.values():
        print "Error {0} was found in the log".format(error.raw)

    for node_id in network:
        print network[node_id]

    print 'node state 2) = {0}'.format(node.nmt.state)

    # Read a variable using SDO

    node.sdo[0x1006].raw = 1
    node.sdo[0x100c].raw = 100
    node.sdo[0x100d].raw = 3
    node.sdo[0x1014].raw = 163
    node.sdo[0x1003][0].raw = 0

    # Transmit SYNC every 100 ms
    network.sync.start(0.1)

    node.load_configuration()

    print 'node state 3) = {0}'.format(node.state)

    node.setup_402_state_machine()
    node.op_mode = 'PROFILED POSITION'

    device_name = node.sdo[0x1008].raw
    vendor_id = node.sdo[0x1018][1].raw

    print device_name
    print vendor_id

    print 'node state 4) = {0}'.format(node.nmt.state)

    # Read PDO configuration from node
    node.tpdo.read()
    # Re-map TxPDO1
    node.tpdo[1].clear()
    node.tpdo[1].add_variable('Statusword')
    node.tpdo[1].add_variable('Velocity actual value')
    node.tpdo[1].trans_type = 1
    node.tpdo[1].event_timer = 0
    node.tpdo[1].enabled = True
    # Save new PDO configuration to node
    node.tpdo.save()

    # publish the a value to the control word (in this case reset the fault at the motors)

    node.rpdo.read()
    node.rpdo[1]['Controlword'].raw = 0x80
    node.rpdo[1].transmit()
    node.rpdo[1][0x6040].raw = 0x81
    node.rpdo[1].transmit()

    node.rpdo.export('database.dbc')

    # -----------------------------------------------------------------------------------------

    try:
        node.state = 'OPERATION ENABLED'

    except RuntimeError as e:
        print e

    print 'Node Status {0}'.format(node.state)

    # -----------------------------------------------------------------------------------------
    node.nmt.start_node_guarding(0.01)

    time_test = time.time()
    reseted = False

    node.homing()

    while True:
        try:
            network.check()
        except Exception:
            break

        # Read a value from TxPDO1
        node.tpdo[1].wait_for_reception()
        speed = node.tpdo[1]['Velocity actual value'].phys

        print 'statusword: {0}'.format(node.statusword)
        print 'VEL: {0}'.format(speed)

        print node.pdo['0x6041'].raw

        time.sleep(0.001)

        if time.time() > time_test + 120 and not reseted:
            print 'Test the reset function'
            node.reset_from_fault()
            reseted = True

except KeyboardInterrupt:
    pass
except Exception as e:
    exc_type, exc_obj, exc_tb = sys.exc_info()
    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
    print(exc_type, fname, exc_tb.tb_lineno)
    traceback.print_exc()
finally:
    # Disconnect from CAN bus
    print 'going to exit... stoping...'
    if network is not None:
        for node_id in network:
            node = network[node_id]
            node.nmt.state = 'PRE-OPERATIONAL'
            node.nmt.stop_node_guarding()
        network.disconnect()

