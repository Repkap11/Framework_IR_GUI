import time
from typing import Callable, Optional
from PySide6.QtCore import QThread, Signal, Slot
import thread_debug
from lib_six15_api.logger import Logger
from framework_ir import Framework_IR


class Framework_IR_LogWatcher(QThread):
    framework_ir: Optional[Framework_IR]

    def __init__(self) -> None:
        super().__init__()
        self.framework_ir = None

    def set_Framework_IR(self, framework_ir: Framework_IR):
        self.framework_ir = framework_ir

    def run(self):
        thread_debug.debug_this_thread()

        while (not self.isInterruptionRequested()):
            try:
                local_framework_ir: Optional[Framework_IR] = self.framework_ir
                if (local_framework_ir == None):
                    time.sleep(0.5)
                    continue
                # local_framework_ir.isConnected()

                def lineFunc(line: str):
                    Logger.log_prefixed(line, "  ")
                local_framework_ir.readLog(lineFunc, self.isInterruptionRequested)
                time.sleep(0.5)
            except Exception as e:
                Logger.error(f"Log Reading Err:{e}")
                time.sleep(0.5)
