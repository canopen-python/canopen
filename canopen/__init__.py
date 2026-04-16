from canopen.network import Network, NodeScanner
from canopen.node import LocalNode, RemoteNode
from canopen.objectdictionary import (
    ObjectDictionary,
    ObjectDictionaryError,
    export_od,
    import_od,
)
from canopen.profiles.p402 import BaseNode402
from canopen.sdo import SdoAbortedError, SdoCommunicationError

try:
    from canopen._version import version as __version__
except ImportError:
    # package is not installed
    __version__ = "unknown"

__all__ = [
    "Network",
    "NodeScanner",
    "RemoteNode",
    "LocalNode",
    "SdoCommunicationError",
    "SdoAbortedError",
    "import_od",
    "export_od",
    "ObjectDictionary",
    "ObjectDictionaryError",
    "BaseNode402",
]
__pypi_url__ = "https://pypi.org/project/canopen/"

Node = RemoteNode
