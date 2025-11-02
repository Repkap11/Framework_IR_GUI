# import ptvsd
from pyclbr import Function
import time
from typing import Callable, Optional
from PySide6.QtCore import QThread, Signal, Slot
from framework_ir_finder import Framework_IR_Finder
from framework_ir import Framework_IR
import usb.core
import thread_debug as ThreadDebug
from lib_six15_api.logger import Logger


class Framework_IR_DeviceListenThread(QThread):
    framework_ir: Optional[Framework_IR]

    def __init__(self, callback) -> None:
        super().__init__()
        self.callback = callback
        self.framework_ir = None
        self.finished.connect(self.deviceFound)

    def run(self):
        ThreadDebug.debug_this_thread()
        finder = Framework_IR_Finder()
        while self.framework_ir == None and not self.isInterruptionRequested():
            # Logger.info("Waiting for device connect")
            try:
                self.framework_ir = finder.getFramework_IR()
                if (self.framework_ir == None):
                    time.sleep(0.5)  # value is in seconds

            except Exception as e:
                if (self.framework_ir == None and not self.isInterruptionRequested()):
                    Logger.error(f"Error in Framework_IRDeviceListenThread: {e}")
                    time.sleep(0.5)
        # Logger.info("Exiting:{}".format(self.isInterruptionRequested()))

    def deviceFound(self):
        self.callback(self.framework_ir)


class Framework_IR_DeviceDisconnectThread(QThread):
    framework_ir: Framework_IR

    def __init__(self, callback: Callable[[Framework_IR], None], framework_ir: Framework_IR):
        super().__init__()
        self.callback = callback
        self.framework_ir = framework_ir
        self.finished.connect(self.deviceDisconnected)

    def run(self):
        ThreadDebug.debug_this_thread()
        while self.framework_ir != None and not self.isInterruptionRequested():
            # Logger.info("Waiting for device disconnect")
            try:
                self.framework_ir = self.framework_ir if self.framework_ir.isConnected() else None
                if (self.framework_ir != None):
                    time.sleep(0.5)  # value is in seconds
            except Exception as e:
                if (self.framework_ir != None and not self.isInterruptionRequested()):
                    Logger.error(f"Error in Framework_IR_DeviceDisconnectThread: {e}")
                    time.sleep(0.5)
        # Logger.info("Exiting:{}".format(self.isInterruptionRequested()))

    def deviceDisconnected(self):
        self.callback(self.framework_ir)