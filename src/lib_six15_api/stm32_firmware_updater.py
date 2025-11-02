from typing import Optional, Callable

from lib_six15_api.logger import Logger
import lib_six15_api.pydfu as PyDfu


def flash_and_verify_STM32_FW(file_name: str, do_flash: bool, do_verify: bool, callback: Optional[Callable[[bool, bool, float], None]] = None) -> bool:
    elements = PyDfu.read_dfu_file(file_name)
    if not elements:
        Logger.error("No data in dfu file")
        return

    if (not do_flash and not do_verify):
        return False
    PyDfu.init()

    def progress_flash(addr, offset, size):
        if (callback):
            percent = offset / size * 100
            callback(False, False, percent)

    def progress_verify(addr, offset, size):
        if (callback):
            percent = (offset / size * 100)
            callback(False, True, percent)

    if (do_flash):
        PyDfu.write_elements(elements, False, progress=progress_flash)
        if (callback):
            callback(True, False, 100)

    if (do_verify):
        verify_ok = PyDfu.verify_elements(elements, progress=progress_verify)
        if (callback):
            callback(True, True, 100)
    else:
        verify_ok = False

    PyDfu.exit_dfu()
    return verify_ok
