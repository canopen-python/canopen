"""
LSS scanner

Performs a binary search using send_identify_remote_slave to all identify slaves
with a predefined vendor and product id.

"""

import queue
import canopen
import traceback
import time


class Range(object):
    '''
    Scan Range
    '''

    def __init__(self):
        '''
        construct a Range object
        '''
        self.q = queue.Queue()
        self.init()

    def init(self):
        self.q.queue.clear()
        self.q.put((0, 0xffffffff))
        self.current = None
        self.cnt = 0

    def next(self):
        self.current = None if self.q.empty() else self.q.get()
        return self.current

    def progress(self):
        pc = self.cnt
        pc *= 100.0
        pc /= 0x100000000
        return int(pc)

    def found(self, f):
        '''
        current range fouund
        '''
        assert self.current is not None
        if self.current[0] == self.current[1] or not f:
            self.cnt += self.current[1] - self.current[0] + 1
        else:
            d = self.current[1] - self.current[0]
            if d == 1:
                self.q.put((self.current[0], self.current[0]))
                self.q.put((self.current[1], self.current[1]))
            else:
                d >>= 1
                ne1 = self.current[0] + d, self.current[1]
                self.q.put(ne1)
                ne2 = self.current[0], ne1[0] - 1
                self.q.put(ne2)
        self.current = None



def identify_all(network, vendorId, productCode, interval = 0.1):

    network.nmt.state = 'STOPPED'
    time.sleep(interval)
    lss = network.lss

    ident = []
    revisions = []
    rev_iter = Range()

    while rev_iter.next() is not None:
        ser_iter = Range()
        ser_iter.next()
        f = lss.send_identify_remote_slave(vendorId, productCode,
                                       rev_iter.current[0], rev_iter.current[1],
                                       ser_iter.current[0], ser_iter.current[1])
        if f:
            print(rev_iter.current)
        time.sleep(interval)
        if f and rev_iter.current[0] == rev_iter.current[1]:
            revisions.append(rev_iter.current[0])
        rev_iter.found(f)

    for rev in revisions:
        ser_iter = Range()

        while ser_iter.next() is not None:
            f = lss.send_identify_remote_slave(vendorId, productCode,
                                        rev, rev,
                                        ser_iter.current[0], ser_iter.current[1])
            if f:
                print(ser_iter.current)
            time.sleep(interval)
            if f and ser_iter.current[0] == ser_iter.current[1]:
                lss.send_switch_state_global(lss.WAITING_STATE)
                time.sleep(interval)
                lss.send_switch_state_selective(vendorId, productCode, rev, ser_iter.current[0]);
                time.sleep(interval)
                node = lss.inquire_node_id()
                ident.append((vendorId, productCode, rev, ser_iter.current[0], node))
            ser_iter.found(f)

    network.nmt.state = 'PRE-OPERATIONAL'
    return ident




if __name__ == '__main__':

    VENDOR_ID = 0xFF
    PRODUCT_CODE = 1

    # Start with creating a network representing one CAN bus
    network = canopen.Network()
    # Connect to the CAN bus
    network.connect(channel='vcan0', bustype='socketcan')
    network.check()

    for _ in identify_all(network, VENDOR_ID, PRODUCT_CODE):
        print(_)

    # Disconnect from CAN bus
    if network:
        network.sync.stop()
        network.disconnect()

