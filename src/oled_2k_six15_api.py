from enum import Enum
import struct
from typing import Dict, Any, Tuple, Optional, Callable
from lib_six15_api.six15_api import *

# See six15_api.h in the 594_display repository
# for the other side of this communication protocol.

VID_SIX15 = 0x2dc4  # 11716
PID_594 = 0x0252  # 594


class I2C_Info:
    def __init__(self, id, prettyName):
        self.id = id
        self.prettyName = prettyName


I2C_DEV_TO_BYTE: Dict[str, I2C_Info] = {
    "oled_display": I2C_Info(0, "OLED (Display)"),
    "oled_eeprom": I2C_Info(1, "OLED (EEPROM)"),
    "oled_io": I2C_Info(2, "OLED (IO)"),
    "fpga": I2C_Info(3, "FPGA"),
    "hdmi_io": I2C_Info(4, "HDMI (IO)"),
    "hdmi_hdmi": I2C_Info(5, "HDMI (HDMI)"),
    "hdmi_info_frame": I2C_Info(6, "HDMI (Info Frame)"),
}


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

    class OLED_DisplayState(Base_Response):
        @staticmethod
        def format() -> Optional[str]:
            return f"<BI"

        def __init__(self, resp):
            data = Base_Response.unpack_checked(self.format(), resp, self.__class__.__name__)
            if (data == None):
                raise ValueError(f"Device did not respond with: {self.__class__.__name__} as expected.")

            self.status = data[0]
            self.brightness = "WIP"
            self.temperature_value = data[1]
            self.serial_number = "WIP"

    class I2C_CMD(Base_Response):
        @staticmethod
        def format() -> Optional[str]:
            return "<BH"

        def __init__(self, resp):
            data = Base_Response.unpack_checked(self.format(), resp, self.__class__.__name__)

            if (data == None):
                raise ValueError(f"Device did not respond to: {self.__class__.__name__} as expected.")

            self.devAddr = data[0]
            self.value = data[1]

    class Adjust_Brightness(Base_Response):
        @staticmethod
        def format() -> Optional[str]:
            return "<B"

        def __init__(self, resp):
            data = Base_Response.unpack_checked(self.format(), resp, self.__class__.__name__)

            if (data == None):
                raise ValueError(f"Device did not respond to: {self.__class__.__name__} as expected.")

            self.brightness = data[0]

    class HDMI_State(Base_Response):
        @staticmethod
        def format() -> Optional[str]:
            return "<BHHffHH"

        def __init__(self, resp):
            data = Base_Response.unpack_checked(self.format(), resp, self.__class__.__name__)

            if (data == None):
                raise ValueError(f"Device did not respond to: {self.__class__.__name__} as expected.")

            self.input_source_locked = data[0]
            self.active_width = data[1]
            self.active_height = data[2]
            self.fps = data[3]
            self.clock_freq = data[4]
            self.total_width = data[5]
            self.total_height = data[6]

    class EDID_State(Base_Response):
        @staticmethod
        def format() -> Optional[str]:
            return f"<HBB"

        def __init__(self, resp):
            data = Base_Response.unpack_checked(self.format(), resp, self.__class__.__name__)

            if (data == None):
                raise ValueError(f"Device did not respond to: {self.__class__.__name__} as expected.")

            self.num_start_conditions = data[0]
            self.e_edid_page_addr_accessed = data[1]
            self.error_flag = data[2]

    class FPGA_Version(Base_Response):
        @staticmethod
        def format() -> Optional[str]:
            return "<16s32s"

        def __init__(self, resp):
            data = Base_Response.unpack_checked(self.format(), resp, self.__class__.__name__)
            if (data == None):
                # Try older versions of the structure
                data = Base_Response.unpack_checked("<16s", resp, self.__class__.__name__)

            if (data == None):
                raise ValueError(f"Device did not respond to: {self.__class__.__name__} as expected.")

            # The version response is not that well defined.
            # It's always 16 chars maximum, but the remaining characters could be null or space.
            # This logic may need to be re-worked to fit whatever the hardware actually does.
            version_fpga_str = Base_Response.decodeToStr(data[0]).strip(' ')
            version_fpga_str = None if version_fpga_str == '' else version_fpga_str
            self.version = version_fpga_str

            if (len(data) >= 2):
                git_version_fpga_str = Base_Response.decodeToStr(data[1]).strip(' ')
                git_version_fpga_str = None if git_version_fpga_str == '' else git_version_fpga_str
                self.git_version = git_version_fpga_str
            else:
                self.git_version = None


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

    class VERSION_DISPLAY_FPGA(Base_CMD):
        value = 0x04
        response = Response.FPGA_Version

    class FLASH_FPGA_START(Base_CMD):
        value = 0x05
        response = Response_Default

    class FLASH_FPGA_PROGRAM(Base_CMD):
        value = 0x06
        response = Response_Default

    class FLASH_FPGA_END(Base_CMD):
        value = 0x07
        response = Response_Default

    class ADJUST_BRIGHTNESS(Base_CMD):
        value = 0x08
        response = Response.Adjust_Brightness

    class I2C(Base_CMD):
        value = 0x0D
        response = Response.I2C_CMD

    class HDMI_STATE(Base_CMD):
        value = 0x0E
        response = Response.HDMI_State

    class OLED_DISPLAY_STATE(Base_CMD):
        value = 0x11
        response = Response.OLED_DisplayState

    class EDID_STATE(Base_CMD):
        value = 0x12
        response = Response.EDID_State

    class READ_STM32_SERIAL_NUMBER(Base_CMD):
        value = 0x1A
        response = Response.SerialNumber

    class READ_LOG(Base_CMD):
        value = 0x1D
        response = Response.LogPart

    class DEBUG_ACTION(Base_CMD):
        value = 0x1E
        response = Response_Default


class OLED_2k_Six15_API(Six15_API):

    def __init__(self, backend: Six15_API_Backend, fake: bool, *args):
        super().__init__(backend, fake, *args)

    def queryMicroVersion(self) -> Optional[Response.Micro_Version]:
        return self.sendCommand(CMD.VERSION_MICRO)

    def queryFPGA_Version(self) -> Optional[Response.FPGA_Version]:
        return self.sendCommand(CMD.VERSION_DISPLAY_FPGA)

    def rebootBootloader(self):
        self.sendCommand(CMD.REBOOT_TO_BOOTLOADER)
        self.close()

    def reboot(self):
        self.sendCommand(CMD.REBOOT_TO_FIRMWARE)
        self.close()

    def sendI2C_CMD(self, write:bool, which_i2c_device:I2C_Info, reg:int, value:int) -> Response.I2C_CMD:
        data = struct.pack("<BBHH", write, which_i2c_device.id, reg, value)
        return self.sendCommand(CMD.I2C, data)

    def sendAdjustBrightness(self, brightness_increment: int) -> Optional[Response.Adjust_Brightness]:
        payload = struct.pack("<b", brightness_increment)
        return self.sendCommand(CMD.ADJUST_BRIGHTNESS, payload)

    def queryHDMI_State(self) -> Optional[Response.HDMI_State]:
        return self.sendCommand(CMD.HDMI_STATE)

    def queryEDID_State(self) -> Optional[Response.EDID_State]:
        return self.sendCommand(CMD.EDID_STATE)
