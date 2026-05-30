import functools
import logging
import re
import xml.etree.ElementTree as etree
from typing import Any, Callable, Optional, Union, TextIO
from canopen.objectdictionary import (
    ODArray,
    ODRecord,
    ODVariable,
    ObjectDictionary,
    datatypes,
    objectcodes,
)

logger = logging.getLogger(__name__)
autoint = functools.partial(int, base=0)
hex = functools.partial(int, base=16)


def import_xdd(
    xdd: Union[str, TextIO, None],
    node_id: Optional[int],
) -> ObjectDictionary:
    od = ObjectDictionary()

    if xdd is not None:
        root = etree.parse(xdd).getroot()

    if node_id is None:
        device_commissioning_elem = root.find('.//{*}DeviceCommissioning')
        if device_commissioning_elem is not None:
            node_id_attr = device_commissioning_elem.get("nodeID")
            if node_id_attr is None:
                raise ValueError(
                    "Missing required nodeID attribute")
            od.node_id = int(node_id_attr, 0)
        else:
            od.node_id = None
    else:
        od.node_id = node_id

    _add_device_information(od, root)
    _add_object_list(od, root)
    _add_dummy_objects(od, root)
    return od


def _add_device_information(
    od: ObjectDictionary,
    root: etree.Element
):
    device_identity = root.find('.//{*}DeviceIdentity')
    if device_identity is None:
        raise ValueError("Missing 'DeviceIdentity' section in XDD file")
    if device_identity is not None:
        identity_fields: list[tuple[str, str, Callable[[str], Any]]] = [
            ("vendorName", "vendor_name", str),
            ("vendorID", "vendor_number", hex),
            ("productName", "product_name", str),
            ("productID", "product_number", hex),
        ]
        for src_prop, dst_prop, f in identity_fields:
            val = device_identity.find(f'{{*}}{src_prop}')
            if val is not None and val.text:
                setattr(od.device_information, dst_prop, f(val.text))

    general_features = root.find('.//{*}CANopenGeneralFeatures')
    if general_features is None:
        raise ValueError("Missing 'CANopenGeneralFeatures' element")
    if general_features is not None:
        features_fields: list[tuple[str, str, Callable[[str], Any], Any]] = [
            # properties without default value (default=None) are required
            ("granularity", "granularity", autoint, None),
            ("nrOfRxPDO", "nr_of_RXPDO", autoint, "0"),
            ("nrOfTxPDO", "nr_of_TXPDO", autoint, "0"),
            ("bootUpSlave", "simple_boot_up_slave", bool, 0),
        ]
        for src_prop, dst_prop, f, default in features_fields:
            val = general_features.get(src_prop, default)
            if val is None:
                raise ValueError(
                    f"Missing required '{src_prop}' property")
            setattr(od.device_information, dst_prop, f(val))

    baud_rate = root.find('.//{*}PhysicalLayer/{*}baudRate')
    if baud_rate is None:
        raise ValueError("Missing 'PhysicalLayer/baudRate' section")

    for baud in baud_rate:
        try:
            baud_value = baud.get("value")
            if baud_value is not None:
                rate = int(baud_value.replace(' Kbps', ''), 10) * 1000
                od.device_information.allowed_baudrates.add(rate)
        except (ValueError, TypeError):
            pass

    if default_baud := baud_rate.get('defaultValue', '250 Kbps'):
        try:
            od.bitrate = int(default_baud.replace(' Kbps', ''), 10) * 1000
        except (ValueError, TypeError):
            pass


def _add_object_list(
    od: ObjectDictionary,
    root: etree.Element
):
    # Process all CANopen objects in the file
    for obj in root.findall('.//{*}CANopenObjectList/{*}CANopenObject'):
        name = obj.get('name', '')
        index = int(obj.get('index', '0'), 16)
        object_type = int(obj.get('objectType', '0'))
        sub_number = obj.get('subNumber')

        # Simple variable
        if object_type == objectcodes.VAR:
            unique_id_ref = obj.get('uniqueIDRef', None)
            parameters = root.find(
                f'.//{{*}}parameter[@uniqueID="{unique_id_ref}"]')

            var = _build_variable(parameters, od.node_id, name, index)
            _set_parameters_from_xdd_canopen_object(od.node_id, var, obj)
            od.add_object(var)

        # Array
        elif object_type == objectcodes.ARRAY and sub_number:
            array = ODArray(name, index)
            for sub_obj in obj:
                sub_index_attr = sub_obj.get('subIndex')
                if sub_index_attr is None:
                    raise ValueError(
                        "Missing 'subIndex' attribute for"
                        " sub-object in array object"
                        f" 0x{index:04X}")
                sub_index = int(sub_index_attr, 16)
                sub_name = sub_obj.get('name', '')
                sub_unique_id = sub_obj.get('uniqueIDRef', None)
                sub_parameters = root.find(
                    f'.//{{*}}parameter[@uniqueID="{sub_unique_id}"]')

                sub_var = _build_variable(
                    sub_parameters, od.node_id, sub_name, index, sub_index)
                _set_parameters_from_xdd_canopen_object(
                    od.node_id, sub_var, sub_obj)
                array.add_member(sub_var)
            od.add_object(array)

        # Record/Struct
        elif object_type == objectcodes.RECORD and sub_number:
            record = ODRecord(name, index)
            for sub_obj in obj:
                sub_index_attr = sub_obj.get('subIndex')
                if sub_index_attr is None:
                    raise ValueError(
                        "Missing 'subIndex' attribute for"
                        " sub-object in record object"
                        f" 0x{index:04X}")
                sub_index = int(sub_index_attr, 16)
                sub_name = sub_obj.get('name', '')
                sub_unique_id = sub_obj.get('uniqueIDRef', None)
                sub_parameters = root.find(
                    f'.//{{*}}parameter[@uniqueID="{sub_unique_id}"]')
                sub_var = _build_variable(
                    sub_parameters, od.node_id, sub_name, index, sub_index)
                _set_parameters_from_xdd_canopen_object(
                    od.node_id, sub_var, sub_obj)
                record.add_member(sub_var)
            od.add_object(record)


def _add_dummy_objects(
    od: ObjectDictionary,
    root: etree.Element
):
    dummy_section = root.find('.//{*}ApplicationLayers/{*}dummyUsage')
    if dummy_section is None:
        return

    for dummy in dummy_section:
        entry = dummy.get('entry')
        if entry is None:
            raise ValueError(
                "Missing 'entry' attribute for dummy object")
        p = entry.split('=')
        key = p[0]
        value = int(p[1], 10)
        index = int(key.replace('Dummy', ''), 10)
        if value == 1:
            var = ODVariable(key, index, 0)
            var.data_type = index
            var.access_type = "const"
            od.add_object(var)


def _set_parameters_from_xdd_canopen_object(
    node_id: Optional[int],
    dst: ODVariable,
    src: etree.Element
):
    # PDO mapping of the object, optional, string
    # Valid values:
    # * no - not mappable
    # * default - mapped by default
    # * optional - optionally mapped
    # * TPDO - may be mapped into TPDO only
    # * RPDO - may be mapped into RPDO only
    pdo_mapping_attr = src.get('PDOmapping')
    if pdo_mapping_attr is not None:
        pdo_mapping = pdo_mapping_attr.lower()
        dst.pdo_mappable = pdo_mapping != 'no'

    # Name of the object, optional, string
    if var_name := src.get('name', None):
        dst.name = var_name

    # CANopen data type (two hex digits), optional
    # data_type matches canopen library, no conversion needed
    var_data_type_attr = src.get('dataType', None)
    if var_data_type_attr is not None:
        dst.data_type = int(var_data_type_attr, 16)

    # Access type of the object; valid values, optional, string
    # * const - read access only; the value is not changing
    # * ro - read access only
    # * wo - write access only
    # * rw - both read and write access
    # strings match with access_type in canopen library, no conversion needed
    access_type_attr = src.get('accessType', None)
    if access_type_attr is not None:
        dst.access_type = access_type_attr

    if dst.data_type in datatypes.INTEGER_TYPES:
        # Low limit of the parameter value, optional, string
        min_value_attr = src.get('lowLimit', None)
        if min_value_attr is not None:
            dst.min = _convert_integer(node_id, dst.data_type, min_value_attr)

        # High limit of the parameter value, optional, string
        max_value_attr = src.get('highLimit', None)
        if max_value_attr is not None:
            dst.max = _convert_integer(node_id, dst.data_type, max_value_attr)

        # Default value of the object, optional, string
        default_value_attr = src.get('defaultValue')
        if default_value_attr is not None:
            if '$NODEID' in default_value_attr:
                dst.relative = True
            dst.default = _convert_integer(
                node_id, dst.data_type, default_value_attr)


def _build_variable(
    par_tree: Optional[etree.Element],
    node_id: Optional[int],
    name: str,
    index: int,
    subindex: int = 0
) -> ODVariable:
    var = ODVariable(name, index, subindex)
    # Set default parameters
    var.access_type = 'ro'
    if par_tree is None:
        return var

    var.description = par_tree.get('description', '')

    # Extract data type
    data_types = {
        'BOOL': datatypes.BOOLEAN,
        'SINT': datatypes.INTEGER8,
        'INT': datatypes.INTEGER16,
        'DINT': datatypes.INTEGER32,
        'LINT': datatypes.INTEGER64,
        'USINT': datatypes.UNSIGNED8,
        'UINT': datatypes.UNSIGNED16,
        'UDINT': datatypes.UNSIGNED32,
        'ULINT': datatypes.UNSIGNED32,
        'REAL': datatypes.REAL32,
        'LREAL': datatypes.REAL64,
        'STRING': datatypes.VISIBLE_STRING,
        'BITSTRING': datatypes.DOMAIN,
        'WSTRING': datatypes.UNICODE_STRING
    }

    for k, v in data_types.items():
        if par_tree.find(f'{{*}}{k}') is not None:
            var.data_type = v

    if var.data_type is None:
        raise ValueError(
            f"Unsupported or missing data type for variable "
            f"'{name}' (index 0x{index:04X})")

    # Extract access type
    access_type_str = par_tree.get('access', 'read')
    # Defines which operations are valid for the parameter:
    # * const - read access only; the value is not changing
    # * read - read access only (default value)
    # * write - write access only
    # * readWrite - both read and write access
    # * readWriteInput - both read and write access, but represents
    #       process input data
    # * readWriteOutput - both read and write access, but represents
    #       process output data
    # * noAccess - access denied
    access_types = {
        'const': 'const',
        'read': 'ro',
        'write': 'wo',
        'readWrite': 'rw',
        'readWriteInput': 'rw',
        'readWriteOutput': 'rw',
        'noAccess': 'const',
    }
    var.access_type = access_types.get(access_type_str, 'ro')

    if var.data_type in datatypes.INTEGER_TYPES:
        # Extract default value
        default_value_elem = par_tree.find('{*}defaultValue')
        if default_value_elem is not None:
            default_value = default_value_elem.get('value')
            if default_value is not None:
                if '$NODEID' in default_value:
                    var.relative = True
                var.default = _convert_integer(
                    node_id, var.data_type, default_value)

        # Extract allowed values range
        min_value_elem = par_tree.find('{*}allowedValues/{*}range/{*}minValue')
        if min_value_elem is not None:
            var.min = _convert_integer(
                node_id, var.data_type, min_value_elem.get('value'))

        max_value_elem = par_tree.find('{*}allowedValues/{*}range/{*}maxValue')
        if max_value_elem is not None:
            var.max = _convert_integer(
                node_id, var.data_type, max_value_elem.get('value'))
    return var


def _calc_bit_length(
    data_type: int
) -> int:
    if data_type == datatypes.INTEGER8:
        return 8
    elif data_type == datatypes.INTEGER16:
        return 16
    elif data_type == datatypes.INTEGER32:
        return 32
    elif data_type == datatypes.INTEGER64:
        return 64
    else:
        raise ValueError(
            f"Invalid data_type '{data_type}', expecting a signed integer "
            "data_type.")


def _signed_int_from_hex(
    hex_str: str,
    bit_length: int
) -> int:
    number = int(hex_str, 0)
    max_value = (1 << (bit_length - 1)) - 1

    if number > max_value:
        return number - (1 << bit_length)
    else:
        return number


def _convert_integer(
    node_id: Optional[int],
    var_type: int,
    value: Optional[str]
) -> Optional[int]:
    if value is None:
        return None
    # COB-ID can contain '$NODEID+' so replace this with node_id
    # before converting
    value = value.replace(" ", "").upper()
    if '$NODEID' in value:
        if node_id is None:
            logger.warn(
                "Cannot convert value with $NODEID, skipping conversion")
            return None
        else:
            return int(re.sub(r'\+?\$NODEID\+?', '', value), 0) + node_id
    else:
        if var_type in datatypes.SIGNED_TYPES:
            return _signed_int_from_hex(value, _calc_bit_length(var_type))
        else:
            return int(value, 0)


def _convert_variable(
    node_id: Optional[int],
    var_type: int,
    value: Optional[str]
) -> Optional[Union[bytes, str, float, int]]:
    if value is None:
        return None
    if var_type in (datatypes.OCTET_STRING, datatypes.DOMAIN):
        return bytes.fromhex(value)
    elif var_type in (datatypes.VISIBLE_STRING, datatypes.UNICODE_STRING):
        return str(value)
    elif var_type in datatypes.FLOAT_TYPES:
        return float(value)
    elif var_type in datatypes.INTEGER_TYPES:
        return _convert_integer(node_id, var_type, value)
    else:
        raise ValueError(
            f"Invalid data_type '{var_type}'")
