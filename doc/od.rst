Object Dictionary
=================

CANopen devices must have an object dictionary, which is used for configuration
and communication with the device.
An entry in the object dictionary is defined by:

* Index, the 16-bit address of the object in the dictionary
* Object type, such as an array, record, or simple variable
* Name, a string describing the entry
* Type, gives the datatype of the variable
  (or the datatype of all variables of an array)
* Attribute, which gives information on the access rights for this entry,
  this can be read/write (rw), read-only (ro) or write-only (wo)

The basic datatypes for object dictionary values such as booleans, integers and
floats are defined in the standard, as well as composite datatypes such as
strings, arrays and records. The composite datatypes can be subindexed with an
8-bit index; the value in subindex 0 of an array or record indicates the number
of elements in the data structure, and is of type UNSIGNED8.


Supported formats
-----------------

The currently supported file formats for specifying a node's object dictionary
are:

* EDS (standardized INI-file like format)
* DCF (same as EDS with bitrate and node ID specified)
* EPF (proprietary XML-format used by Inmotion Technologies)


Examples
--------

The object dictionary file is normally provided when creating a node.
Here is an example where the entire object dictionary gets printed out::

    node = network.add_node(6, 'od.eds')
    for obj in node.object_dictionary.values():
        print(f'0x{obj.index:X}: {obj.name}')
        if isinstance(obj, canopen.objectdictionary.ODRecord):
            for subobj in obj.values():
                print(f'  {subobj.subindex}: {subobj.name}')

You can access the objects using either index/subindex or names::

    device_name_obj = node.object_dictionary['ManufacturerDeviceName']
    vendor_id_obj = node.object_dictionary[0x1018][1]
    actual_speed = node.object_dictionary['ApplicationStatus.ActualSpeed']
    command_all = node.object_dictionary['ApplicationCommands.CommandAll']

API
---

.. autofunction:: canopen.export_od

.. autofunction:: canopen.import_od

.. autoclass:: canopen.ObjectDictionary
   :members:

   .. describe:: od[index]

      Return the object for the specified index (as int) or name
      (as string).

   .. describe:: iter(od)

      Return an iterator over the indexes from the object dictionary.

   .. describe:: index in od

      Return ``True`` if the index (as int) or name (as string) exists in
      the object dictionary.

   .. describe:: len(od)

      Return the number of objects in the object dictionary.

   .. method:: values()

      Return a list of objects (records, arrays and variables).


.. autoclass:: canopen.objectdictionary.ODVariable
   :members:

   .. describe:: len(var)

      Return the length of the variable data type in number of bits.

   .. describe:: var == other

      Return ``True`` if the variables have the same index and subindex.


.. autoclass:: canopen.objectdictionary.ODRecord
   :members:

   .. describe:: record[subindex]

      Return the :class:`~canopen.objectdictionary.ODVariable` for the specified
      subindex (as int) or name (as string).

   .. describe:: iter(record)

      Return an iterator over the subindexes from the record.

   .. describe:: subindex in record

      Return ``True`` if the subindex (as int) or name (as string) exists in
      the record.

   .. describe:: len(record)

      Return the number of subindexes in the record.

   .. describe:: record == other

      Return ``True`` if the records have the same index.

   .. method:: values()

      Return a list of :class:`~canopen.objectdictionary.ODVariable` in the record.


.. autoclass:: canopen.objectdictionary.ODArray
   :members:

   .. describe:: array[subindex]

      Return the :class:`~canopen.objectdictionary.ODVariable` for the specified
      subindex (as int) or name (as string).
      This will work for all subindexes between 1 and 255. If the requested
      subindex has not been specified in the object dictionary, it will be
      created dynamically from the first subindex and suffixing the name with
      an underscore + the subindex in hex format.


.. autoexception:: canopen.ObjectDictionaryError
   :members:


Constants
~~~~~~~~~

.. py:data:: canopen.objectdictionary.UNSIGNED8
.. py:data:: canopen.objectdictionary.UNSIGNED16
.. py:data:: canopen.objectdictionary.UNSIGNED32
.. py:data:: canopen.objectdictionary.UNSIGNED64

.. py:data:: canopen.objectdictionary.INTEGER8
.. py:data:: canopen.objectdictionary.INTEGER16
.. py:data:: canopen.objectdictionary.INTEGER32
.. py:data:: canopen.objectdictionary.INTEGER64

.. py:data:: canopen.objectdictionary.BOOLEAN

.. py:data:: canopen.objectdictionary.REAL32
.. py:data:: canopen.objectdictionary.REAL64

.. py:data:: canopen.objectdictionary.VISIBLE_STRING
.. py:data:: canopen.objectdictionary.OCTET_STRING
.. py:data:: canopen.objectdictionary.UNICODE_STRING
.. py:data:: canopen.objectdictionary.DOMAIN


.. py:data:: canopen.objectdictionary.SIGNED_TYPES
.. py:data:: canopen.objectdictionary.UNSIGNED_TYPES
.. py:data:: canopen.objectdictionary.INTEGER_TYPES
.. py:data:: canopen.objectdictionary.FLOAT_TYPES
.. py:data:: canopen.objectdictionary.NUMBER_TYPES
.. py:data:: canopen.objectdictionary.DATA_TYPES
