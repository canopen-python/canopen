Service Data Object (SDO)
=========================

The SDO protocol is used for setting and for reading values from the
object dictionary of a remote device. The device whose object dictionary is
accessed is the SDO server and the device accessing the remote device is the SDO
client. The communication is always initiated by the SDO client. In CANopen
terminology, communication is viewed from the SDO server, so that a read from an
object dictionary results in an SDO upload and a write to a dictionary entry is
an SDO download.

Because the object dictionary values can be larger than the eight bytes limit of
a CAN frame, the SDO protocol implements segmentation and desegmentation of
longer messages. Actually, there are two of these protocols: SDO download/upload
and SDO Block download/upload. The SDO block transfer is a newer addition to
standard, which allows large amounts of data to be transferred with slightly
less protocol overhead.

The COB-IDs of the respective SDO transfer messages from client to server and
server to client can be set in the object dictionary. Up to 128 SDO servers can
be set up in the object dictionary at addresses 0x1200 - 0x127F. Similarly, the
SDO client connections of the device can be configured with variables at
0x1280 - 0x12FF. However the pre-defined connection set defines an SDO channel
which can be used even just after bootup (in the Pre-operational state) to
configure the device. The COB-IDs of this channel are 0x600 + node ID for
receiving and 0x580 + node ID for transmitting.


Examples
--------

SDO objects can be accessed using the ``.sdo`` member which works like a Python
dictionary. Indexes can be identified by either name or number.
There are two ways to idenity subindexes, either by using the index and subindex
as separate arguments or by using a combined syntax using a dot.
The code below only creates objects, no messages are sent or received yet::

    # Complex records
    command_all = node.sdo['ApplicationCommands']['CommandAll']
    command_all = node.sdo['ApplicationCommands.CommandAll']
    actual_speed = node.sdo['ApplicationStatus']['ActualSpeed']
    control_mode = node.sdo['ApplicationSetupParameters']['RequestedControlMode']

    # Simple variables
    device_type = node.sdo[0x1000]

    # Arrays
    error_log = node.sdo[0x1003]

To actually read or write the variables, use the ``.raw``, ``.phys``, ``.desc``,
or ``.bits`` attributes::

    print(f"The device type is 0x{device_type.raw:X}")

    # Using value descriptions instead of integers (if supported by OD)
    control_mode.desc = 'Speed Mode'

    # Set individual bit
    command_all.bits[3] = 1

    # Read and write physical values scaled by a factor (if supported by OD)
    print(f"The actual speed is {actual_speed.phys} rpm")

    # Iterate over arrays or records
    for error in error_log.values():
        print(f"Error 0x{error.raw:X} was found in the log")

It is also possible to read and write to variables that are not in the Object
Dictionary, but only using raw bytes::

    device_type_data = node.sdo.upload(0x1000, 0)
    node.sdo.download(0x1017, 0, b'\x00\x00')

Variables can be opened as readable or writable file objects which can be useful
when dealing with large amounts of data::

    # Open the Store EDS variable as a file like object
    with node.sdo[0x1021].open('r', encoding='ascii') as infile,
            open('out.eds', 'w', encoding='ascii') as outfile:

       # Iteratively read lines from node and write to file
       outfile.writelines(infile)

Most APIs accepting file objects should also be able to accept this.

Block transfer can be used to effectively transfer large amounts of data if the
server supports it. This is done through the file object interface::

    FIRMWARE_PATH = '/path/to/firmware.bin'
    FILESIZE = os.path.getsize(FIRMWARE_PATH)

    with open(FIRMWARE_PATH, 'rb') as infile,
            node.sdo['Firmware'].open('wb', size=FILESIZE, block_transfer=True) as outfile:

        # Iteratively transfer data without having to read all into memory
        while True:
            data = infile.read(1024)
            if not data:
                break
            outfile.write(data)

.. warning::
   Block transfer is still in experimental stage!


API
---

.. autoclass:: canopen.sdo.SdoClient
    :members:

    .. py:attribute:: od

       The :class:`canopen.ObjectDictionary` associated with this object.

    .. describe:: c[index]

       Return the SDO object for the specified index (as int) or name
       (as string).

    .. describe:: iter(c)

       Return an iterator over the indexes from the object dictionary.

    .. describe:: index in c

       Return ``True`` if the index (as int) or name (as string) exists in
       the object dictionary.

    .. describe:: len(c)

       Return the number of indexes in the object dictionary.

    .. method:: values()

       Return a list of objects (records, arrays and variables).


.. autoclass:: canopen.sdo.SdoServer
    :members:

    .. py:attribute:: od

       The :class:`canopen.ObjectDictionary` associated with this object.

    .. describe:: c[index]

       Return the SDO object for the specified index (as int) or name
       (as string).

    .. describe:: iter(c)

       Return an iterator over the indexes from the object dictionary.

    .. describe:: index in c

       Return ``True`` if the index (as int) or name (as string) exists in
       the object dictionary.

    .. describe:: len(c)

       Return the number of indexes in the object dictionary.

    .. method:: values()

       Return a list of objects (records, arrays and variables).


.. autoclass:: canopen.sdo.SdoVariable
    :members:
    :inherited-members:

    .. py:attribute:: od

       The :class:`canopen.objectdictionary.ODVariable` associated with this object.


.. autoclass:: canopen.sdo.SdoRecord
    :members:

    .. py:attribute:: od

       The :class:`canopen.objectdictionary.ODRecord` associated with this object.

    .. describe:: record[subindex]

       Return the :class:`canopen.sdo.SdoVariable` for the specified subindex
       (as int) or name (as string).

    .. describe:: iter(record)

       Return an iterator over the subindexes from the record.  Only those with
       a matching object dictionary entry are considered.  The "highest
       subindex" entry is officially not part of the data and thus skipped in
       the yielded values.

    .. describe:: subindex in record

       Return ``True`` if the subindex (as int) or name (as string) exists in
       the record.

    .. describe:: len(record)

       Return the number of subindexes in the record, not counting the "highest
       subindex" entry itself.  Only those with a matching object dictionary
       entry are considered.

    .. method:: values()

       Return a list of :class:`canopen.sdo.SdoVariable` in the record.


.. autoclass:: canopen.sdo.SdoArray
    :members:

    .. py:attribute:: od

       The :class:`canopen.objectdictionary.ODArray` associated with this object.

    .. describe:: array[subindex]

       Return the :class:`canopen.sdo.SdoVariable` for the specified subindex
       (as int) or name (as string).

    .. describe:: iter(array)

       Return an iterator over the subindexes from the array.
       This will make an SDO read operation on subindex 0 in order to get the
       actual length of the array.  This "highest subindex" entry is officially
       not part of the data and thus skipped in the yielded values.

    .. describe:: subindex in array

       Return ``True`` if the subindex (as int) or name (as string) exists in
       the array.
       This will make an SDO read operation on subindex 0 in order to get the
       actual length of the array.

    .. describe:: len(array)

       Return the length of the array, not counting the "highest subindex" entry
       itself.
       This will make an SDO read operation on subindex 0.

    .. method:: values()

       Return a list of :class:`canopen.sdo.SdoVariable` in the array.
       This will make an SDO read operation on subindex 0 in order to get the
       actual length of the array.


.. autoexception:: canopen.SdoAbortedError
    :show-inheritance:
    :members:

.. autoexception:: canopen.SdoCommunicationError
    :show-inheritance:
    :members:
