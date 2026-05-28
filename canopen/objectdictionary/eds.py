from __future__ import annotations

import copy
import logging
import re
from configparser import NoOptionError, NoSectionError, RawConfigParser
from typing import Any, TYPE_CHECKING

from canopen.objectdictionary import (
    ODArray,
    ODRecord,
    ODVariable,
    ObjectDictionary,
    datatypes,
    objectcodes,
)
from canopen.sdo import SdoClient

if TYPE_CHECKING:
    import canopen.network


logger = logging.getLogger(__name__)


def import_eds(source, node_id):
    eds = RawConfigParser(inline_comment_prefixes=(';',))
    eds.optionxform = str
    opened_here = False
    try:
        if hasattr(source, "read"):
            fp = source
        else:
            fp = open(source)
            opened_here = True
        eds.read_file(fp)
    finally:
        # Only close object if opened in this fn
        if opened_here:
            fp.close()

    od = ObjectDictionary()

    if eds.has_section("FileInfo"):
        od.__edsFileInfo = {  # type: ignore[attr-defined] # custom addition
            opt: eds.get("FileInfo", opt)
            for opt in eds.options("FileInfo")
        }

    if eds.has_section("Comments"):
        linecount = int(eds.get("Comments", "Lines"), 0)
        od.comments = '\n'.join([
            eds.get("Comments", f"Line{line}")
            for line in range(1, linecount + 1)
        ])

    if not eds.has_section("DeviceInfo"):
        logger.warn("eds file does not have a DeviceInfo section. This section is mandatory")
    else:
        for rate in [10, 20, 50, 125, 250, 500, 800, 1000]:
            baudPossible = int(
                eds.get("DeviceInfo", f"BaudRate_{rate}", fallback='0'), 0)
            if baudPossible != 0:
                od.device_information.allowed_baudrates.add(rate*1000)

        for t, eprop, odprop in [
            (str, "VendorName", "vendor_name"),
            (int, "VendorNumber", "vendor_number"),
            (str, "ProductName", "product_name"),
            (int, "ProductNumber", "product_number"),
            (int, "RevisionNumber", "revision_number"),
            (str, "OrderCode", "order_code"),
            (bool, "SimpleBootUpMaster", "simple_boot_up_master"),
            (bool, "SimpleBootUpSlave", "simple_boot_up_slave"),
            (bool, "Granularity", "granularity"),
            (bool, "DynamicChannelsSupported", "dynamic_channels_supported"),
            (bool, "GroupMessaging", "group_messaging"),
            (int, "NrOfRXPDO", "nr_of_RXPDO"),
            (int, "NrOfTXPDO", "nr_of_TXPDO"),
            (bool, "LSS_Supported", "LSS_supported"),
        ]:
            try:
                if t in (int, bool):
                    setattr(od.device_information, odprop,
                            t(int(eds.get("DeviceInfo", eprop), 0))
                            )
                elif t is str:
                    setattr(od.device_information, odprop,
                            eds.get("DeviceInfo", eprop)
                            )
            except NoOptionError:
                pass

    if eds.has_section("DeviceComissioning"):
        if val := eds.getint("DeviceComissioning", "Baudrate", fallback=None):
            od.bitrate = val * 1000

        if node_id is None:
            if val := eds.get("DeviceComissioning", "NodeID", fallback=None):
                node_id = int(val, base=0)
        od.node_id = node_id

    DUMMY_SECTION_REGEX = re.compile(r"^[Dd]ummy[Uu]sage$")
    INDEX_SECTION_REGEX = re.compile(r"^[0-9A-Fa-f]{4}$")
    SUB_SECTION_REGEX = re.compile(r"^([0-9A-Fa-f]{4})[S|s]ub([0-9A-Fa-f]+)$")
    NAME_SECTION_REGEX = re.compile(r"^([0-9A-Fa-f]{4})Name")
    for section in eds.sections():
        if DUMMY_SECTION_REGEX.match(section) is not None:
            for i in range(1, 8):
                key = f"Dummy{i:04d}"
                if eds.getint(section, key) == 1:
                    var = ODVariable(key, i, 0)
                    var.data_type = i
                    var.access_type = "const"
                    od.add_object(var)

        if INDEX_SECTION_REGEX.match(section) is not None:
            index = int(section, 16)
            name = eds.get(section, "ParameterName")
            try:
                object_type = int(eds.get(section, "ObjectType"), 0)
            except NoOptionError:
                # DS306 4.6.3.2 object description
                # If the keyword ObjectType is missing, this is regarded as
                # "ObjectType=0x7" (=VAR).
                object_type = objectcodes.VAR
            try:
                storage_location = eds.get(section, "StorageLocation")
            except NoOptionError:
                storage_location = None

            if object_type in (objectcodes.VAR, objectcodes.DOMAIN):
                var = build_variable(eds, section, node_id, object_type, index)
                od.add_object(var)
            elif object_type == objectcodes.ARRAY and eds.has_option(section, "CompactSubObj"):
                arr = ODArray(name, index)
                last_subindex = ODVariable("Number of entries", index, 0)
                last_subindex.data_type = datatypes.UNSIGNED8
                arr.add_member(last_subindex)
                arr.add_member(build_variable(eds, section, node_id, object_type, index, 1))
                arr.storage_location = storage_location
                arr.custom_options = _get_custom_options(eds, section)
                od.add_object(arr)
            elif object_type == objectcodes.ARRAY:
                arr = ODArray(name, index)
                arr.storage_location = storage_location
                arr.custom_options = _get_custom_options(eds, section)
                od.add_object(arr)
            elif object_type == objectcodes.RECORD:
                record = ODRecord(name, index)
                record.storage_location = storage_location
                record.custom_options = _get_custom_options(eds, section)
                od.add_object(record)

            continue

        if (m := SUB_SECTION_REGEX.match(section)) is not None:
            index = int(m.group(1), 16)
            subindex = int(m.group(2), 16)
            entry = od[index]
            if isinstance(entry, (ODRecord, ODArray)):
                try:
                    object_type = int(eds.get(section, "ObjectType"), 0)
                except NoOptionError:
                    object_type = objectcodes.VAR
                var = build_variable(eds, section, node_id, object_type, index, subindex)
                entry.add_member(var)

        # Match [index]Name
        if (m := NAME_SECTION_REGEX.match(section)) is not None:
            index = int(m.group(1), 16)
            num_of_entries = int(eds.get(section, "NrOfEntries"))
            entry = od[index]
            # For CompactSubObj index 1 is were we find the variable
            src_var = od[index][1]
            for subindex in range(1, num_of_entries + 1):
                var = copy_variable(eds, section, subindex, src_var)
                if var is not None:
                    entry.add_member(var)

    return od


def import_from_node(node_id: int, network: canopen.network.Network):
    """ Download the configuration from the remote node
    :param int node_id: Identifier of the node
    :param network: network object
    """
    # Create temporary SDO client
    sdo_client = SdoClient(0x600 + node_id, 0x580 + node_id, ObjectDictionary())
    sdo_client.network = network
    # Subscribe to SDO responses
    network.subscribe(0x580 + node_id, sdo_client.on_response)
    # Create file like object for Store EDS variable
    try:
        with sdo_client.open(0x1021, 0, "rt") as eds_fp:
            od = import_eds(eds_fp, node_id)
    except Exception as e:
        logger.error("No object dictionary could be loaded for node %d: %s",
                     node_id, e)
        od = None
    finally:
        network.unsubscribe(0x580 + node_id)
    return od


def _calc_bit_length(data_type: int) -> int:
    if data_type in datatypes.INTEGER_TYPES:
        st = ODVariable.STRUCT_TYPES[data_type]
        if isinstance(st, datatypes.IntegerN):
            return st.width
        return st.size * 8
    else:
        raise ValueError(
            f"Invalid data_type 0x{data_type:04X}, expecting an integer data_type."
        )


def _signed_int_from_hex(hex_str, bit_length):
    number = int(hex_str, 0)
    min_signed = -(1 << (bit_length - 1))
    max_signed = (1 << (bit_length - 1)) - 1
    max_unsigned = (1 << bit_length) - 1

    if number < min_signed:
        raise ValueError(
            f"Value {hex_str!r} is out of range for a {bit_length}-bit signed integer"
        )
    if number < 0:
        # Negative literal (e.g. LowLimit=-32768 or -0x8000)
        return number

    if number > max_unsigned:
        raise ValueError(
            f"Value {hex_str!r} is out of range for a {bit_length}-bit signed integer"
        )
    if number > max_signed:
        # Unsigned hex literal, two's-complement (e.g. LowLimit=0xFFFF → -1 for INTEGER16)
        return number - (1 << bit_length)
    return number


def _decode_from_eds(node_id: int, var_type: int, value: Any) -> Any:
    if var_type in (datatypes.OCTET_STRING, datatypes.DOMAIN):
        return bytes.fromhex(value)
    if var_type in (datatypes.VISIBLE_STRING, datatypes.UNICODE_STRING):
        return value
    if var_type in datatypes.FLOAT_TYPES:
        return float(value)
    # COB-ID can contain '$NODEID+' so replace this with node_id before converting
    value = value.replace(" ", "").upper()
    if '$NODEID' in value and node_id is not None:
        return int(re.sub(r'\+?\$NODEID\+?', '', value), 0) + node_id
    return int(value, 0)


def _encode_to_eds(var_type: int, value: Any) -> Any:
    if value is None:
        return None
    if var_type in (datatypes.OCTET_STRING, datatypes.DOMAIN):
        return bytes.hex(value)
    if var_type in (datatypes.VISIBLE_STRING, datatypes.UNICODE_STRING):
        return value
    if var_type in datatypes.FLOAT_TYPES:
        return value
    return f"0x{value:02X}"


_STANDARD_OPTIONS = {
    "ObjectType", "ParameterName", "DataType", "AccessType",
    "PDOMapping", "LowLimit", "HighLimit", "DefaultValue",
    "ParameterValue", "Factor", "Description", "Unit",
    "StorageLocation", "CompactSubObj",
    # CiA 306 fields parsed explicitly:
    "SubNumber",
    # ObjFlags and Denotation are intentionally absent: they are not yet
    # parsed by this codebase, so they flow through custom_options and
    # survive round-trips. Proper first-class support is tracked in #654.
}


def _get_custom_options(eds: RawConfigParser, section: str) -> dict[str, str]:
    custom_options = {}
    for option, value in eds.items(section):
        if option not in _STANDARD_OPTIONS:
            custom_options[option] = value
    return custom_options


def build_variable(
    eds: RawConfigParser,
    section: str,
    node_id: int,
    object_type: int,
    index: int,
    subindex: int = 0
) -> ODVariable:
    """Create a object dictionary entry.

    :param eds: String stream of the eds file
    :param section:
    :param node_id: Node ID
    :param index: Index of the CANOpen object
    :param subindex: Subindex of the CANOpen object (if present, else 0)
    :param is_domain: variable represents a DOMAIN ObjectType (if present, else False)
    """
    name = eds.get(section, "ParameterName")
    var = ODVariable(name, index, subindex)
    try:
        var.storage_location = eds.get(section, "StorageLocation")
    except NoOptionError:
        var.storage_location = None
    var.data_type = int(eds.get(section, "DataType"), 0)
    var.access_type = eds.get(section, "AccessType").lower()
    var.is_domain = object_type == objectcodes.DOMAIN
    if var.data_type > 0x1B:
        # The object dictionary editor from CANFestival creates an optional object if min max
        # values are used.  This optional object is then placed in the eds under the section
        # [A0] (start point, iterates for more).  The eds.get function gives us 0x00A0 now
        # convert to String without hex representation and upper case.  The sub2 part is then
        # the section where the type parameter stands.
        try:
            var.data_type = int(eds.get(f"{var.data_type:X}sub1", "DefaultValue"), 0)
        except NoSectionError:
            logger.warning(
                "%s has an unknown or unsupported data type (0x%X)", name, var.data_type
            )
            # Assume DOMAIN to force application to interpret the byte data
            var.data_type = datatypes.DOMAIN

    var.pdo_mappable = bool(int(eds.get(section, "PDOMapping", fallback="0"), 0))

    if (raw_string := eds.get(section, "LowLimit", fallback=None)) is not None:
        try:
            if var.data_type in datatypes.SIGNED_TYPES:
                var.min = _signed_int_from_hex(raw_string, _calc_bit_length(var.data_type))
            else:
                var.min = int(raw_string, 0)
        except ValueError:
            logger.warning(
                "Invalid LowLimit %r for %s (0x%X), ignoring", raw_string, var.name, var.index
            )
    if (raw_string := eds.get(section, "HighLimit", fallback=None)) is not None:
        try:
            if var.data_type in datatypes.SIGNED_TYPES:
                var.max = _signed_int_from_hex(raw_string, _calc_bit_length(var.data_type))
            else:
                var.max = int(raw_string, 0)
        except ValueError:
            logger.warning(
                "Invalid HighLimit %r for %s (0x%X), ignoring", raw_string, var.name, var.index
            )
    if (raw_string := eds.get(section, "DefaultValue", fallback=None)) is not None:
        var.default_raw = raw_string  # type: ignore[attr-defined] # custom round-trip addition
        try:
            if '$NODEID' in raw_string:
                var.relative = True
            var.default = _decode_from_eds(node_id, var.data_type, raw_string)
        except ValueError:
            logger.warning(
                "Invalid DefaultValue %r for %s (0x%X), ignoring",
                raw_string, var.name, var.index,
            )
    if (raw_string := eds.get(section, "ParameterValue", fallback=None)) is not None:
        var.value_raw = raw_string  # type: ignore[attr-defined] # custom round-trip addition
        try:
            var.value = _decode_from_eds(node_id, var.data_type, raw_string)
        except ValueError:
            logger.warning(
                "Invalid ParameterValue %r for %s (0x%X), ignoring",
                raw_string, var.name, var.index,
            )
    # Factor, Description and Unit are not standard according to the CANopen specifications, but
    # they are implemented in the python canopen package, so we can at least try to use them
    if (raw_string := eds.get(section, "Factor", fallback=None)) is not None:
        try:
            var.factor = float(raw_string)
        except ValueError:
            logger.warning(
                "Invalid Factor %r for %s (0x%X), ignoring", raw_string, var.name, var.index
            )
    if (raw_string := eds.get(section, "Description", fallback=None)) is not None:
        var.description = raw_string
    if (raw_string := eds.get(section, "Unit", fallback=None)) is not None:
        var.unit = raw_string

    var.custom_options = _get_custom_options(eds, section)
    return var


def copy_variable(eds, section, subindex, src_var):
    name = eds.get(section, str(subindex))
    var = copy.copy(src_var)
    # It is only the name and subindex that varies
    var.name = name
    var.subindex = subindex
    return var


def export_dcf(od, dest=None, fileInfo={}):
    return export_eds(od, dest, fileInfo, True)


def export_eds(od, dest=None, file_info={}, device_commisioning=False):
    def export_object(obj, eds):
        if isinstance(obj, ODVariable):
            return export_variable(obj, eds)
        if isinstance(obj, ODRecord):
            return export_record(obj, eds)
        if isinstance(obj, ODArray):
            return export_array(obj, eds)

    def export_common(var, eds, section):
        eds.add_section(section)
        eds.set(section, "ParameterName", var.name)
        if var.storage_location:
            eds.set(section, "StorageLocation", var.storage_location)

    def export_variable(var, eds):
        if isinstance(var.parent, ObjectDictionary):
            # top level variable
            section = f"{var.index:04X}"
        else:
            # nested variable
            section = f"{var.index:04X}sub{var.subindex:X}"

        export_common(var, eds, section)
        object_type = objectcodes.DOMAIN if var.is_domain else objectcodes.VAR
        eds.set(section, "ObjectType", f"0x{object_type:X}")
        if var.data_type:
            eds.set(section, "DataType", f"0x{var.data_type:04X}")
        if var.access_type:
            eds.set(section, "AccessType", var.access_type)

        if getattr(var, 'default_raw', None) is not None:
            eds.set(section, "DefaultValue", var.default_raw)
        elif var.default is not None:
            eds.set(section, "DefaultValue", _encode_to_eds(var.data_type, var.default))

        if device_commisioning:
            if getattr(var, 'value_raw', None) is not None:
                eds.set(section, "ParameterValue", var.value_raw)
            elif var.value is not None:
                eds.set(section, "ParameterValue", _encode_to_eds(var.data_type, var.value))

        eds.set(section, "DataType", f"0x{var.data_type:04X}")
        eds.set(section, "PDOMapping", hex(var.pdo_mappable))

        if var.min is not None:
            eds.set(section, "LowLimit", var.min)
        if var.max is not None:
            eds.set(section, "HighLimit", var.max)

        if var.description != '':
            eds.set(section, "Description", var.description)
        if var.factor != 1:
            eds.set(section, "Factor", var.factor)
        if var.unit != '':
            eds.set(section, "Unit", var.unit)

        for option, value in var.custom_options.items():
            if option not in _STANDARD_OPTIONS:
                eds.set(section, option, str(value))

    def export_record(var, eds):
        section = f"{var.index:04X}"
        export_common(var, eds, section)
        eds.set(section, "SubNumber", f"0x{len(var.subindices):X}")
        ot = objectcodes.RECORD if isinstance(var, ODRecord) else objectcodes.ARRAY
        eds.set(section, "ObjectType", f"0x{ot:X}")
        for option, value in var.custom_options.items():
            if option not in _STANDARD_OPTIONS:
                eds.set(section, option, str(value))
        for i in var:
            export_variable(var[i], eds)

    export_array = export_record

    eds = RawConfigParser()
    # both disables lowercasing, and allows int keys
    eds.optionxform = str

    from datetime import datetime as dt
    defmtime = dt.utcnow()

    try:
        # only if eds was loaded by us
        origFileInfo = od.__edsFileInfo  # type: ignore[attr-defined] # custom addition
    except AttributeError:
        origFileInfo = {
            # just set some defaults
            "CreationDate": defmtime.strftime("%m-%d-%Y"),
            "CreationTime": defmtime.strftime("%I:%m%p"),
            "EdsVersion": 4.2,
        }

    file_info.setdefault("ModificationDate", defmtime.strftime("%m-%d-%Y"))
    file_info.setdefault("ModificationTime", defmtime.strftime("%I:%m%p"))
    for k, v in origFileInfo.items():
        file_info.setdefault(k, v)

    eds.add_section("FileInfo")
    for k, v in file_info.items():
        eds.set("FileInfo", k, v)

    eds.add_section("DeviceInfo")
    for eprop, odprop in [
        ("VendorName", "vendor_name"),
        ("VendorNumber", "vendor_number"),
        ("ProductName", "product_name"),
        ("ProductNumber", "product_number"),
        ("RevisionNumber", "revision_number"),
        ("OrderCode", "order_code"),
        ("SimpleBootUpMaster", "simple_boot_up_master"),
        ("SimpleBootUpSlave", "simple_boot_up_slave"),
        ("Granularity", "granularity"),
        ("DynamicChannelsSupported", "dynamic_channels_supported"),
        ("GroupMessaging", "group_messaging"),
        ("NrOfRXPDO", "nr_of_RXPDO"),
        ("NrOfTXPDO", "nr_of_TXPDO"),
        ("LSS_Supported", "LSS_supported"),
    ]:
        val = getattr(od.device_information, odprop, None)
        if val is None:
            continue
        elif isinstance(val, str):
            eds.set("DeviceInfo", eprop, val)
        elif isinstance(val, (int, bool)):
            eds.set("DeviceInfo", eprop, int(val))

    # we are also adding out of spec baudrates here.
    for rate in od.device_information.allowed_baudrates.union(
            {10e3, 20e3, 50e3, 125e3, 250e3, 500e3, 800e3, 1000e3}):
        eds.set(
            "DeviceInfo", f"BaudRate_{int(rate//1000)}",
            int(rate in od.device_information.allowed_baudrates))

    if device_commisioning and (od.bitrate or od.node_id):
        eds.add_section("DeviceComissioning")
        if od.bitrate:
            eds.set("DeviceComissioning", "Baudrate", int(od.bitrate / 1000))
        if od.node_id:
            eds.set("DeviceComissioning", "NodeID", int(od.node_id))

    eds.add_section("Comments")
    i = 0
    for line in od.comments.splitlines():
        i += 1
        eds.set("Comments", f"Line{i}", line)
    eds.set("Comments", "Lines", i)

    eds.add_section("DummyUsage")
    for i in range(1, 8):
        key = f"Dummy{i:04d}"
        eds.set("DummyUsage", key, 1 if (key in od) else 0)

    def mandatory_indices(x):
        return x in {0x1000, 0x1001, 0x1018}

    def manufacturer_indices(x):
        return 0x2000 <= x < 0x6000

    def optional_indices(x):
        return all((
            x > 0x1001,
            not mandatory_indices(x),
            not manufacturer_indices(x),
        ))

    supported_mantatory_indices = list(filter(mandatory_indices, od))
    supported_optional_indices = list(filter(optional_indices, od))
    supported_manufacturer_indices = list(filter(manufacturer_indices, od))

    def add_list(section, lst):
        eds.add_section(section)
        eds.set(section, "SupportedObjects", len(lst))
        for i in range(0, len(lst)):
            eds.set(section, (i + 1), f"0x{lst[i]:04X}")
        for index in lst:
            export_object(od[index], eds)

    add_list("MandatoryObjects", supported_mantatory_indices)
    add_list("OptionalObjects", supported_optional_indices)
    add_list("ManufacturerObjects", supported_manufacturer_indices)

    if not dest:
        import sys
        dest = sys.stdout

    eds.write(dest, False)
