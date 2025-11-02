#!/usr/bin/env python3
import os
from typing import Callable, Optional

# os.environ['PYUSB_DEBUG'] = 'debug' # uncomment for verbose pyusb output
import sys
import platform
import struct
import argparse
import traceback
import time
from generated import app_version as AppVersion
import oled_2k_six15_api as Six15_API
from lib_six15_api.six15_api_backend import Six15_API_Backend
from oled_2k_six15_api import OLED_2k_Six15_API
from lib_six15_api.logger import Logger
import lib_six15_api.lattice_fpga_updater as Lattice_FPGA_Updater
import lib_six15_api.stm32_firmware_updater as STM32_Firmware_Update

NUM_CHARGER_BAYS = 4


class OLED_2k(OLED_2k_Six15_API):

    REBOOT_TO_BOOTLOADER_DELAY_SECONDS = 2
    REBOOT_TO_DISCONNECT_DELAY_SECONDS = 0.5

    def __init__(self, backend: Six15_API_Backend, *args) -> None:
        super().__init__(backend, False, *args)
        self.backend = backend

    def flash_FPGA_FW(self, file_name: str, callback: Optional[Callable[[bool, int], None]] = None):
        return Lattice_FPGA_Updater.flash_FPGA_FW(self, file_name, Six15_API.CMD.FLASH_FPGA_START, Six15_API.CMD.FLASH_FPGA_PROGRAM, Six15_API.CMD.FLASH_FPGA_END, callback)

    def readLog(self, lineFunc: Callable[[str], None], abortFunc: Callable[[None], bool]):
        keepReading = True
        partial_line = ""
        while keepReading and not abortFunc():
            log_part: Optional[Six15_API.Response.LogPart] = self.sendCommand(Six15_API.CMD.READ_LOG, None, 100)
            if (log_part == None):
                break
            lines = log_part.msg.splitlines(keepends=True)
            if (len(lines) != 0):
                lines[0] = partial_line + lines[0]
                partial_line = ""
                lastHasEnd = lines[-1].endswith("\n")
                if (not lastHasEnd):
                    partial_line = lines[-1]
                    del lines[-1]
                for line in lines:
                    line = line.strip("\r\n")
                    # print(f"line:{line}")
                    lineFunc(line)
            keepReading = not log_part.log_finished
            # print(f"Log Part:{log_part.msg}")
        if (partial_line != ""):
            lineFunc("<Warning, log ended with partial line>")

    def queryOLED_DisplayState(self) -> Optional[Six15_API.Response.OLED_DisplayState]:
        return self.sendCommand(Six15_API.CMD.OLED_DISPLAY_STATE)

    def sendDebugAction(self, index: int) -> int:
        return self.sendSimpleCMD(Six15_API.CMD.DEBUG_ACTION, struct.pack("<B", index))

    def parseForArgs():
        parser = argparse.ArgumentParser(description='OLED 2k CLI')
        sub_parsers = parser.add_subparsers(dest="sub_command", required=True)

        # Version
        sub_parsers.add_parser("version", help="Print GUI/CLI Version")

        # Reboot
        sub_parsers.add_parser("reboot", help="Reboot the system")

        # Reboot Bootloader
        sub_parsers.add_parser("reboot_bootloader",  help="Reboot the system and jump to the bootloader")

        # Flash STM32 FW
        flash_stm32_fw_parser = sub_parsers.add_parser("flash_stm32_fw", help="Flash and Verify the STM32 microcontroller")
        flash_stm32_fw_parser.add_argument("file_name")

        # Verify STM32 FW
        verify_stm32_fw_parser = sub_parsers.add_parser("verify_stm32_fw", help="Verify the firmware of the STM32 microcontroller")
        verify_stm32_fw_parser.add_argument("file_name")

        # Flash FPGA FW
        flash_fpga_fw_parser = sub_parsers.add_parser("flash_fpga_fw", help="Flash and Verify the FPGA logic")
        flash_fpga_fw_parser.add_argument("file_name")

        # Charger State
        sub_parsers.add_parser("oled_display_state", help="Dump information about the OLEDWorks 2k display")

        args = parser.parse_args()
        return args

    def flashAndVerifySTM32InBootloader(file_name):
        def callback(finished: bool, is_verify: bool, percent_complete: float):
            stage = "Verify" if is_verify else "Flash"
            print(f"\r {stage} Progress:{percent_complete:3.0f} ", end="\n" if finished else "")
        verify_ok = STM32_Firmware_Update.flash_and_verify_STM32_FW(file_name, True, True, callback)
        verify_ok_str = "OK" if verify_ok else "FAIL"
        Logger.info(f"Verify Result: {verify_ok_str}")

    def verifySTM32InBootloader(file_name):
        def callback(finished: bool, is_verify: bool, percent_complete: float):
            stage = "Verify" if is_verify else "Flash"
            print(f"\r {stage} Progress:{percent_complete:3.0f} ", end="\n" if finished else "")
        verify_ok = STM32_Firmware_Update.flash_and_verify_STM32_FW(file_name, False, True, callback)
        verify_ok_str = "OK" if verify_ok else "FAIL"
        Logger.info(f"Verify Result: {verify_ok_str}")

    def handleArgsNoDevice(args) -> int:
        if (args.sub_command == "version"):
            Logger.info(f"GUI/CLI Version: {AppVersion.GIT_VERSION}")
            return 0
        elif (args.sub_command == "flash_stm32_fw"):
            OLED_2k.flashAndVerifySTM32InBootloader(args.file_name)
            return 0
        elif (args.sub_command == "verify_stm32_fw"):
            OLED_2k.verifySTM32InBootloader(args.file_name)
            return 0
        return -1

    def handleArgs(self, args) -> int:
        if (args.sub_command == "version"):
            Logger.info(f"GUI/CLI Version: {AppVersion.GIT_VERSION}")
            version = self.queryMicroVersion()
            Logger.info(f"STM32 Version: {version.major}.{version.minor}")
            Logger.info(f"STM32 Git Version: {version.git_version}")
        elif (args.sub_command == "reboot_bootloader"):
            self.rebootBootloader()
        elif (args.sub_command == "reboot"):
            self.reboot()
        elif (args.sub_command == "flash_fpga_fw"):
            def callback(finished: bool, percent_complete: float):
                print(f"\r Flash Progress:{percent_complete:3.0f}", end="\n" if finished else "")
            self.flash_FPGA_FW(args.file_name, callback)
            self.reboot()
        elif (args.sub_command == "flash_stm32_fw"):
            self.rebootBootloader()
            time.sleep(OLED_2k.REBOOT_TO_BOOTLOADER_DELAY_SECONDS)
            Logger.info("")
            OLED_2k.flashAndVerifySTM32InBootloader(args.file_name)
        elif (args.sub_command == "verify_stm32_fw"):
            self.rebootBootloader()
            time.sleep(OLED_2k.REBOOT_TO_BOOTLOADER_DELAY_SECONDS)
            Logger.info("")
            OLED_2k.verifySTM32InBootloader(args.file_name)
        elif (args.sub_command == "oled_display_state"):
            oled_display_state: Six15_API.Response.OLED_DisplayState = self.queryOLED_DisplayState()
            Logger.info(f"temp_value: {oled_display_state.temp_value}")
            return -1
        return 0


def main():
    OLED_2k_Gui = __import__("594_gui")
    sys.exit(OLED_2k_Gui.run_cli())


if __name__ == "__main__":
    main()
