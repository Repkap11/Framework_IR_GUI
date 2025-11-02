
from typing import Callable, Optional, Dict, Any
from PySide6.QtCore import Signal, QObject
from PySide6.QtGui import QColor
from enum import Enum


class LogLevel(Enum):
    VERBOSE = 0
    INFO = 1
    WARN = 2
    ERROR = 3
    CRITICAL_ERROR = 4


class LoggerImpl(QObject):

    # Single quotes on type for a forward referenced type
    default_logger_impl: Optional['LoggerImpl'] = None
    impl_signal = Signal(LogLevel, str)

    def __init__(self, callback: Callable[[LogLevel, str], None]):
        super().__init__()
        self.impl_signal.connect(callback)

    def makeDefault(self, isDefault: bool):
        LoggerImpl.default_logger_impl = self if isDefault else None

    @staticmethod
    def defaultImpl(level: LogLevel, msg: str):
        prefix = Logger.LOG_LEVEL_TO_PREFIX[level]
        divider = ": " if prefix != "" else ""
        print(f"{prefix}{divider}{msg}")


class Logger(QObject):
    enableVerbose: bool = True

    LOG_LEVEL_TO_PREFIX: Dict[LogLevel, str] = {
        LogLevel.VERBOSE: "",
        LogLevel.INFO: "",
        LogLevel.WARN: "Warn",
        LogLevel.ERROR: "Error",
        LogLevel.CRITICAL_ERROR: "ERROR",
    }

    PREFIX_TO_LOG_LEVEL: Dict[str, LogLevel] = {
        "Warn:": LogLevel.WARN,
        "Warning:": LogLevel.WARN,
        "Error:": LogLevel.ERROR,

    }

    LOG_LEVEL_TO_COLOR: Dict[LogLevel, QColor] = {
        LogLevel.VERBOSE: QColor.fromRgb(0x444444),
        LogLevel.INFO:  QColor('black'),
        LogLevel.WARN: QColor.fromRgb(0x808000),
        LogLevel.ERROR: QColor('red'),
        LogLevel.CRITICAL_ERROR: QColor('red'),
    }


### Static functions for easy access ###

    @staticmethod
    def setEnableVerbose(enabled: bool):
        Logger.enableVerbose = enabled

    @staticmethod
    def log(level: LogLevel, msg: Any):
        msg = str(msg)
        if (level == LogLevel.VERBOSE and not Logger.enableVerbose):
            return
        if (LoggerImpl.default_logger_impl is None):
            LoggerImpl.defaultImpl(level, msg)
        else:
            LoggerImpl.default_logger_impl.impl_signal.emit(level, msg)

    @staticmethod
    def verbose(msg: Any):
        msg = str(msg)
        Logger.log(LogLevel.VERBOSE, msg)

    @staticmethod
    def info(msg: Any):
        msg = str(msg)
        Logger.log(LogLevel.INFO, msg)

    @staticmethod
    def warn(msg: Any):
        msg = str(msg)
        Logger.log(LogLevel.WARN, msg)

    @staticmethod
    def error(msg: Any):
        msg = str(msg)
        Logger.log(LogLevel.ERROR, msg)

    @staticmethod
    def critical_error(msg: Any):
        msg = str(msg)
        Logger.log(LogLevel.CRITICAL_ERROR, msg)

    @staticmethod
    def log_prefixed(msg: Any, extra_prefix: str = ""):
        msg = str(msg)
        for prefix, level in Logger.PREFIX_TO_LOG_LEVEL.items():
            if (msg.startswith(prefix)):
                Logger.log(level, f"{extra_prefix}{msg}")
                return
        Logger.info(f"{extra_prefix}{msg}")
