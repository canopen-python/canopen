import logging

import re
import xml.etree.ElementTree as etree
from configparser import NoOptionError
from typing import TYPE_CHECKING

from canopen import objectdictionary
from canopen.objectdictionary import ObjectDictionary
from canopen.utils import signed_int_from_hex, calc_bit_length

if TYPE_CHECKING:
    import canopen.network

logger = logging.getLogger(__name__)

# Object type. Don't confuse with Data type
VAR = 7
ARR = 8
RECORD = 9


def import_xdd(xdd, node_id):
    od = ObjectDictionary()
    if etree.iselement(xdd):
        root = xdd
    else:
        root = etree.parse(xdd).getroot()

    if node_id is None:
        device_commissioning = root.find('.//{*}DeviceCommissioning')
        if device_commissioning is not None:
            if node_id := device_commissioning.get('nodeID', None):
                try:
                    od.node_id = int(node_id, 0)
                except (ValueError, TypeError):
                    pass
    else:
        od.node_id = node_id

    _add_device_information_to_od(od, root)
    _add_object_list_to_od(od, root)
    _add_dummy_objects_to_od(od, root)


    return od

def _add_device_information_to_od(od, root):
    device_identity = root.find('.//{*}DeviceIdentity')
    if device_identity is not None:
        for src_prop, dst_prop, f in [
            ("vendorName", "vendor_name", lambda val: str(val)),
            ("vendorID", "vendor_number", lambda val: int(val, 0)),
            ("productName", "product_name", lambda val: str(val)),
            ("productID", "product_number", lambda val: int(val, 0)),
        ]:
            val = device_identity.find(f'{{*}}{src_prop}')
            if val is not None and val.text:
                try:
                    setattr(od.device_information, dst_prop, f(val.text))
                except NoOptionError:
                    pass

    general_features = root.find('.//{*}CANopenGeneralFeatures')
    if general_features is not None:
        for src_prop, dst_prop, f in [
            ("granularity", "granularity", lambda val: int(val, 0)),
            ("nrOfRxPDO", "nr_of_RXPDO", lambda val: int(val, 0)),
            ("nrOfTxPDO", "nr_of_TXPDO", lambda val: int(val, 0)),
            ("bootUpSlave", "simple_boot_up_slave", lambda val: bool(val)),
        ]:
            if val := general_features.get(src_prop, None):
                try:
                    setattr(od.device_information, dst_prop, f(val))
                except NoOptionError:
                    pass

    baud_rate = root.find('.//{*}PhysicalLayer/{*}baudRate')
    for baud in baud_rate:
        try:
            rate = int(baud.get("value").replace(' Kbps', ''), 10) * 1000
            od.device_information.allowed_baudrates.add(rate)
        except (ValueError, TypeError):
            pass

    if default_baud := baud_rate.get('defaultValue', None):
        try:
            od.bitrate = int(default_baud.replace(' Kbps', ''), 10) * 1000
        except (ValueError, TypeError):
            pass

def _add_object_list_to_od(od: ObjectDictionary, root):
    # Process all CANopen objects in the file
    for obj in root.findall('.//{*}CANopenObjectList/{*}CANopenObject'):
        name = obj.get('name', '')
        index = int(obj.get('index', '0'), 16)
        object_type = int(obj.get('objectType', '0'))
        sub_number = obj.get('subNumber')

        # Simple variable
        if object_type == VAR:
            unique_id_ref = obj.get('uniqueIDRef', None)
            parameters = root.find(f'.//{{*}}parameter[@uniqueID="{unique_id_ref}"]')

            var = _build_variable(parameters, od.node_id, name, index)
            _set_parameters_from_xdd_canopen_object(od.node_id, var, obj)
            od.add_object(var)

        # Array
        elif object_type == ARR and sub_number:
            array = objectdictionary.ODArray(name, index)
            for sub_obj in obj:
                sub_name = sub_obj.get('name', '')
                sub_index = int(sub_obj.get('subIndex'), 16)
                sub_unique_id = sub_obj.get('uniqueIDRef', None)
                sub_parameters = root.find(f'.//{{*}}parameter[@uniqueID="{sub_unique_id}"]')

                sub_var = _build_variable(sub_parameters, od.node_id, sub_name, index, sub_index)
                _set_parameters_from_xdd_canopen_object(od.node_id, sub_var, sub_obj)
                array.add_member(sub_var)
            od.add_object(array)

        # Record/Struct
        elif object_type == RECORD and sub_number:
            record = objectdictionary.ODRecord(name, index)
            for sub_obj in obj:
                sub_name = sub_obj.get('name', '')
                sub_index = int(sub_obj.get('subIndex'))
                sub_unique_id = sub_obj.get('uniqueIDRef', None)
                sub_parameters = root.find(f'.//{{*}}parameter[@uniqueID="{sub_unique_id}"]')
                sub_var = _build_variable(sub_parameters, od.node_id, sub_name, index, sub_index)
                _set_parameters_from_xdd_canopen_object(od.node_id, sub_var, sub_obj)
                record.add_member(sub_var)
            od.add_object(record)

def _add_dummy_objects_to_od(od: ObjectDictionary, root):
    dummy_section = root.find('.//{*}ApplicationLayers/{*}dummyUsage')
    for dummy in dummy_section:
        p = dummy.get('entry').split('=')
        key = p[0]
        value = int(p[1], 10)
        index = int(key.replace('Dummy', ''), 10)
        if value == 1:
            var = objectdictionary.ODVariable(key, index, 0)
            var.data_type = index
            var.access_type = "const"
            od.add_object(var)

def _set_parameters_from_xdd_canopen_object(node_id, dst, src):
    # PDO mapping of the object, optional, string
    # Valid values:
    # * no – not mappable
    # * default – mapped by default
    # * optional – optionally mapped
    # * TPDO – may be mapped into TPDO only
    # * RPDO – may be mapped into RPDO only
    pdo_mapping = src.get('PDOmapping', 'no')
    dst.pdo_mappable = pdo_mapping != 'no'

    # Name of the object, optional, string
    if var_name := src.get('name', None):
        dst.name = var_name

    # CANopen data type (two hex digits), optional
    # data_type matches canopen library, no conversion needed
    if var_data_type := src.get('dataType', None):
        try:
            dst.data_type = int(var_data_type, 16)
        except (ValueError, TypeError):
            pass

    # Access type of the object; valid values, optional, string
    # * const – read access only; the value is not changing
    # * ro – read access only
    # * wo – write access only
    # * rw – both read and write access
    # strings match with access_type in canopen library, no conversion needed
    if access_type := src.get('accessType', None):
        dst.access_type = access_type

    # Low limit of the parameter value, optional, string
    if min_value := src.get('lowLimit', None):
        try:
            dst.min = _convert_variable(node_id, dst.data_type, min_value)
        except (ValueError, TypeError):
            pass

    # High limit of the parameter value, optional, string
    if max_value := src.get('highLimit', None):
        try:
            dst.max = _convert_variable(node_id, dst.data_type, max_value)
        except (ValueError, TypeError):
            pass

    # Default value of the object, optional, string
    if default_value := src.get('defaultValue', None):
        try:
            dst.default_raw = default_value
            if '$NODEID' in dst.default_raw:
                dst.relative = True
            dst.default = _convert_variable(node_id, dst.data_type, dst.default_raw)
        except (ValueError, TypeError):
            pass

def _build_variable(par_tree, node_id, name, index, subindex=0):
    var = objectdictionary.ODVariable(name, index, subindex)
    # Set default parameters
    var.default_raw = None
    var.access_type = 'ro'
    if par_tree is None:
        return

    var.description = par_tree.get('description', '')

    # Extract data type
    data_types = {
        'BOOL': objectdictionary.BOOLEAN,
        'SINT': objectdictionary.INTEGER8,
        'INT': objectdictionary.INTEGER16,
        'DINT': objectdictionary.INTEGER32,
        'LINT': objectdictionary.INTEGER64,
        'USINT': objectdictionary.UNSIGNED8,
        'UINT': objectdictionary.UNSIGNED16,
        'UDINT': objectdictionary.UNSIGNED32,
        'ULINT': objectdictionary.UNSIGNED32,
        'REAL': objectdictionary.REAL32,
        'LREAL': objectdictionary.REAL64,
        'STRING': objectdictionary.VISIBLE_STRING,
        'BITSTRING': objectdictionary.DOMAIN,
        'WSTRING': objectdictionary.UNICODE_STRING
    }

    #print(f'par_tree={etree.tostring(par_tree, encoding="unicode")}')
    for k, v in data_types.items():
        if par_tree.find(f'{{*}}{k}') is not None:
            var.data_type = v

    # Extract access type
    if access_type_str := par_tree.get('access', None):
        # Defines which operations are valid for the parameter:
        # * const – read access only; the value is not changing
        # * read – read access only (default value)
        # * write – write access only
        # * readWrite – both read and write access
        # * readWriteInput – both read and write access, but represents process input data
        # * readWriteOutput – both read and write access, but represents process output data
        # * noAccess – access denied
        access_types = {
            'const': 'const',
            'read': 'ro',
            'write': 'wo',
            'readWrite': 'rw',
            'readWriteInput': 'rw',
            'readWriteOutput': 'rw',
            'noAccess': 'const',
        }
        var.access_type = access_types.get(access_type_str)

    # Extract default value
    default_value = par_tree.find('{*}defaultValue')
    if default_value is not None:
        try:
            var.default_raw = default_value.get('value')
            if '$NODEID' in var.default_raw:
                var.relative = True
            var.default = _convert_variable(node_id, var.data_type, var.default_raw)
        except (ValueError, TypeError):
            pass

    # Extract allowed values range
    min_value = par_tree.find('{*}allowedValues/{*}range/{*}minValue')
    if min_value is not None:
        try:
            var.min = _convert_variable(node_id, var.data_type, min_value.get('value'))
        except (ValueError, TypeError):
            pass

    max_value = par_tree.find('{*}allowedValues/{*}range/{*}maxValue')
    if max_value is not None:
        try:
            var.max = _convert_variable(node_id, var.data_type, max_value.get('value'))
        except (ValueError, TypeError):
            pass
    return var

def _convert_variable(node_id, var_type, value):
    if var_type in (objectdictionary.OCTET_STRING, objectdictionary.DOMAIN):
        return bytes.fromhex(value)
    elif var_type in (objectdictionary.VISIBLE_STRING, objectdictionary.UNICODE_STRING):
        return value
    elif var_type in objectdictionary.FLOAT_TYPES:
        return float(value)
    else:
        # COB-ID can contain '$NODEID+' so replace this with node_id before converting
        value = value.replace(" ", "").upper()
        if '$NODEID' in value:
            if node_id is None:
                logger.warn("Cannot convert value with $NODEID, skipping conversion")
                return None
            else:
                return int(re.sub(r'\+?\$NODEID\+?', '', value), 0) + node_id
        else:
            if var_type in objectdictionary.SIGNED_TYPES:
                return signed_int_from_hex(value, calc_bit_length(var_type))
            else:
                return int(value, 0)
