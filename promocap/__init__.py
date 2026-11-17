"""promo-capture: script app footage for promo videos on Android, the iOS Simulator and macOS windows."""
from .android import Device, Node, parse_ui
from .ios import Simulator
from .take import Take, validate

__version__ = '0.1.0'
