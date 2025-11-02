from typing import Callable, Optional
from PySide6.QtCore import QThread, Signal, Slot
import thread_debug as ThreadDebug
from lib_six15_api.logger import Logger
from oled_2k import OLED_2k
import traceback


class FPGA_FirmwareUpdateThread(QThread):
    status_callback = Signal(bool, int)

    def __init__(self, file_name: str, callback: Callable[[bool, int], None], oled_2k: OLED_2k):
        super().__init__()
        self.file_name = file_name
        self.status_callback.connect(callback)
        self.oled_2k = oled_2k

    def run(self):
        ThreadDebug.debug_this_thread()
        try:
            ret = self.oled_2k.flash_FPGA_FW(self.file_name, self.status_callback.emit)
            if ret == 0:
                Logger.info("FPGA Firmware Update Success")
            else:
                Logger.critical_error("FPGA Firmware Update FAILED")
                self.status_callback.emit(True, 0)

        except Exception as err:
            error_msg = f"FPGA Firmware Update Failed: {err}\ntraceback:  {traceback.format_exc()}"
            Logger.critical_error(error_msg)
            self.status_callback.emit(True, 0)
