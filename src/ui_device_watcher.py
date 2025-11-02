# import ptvsd
from pyclbr import Function
import time
from typing import Callable, Optional
from PySide6.QtCore import QThread, Signal, Slot
from oled_2k_finder import OLED_2k_Finder
from oled_2k import OLED_2k
import usb.core
import thread_debug as ThreadDebug
from lib_six15_api.logger import Logger


class OLED_2k_DeviceListenThread(QThread):
    oled_2k: Optional[OLED_2k]

    def __init__(self, callback) -> None:
        super().__init__()
        self.callback = callback
        self.oled_2k = None
        self.finished.connect(self.deviceFound)

    def run(self):
        ThreadDebug.debug_this_thread()
        finder = OLED_2k_Finder()
        while self.oled_2k == None and not self.isInterruptionRequested():
            # Logger.info("Waiting for device connect")
            try:
                self.oled_2k = finder.getOLED_2k()
                if (self.oled_2k == None):
                    time.sleep(0.5)  # value is in seconds

            except Exception as e:
                if (self.oled_2k == None and not self.isInterruptionRequested()):
                    Logger.error(f"Error in OLED_2kDeviceListenThread: {e}")
                    time.sleep(0.5)
        # Logger.info("Exiting:{}".format(self.isInterruptionRequested()))

    def deviceFound(self):
        self.callback(self.oled_2k)


class OLED_2k_DeviceDisconnectThread(QThread):
    oled_2k: OLED_2k

    def __init__(self, callback: Callable[[OLED_2k], None], oled_2k: OLED_2k):
        super().__init__()
        self.callback = callback
        self.oled_2k = oled_2k
        self.finished.connect(self.deviceDisconnected)

    def run(self):
        ThreadDebug.debug_this_thread()
        while self.oled_2k != None and not self.isInterruptionRequested():
            # Logger.info("Waiting for device disconnect")
            try:
                self.oled_2k = self.oled_2k if self.oled_2k.isConnected() else None
                if (self.oled_2k != None):
                    time.sleep(0.5)  # value is in seconds
            except Exception as e:
                if (self.oled_2k != None and not self.isInterruptionRequested()):
                    Logger.error(f"Error in OLED_2k_DeviceDisconnectThread: {e}")
                    time.sleep(0.5)
        # Logger.info("Exiting:{}".format(self.isInterruptionRequested()))

    def deviceDisconnected(self):
        self.callback(self.oled_2k)