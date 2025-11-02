import time
from typing import Callable, Optional
from PySide6.QtCore import QThread, Signal, Slot
import thread_debug
from lib_six15_api.logger import Logger
from oled_2k import OLED_2k


class OLED_2k_LogWatcher(QThread):
    oled_2k: Optional[OLED_2k]

    def __init__(self) -> None:
        super().__init__()
        self.oled_2k = None

    def set_OLED_2k(self, oled_2k: OLED_2k):
        self.oled_2k = oled_2k

    def run(self):
        thread_debug.debug_this_thread()

        while (not self.isInterruptionRequested()):
            try:
                local_oled_2k: Optional[OLED_2k] = self.oled_2k
                if (local_oled_2k == None):
                    time.sleep(0.5)
                    continue
                # local_oled_2k.isConnected()

                def lineFunc(line: str):
                    Logger.log_prefixed(line, "  ")
                local_oled_2k.readLog(lineFunc, self.isInterruptionRequested)
                time.sleep(0.5)
            except Exception as e:
                Logger.error(f"Log Reading Err:{e}")
                time.sleep(0.5)
