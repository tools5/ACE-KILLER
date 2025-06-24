"""核心功能模块"""

from core.process_monitor import GameProcessMonitor
from core.system_utils import run_as_admin

__all__ = ["GameProcessMonitor", "run_as_admin"] 