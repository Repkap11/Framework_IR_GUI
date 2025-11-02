from typing import Optional, Callable
import usb
import time
import lib_six15_api.pydfu as PyDfu
from lib_six15_api.six15_api import Six15_API
from lib_six15_api.logger import Logger
from PySide6.QtCore import QThread

def find_STM32_Bootloader() -> Optional[usb.core.Device]:
    devices = PyDfu.get_dfu_devices()
    if (devices is None or len(devices) != 1):
        return None
    return devices[0]


class BootloaderListenThread(QThread):

    def __init__(self, callback) -> None:
        super().__init__()
        self.callback = callback
        self.oled_2k_bootloader = None
        self.finished.connect(self.deviceFound)

    def run(self):
        while self.oled_2k_bootloader == None and not self.isInterruptionRequested():
            # Logger.info("Waiting for device connect")
            try:
                self.oled_2k_bootloader = find_STM32_Bootloader()
                if (self.oled_2k_bootloader == None):
                    time.sleep(0.5)  # value is in seconds

            except Exception as e:
                if (self.oled_2k_bootloader == None and not self.isInterruptionRequested()):
                    Logger.error(f"Error in BootloaderListenThread: {e}")
                    time.sleep(0.5)
        # Logger.info("Exiting:{}".format(self.isInterruptionRequested()))

    def deviceFound(self):
        self.callback(self.oled_2k_bootloader)


class BootloaderDisconnectThread(QThread):

    def __init__(self, callback: Callable[[Six15_API], None]):
        super().__init__()
        self.callback = callback
        self.finished.connect(self.deviceDisconnected)

    def isConnected(self) -> bool:
        return find_STM32_Bootloader() != None

    def run(self):
        while not self.isInterruptionRequested():
            # Logger.info("Waiting for device disconnect")
            try:
                if (self.isConnected()):
                    time.sleep(0.5)  # value is in seconds
                else:
                    break
            except Exception as e:
                if (not self.isInterruptionRequested()):
                    Logger.error("Error in BootloaderDisconnectThread")
                    time.sleep(0.5)
        # Logger.info("Exiting:{}".format(self.isInterruptionRequested()))

    def deviceDisconnected(self):
        self.callback(None)
