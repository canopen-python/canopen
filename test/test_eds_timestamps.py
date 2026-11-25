"""File timestamps must preserve the clock's minutes, not the month."""
from configparser import RawConfigParser
from datetime import datetime
from io import StringIO
from unittest.mock import patch

import pytest

from canopen.objectdictionary import ObjectDictionary
from canopen.objectdictionary.eds import export_dcf, export_eds


@pytest.mark.parametrize('exporter', [export_eds, export_dcf])
@pytest.mark.parametrize('hour,minute,expected', [(15, 45, '03:45PM'), (0, 7, '12:07AM')])
def test_generated_file_times(exporter, hour, minute, expected):
    class Clock(datetime):
        @classmethod
        def utcnow(cls):
            return cls(2026, 11, 18, hour, minute)

    output = StringIO()
    with patch('datetime.datetime', Clock):
        # Give each export its own metadata dictionary.
        exporter(ObjectDictionary(), output, {})
    result = RawConfigParser()
    result.read_string(output.getvalue())
    assert result['FileInfo']['CreationTime'] == expected
    assert result['FileInfo']['ModificationTime'] == expected
    assert result['FileInfo']['CreationDate'] == '11-18-2026'
    assert result['FileInfo']['ModificationDate'] == '11-18-2026'


@pytest.mark.parametrize('exporter', [export_eds, export_dcf])
def test_explicit_file_times_are_preserved(exporter):
    output = StringIO()
    exporter(ObjectDictionary(), output, {
        'CreationTime': '06:29AM', 'ModificationTime': '08:53PM',
    })
    result = RawConfigParser()
    result.read_string(output.getvalue())
    assert result['FileInfo']['CreationTime'] == '06:29AM'
    assert result['FileInfo']['ModificationTime'] == '08:53PM'
