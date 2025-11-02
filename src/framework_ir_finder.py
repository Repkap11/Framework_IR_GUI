import framework_ir_six15_api as Six15_API
import platform
import time
from framework_ir import Framework_IR
from lib_six15_api.six15_api_backend import Six15_API_Backend
from lib_six15_api.six15_api_backend_hid import Six15_API_Backend_HID
import lib_six15_api.pydfu as PyDfu

import usb.core
from typing import Optional, Callable
from lib_six15_api.logger import Logger

hasSleptOnce = False


class Framework_IR_Finder(object):

    def __init__(self) -> None:
        super().__init__()

    def getFramework_IR(self) -> Optional[Framework_IR]:
        backend = self.getFramework_IR_HID()
        if (backend == None):
            return None

        if (not backend.isConnected()):
            # For HID, this can happen if a device is enumerating while disconnecting.
            # This often happens since our disconnect detection happens before enumerating removes our device.
            # For FTDI, finding an FTDI chip doesn't mean we have a connected device
            backend.close()
            return None
        charger = Framework_IR(backend)
        return charger

    def getFramework_IR_HID(self) -> Optional[Six15_API_Backend_HID]:
        hid_device, hid_path = Six15_API_Backend_HID.findDevice(Six15_API.VID_SIX15, Six15_API.PID_FRAMEWORK_IR)
        if (hid_device == None or hid_path == None):
            return None

        if platform.system() == 'Windows':
            global hasSleptOnce
            if (not hasSleptOnce):
                Logger.verbose("Delaying first connection on Windows")
                time.sleep(1)  # Windows takes forever at starting the HID driver.
                hasSleptOnce = True

        return Six15_API_Backend_HID(hid_device, hid_path, Six15_API.VID_SIX15, Six15_API.PID_FRAMEWORK_IR)
