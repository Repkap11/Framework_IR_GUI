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
import framework_ir_six15_api as Six15_API
from lib_six15_api.six15_api_backend import Six15_API_Backend
from framework_ir_six15_api import Framework_IR_Six15_API
from lib_six15_api.logger import Logger
import lib_six15_api.stm32_firmware_updater as STM32_Firmware_Update

NUM_CHARGER_BAYS = 4


class Framework_IR(Framework_IR_Six15_API):

    REBOOT_TO_BOOTLOADER_DELAY_SECONDS = 2
    REBOOT_TO_DISCONNECT_DELAY_SECONDS = 0.5

    def __init__(self, backend: Six15_API_Backend, *args) -> None:
        super().__init__(backend, False, *args)
        self.backend = backend

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


    def parseForArgs():
        parser = argparse.ArgumentParser(description='Framework IR CLI')
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
            Framework_IR.flashAndVerifySTM32InBootloader(args.file_name)
            return 0
        elif (args.sub_command == "verify_stm32_fw"):
            Framework_IR.verifySTM32InBootloader(args.file_name)
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
        elif (args.sub_command == "flash_stm32_fw"):
            self.rebootBootloader()
            time.sleep(Framework_IR.REBOOT_TO_BOOTLOADER_DELAY_SECONDS)
            Logger.info("")
            Framework_IR.flashAndVerifySTM32InBootloader(args.file_name)
        elif (args.sub_command == "verify_stm32_fw"):
            self.rebootBootloader()
            time.sleep(Framework_IR.REBOOT_TO_BOOTLOADER_DELAY_SECONDS)
            Logger.info("")
            Framework_IR.verifySTM32InBootloader(args.file_name)
        return 0


def main():
    Framework_IR_Gui = __import__("framework_ir_gui")
    sys.exit(Framework_IR_Gui.run_cli())


if __name__ == "__main__":
    main()
