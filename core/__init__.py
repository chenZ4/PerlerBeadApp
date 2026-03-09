# core/__init__.py
from .colors import ColorPalette, get_palette, PALETTE_OPTIONS
from .processor import ImageProcessor
from .history_manager import HistoryManager
from .settings_manager import SettingsManager
from .utils import setup_logging, get_resource_path

__all__ = [
    'ColorPalette',
    'get_palette',
    'PALETTE_OPTIONS',
    'ImageProcessor',
    'HistoryManager',
    'SettingsManager',
    'setup_logging',
    'get_resource_path'
]