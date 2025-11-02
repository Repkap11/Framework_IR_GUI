from enum import Enum
import struct
from typing import Dict, Any, Tuple, Optional, Callable
from lib_six15_api.six15_api import *

# See six15_api.h in the FRAMEWORK_IR_display repository
# for the other side of this communication protocol.

VID_SIX15 = 0x2dc4  # 11716
PID_FRAMEWORK_IR = 0x2A  # FRAMEWORK_IR (42)

class Response:

    class Micro_Version(Base_Response):
        @staticmethod
        def format() -> Optional[str]:
            return "<BB56s"

        def __init__(self, resp):
            data = Base_Response.unpack_checked(self.format(), resp, self.__class__.__name__)

            if (data == None):
                raise ValueError(f"Device did not respond to: {self.__class__.__name__} as expected.")

            self.major = data[0]
            self.minor = data[1]
            self.git_version = Base_Response.decodeToStr(data[2])

    class LogPart(Base_Response):
        @staticmethod
        def format() -> Optional[str]:
            return f"<58s"

        def __init__(self, resp):
            data = Base_Response.unpack_checked(self.format(), resp, self.__class__.__name__)
            if (data == None):
                raise ValueError(f"Device did not respond with: {self.__class__.__name__} as expected.")

            self.msg = Base_Response.decodeToStr(data[0])
            self.log_finished = data[0][-1] == 0

    class SerialNumber(Base_Response):
        @staticmethod
        def format() -> Optional[str]:
            return f"<58s"

        def __init__(self, resp):
            data = Base_Response.unpack_checked(self.format(), resp, self.__class__.__name__)
            if (data == None):
                raise ValueError(f"Device did not respond with: {self.__class__.__name__} as expected.")

            self.serial_number = Base_Response.decodeToStr(data[0])

    class Framework_IR_State(Base_Response):
        @staticmethod
        def format() -> Optional[str]:
            return f"<BB"

        def __init__(self, resp):
            data = Base_Response.unpack_checked(self.format(), resp, self.__class__.__name__)

            if (data == None):
                raise ValueError(f"Device did not respond to: {self.__class__.__name__} as expected.")

            self.val1 = data[0]
            self.val2 = data[1]


class CMD:
    class VERSION_MICRO(Base_CMD):
        value = 0x01
        response = Response.Micro_Version

    class REBOOT_TO_FIRMWARE(Base_CMD):
        value = 0x02
        response = None

    class REBOOT_TO_BOOTLOADER(Base_CMD):
        value = 0x03
        response = None

    class READ_LOG(Base_CMD):
        value = 0x04
        response = Response.LogPart

    class READ_STM32_SERIAL_NUMBER(Base_CMD):
        value = 0x05
        response = Response.SerialNumber

    class FRAMEWORK_IR_STATE(Base_CMD):
        value = 0x06
        response = Response.Framework_IR_State



class Framework_IR_Six15_API(Six15_API):

    def __init__(self, backend: Six15_API_Backend, fake: bool, *args):
        super().__init__(backend, fake, *args)

    def queryMicroVersion(self) -> Optional[Response.Micro_Version]:
        return self.sendCommand(CMD.VERSION_MICRO)

    def rebootBootloader(self):
        self.sendCommand(CMD.REBOOT_TO_BOOTLOADER)
        self.close()

    def reboot(self):
        self.sendCommand(CMD.REBOOT_TO_FIRMWARE)
        self.close()

    def queryFramework_IR_State(self) -> Optional[Response.Framework_IR_State]:
        return self.sendCommand(CMD.FRAMEWORK_IR_STATE)

