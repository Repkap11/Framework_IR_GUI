import oled_2k_six15_api as Six15_API
import platform
import time
from oled_2k import OLED_2k
from lib_six15_api.six15_api_backend import Six15_API_Backend
from lib_six15_api.six15_api_backend_hid import Six15_API_Backend_HID
from lib_six15_api.six15_api_backend_ftdi import Six15_API_Backend_FTDI
import lib_six15_api.pydfu as PyDfu

if platform.system() != "Windows":
    from lib_six15_api.six15_api_backend_dev_i2c import Six15_API_Backend_Dev_I2C

import usb.core
from typing import Optional, Callable
from lib_six15_api.logger import Logger

hasSleptOnce = False


class OLED_2k_Finder(object):

    def __init__(self) -> None:
        super().__init__()

    def getOLED_2k(self) -> Optional[OLED_2k]:
        backend = self.getOLED_2k_HID()
        if (backend == None):
            return None

        if (not backend.isConnected()):
            # For HID, this can happen if a device is enumerating while disconnecting.
            # This often happens since our disconnect detection happens before enumerating removes our device.
            # For FTDI, finding an FTDI chip doesn't mean we have a connected device
            backend.close()
            return None
        charger = OLED_2k(backend)
        return charger

    def getOLED_2k_HID(self) -> Optional[Six15_API_Backend_HID]:
        hid_device, hid_path = Six15_API_Backend_HID.findDevice(Six15_API.VID_SIX15, Six15_API.PID_594)
        if (hid_device == None or hid_path == None):
            return None

        if platform.system() == 'Windows':
            global hasSleptOnce
            if (not hasSleptOnce):
                Logger.verbose("Delaying first connection on Windows")
                time.sleep(1)  # Windows takes forever at starting the HID driver.
                hasSleptOnce = True

        return Six15_API_Backend_HID(hid_device, hid_path, Six15_API.VID_SIX15, Six15_API.PID_594)
