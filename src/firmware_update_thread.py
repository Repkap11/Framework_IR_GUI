from typing import Callable, Optional
from PySide6.QtCore import QThread, Signal, Slot
import thread_debug as ThreadDebug
from lib_six15_api.logger import Logger
from framework_ir import Framework_IR
import traceback


class FPGA_FirmwareUpdateThread(QThread):
    status_callback = Signal(bool, int)

    def __init__(self, file_name: str, callback: Callable[[bool, int], None], framework_ir: Framework_IR):
        super().__init__()
        self.file_name = file_name
        self.status_callback.connect(callback)
        self.framework_ir = framework_ir

    def run(self):
        ThreadDebug.debug_this_thread()
        try:
            ret = self.framework_ir.flash_FPGA_FW(self.file_name, self.status_callback.emit)
            if ret == 0:
                Logger.info("FPGA Firmware Update Success")
            else:
                Logger.critical_error("FPGA Firmware Update FAILED")
                self.status_callback.emit(True, 0)

        except Exception as err:
            error_msg = f"FPGA Firmware Update Failed: {err}\ntraceback:  {traceback.format_exc()}"
            Logger.critical_error(error_msg)
            self.status_callback.emit(True, 0)
