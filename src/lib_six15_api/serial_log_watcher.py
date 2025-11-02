import time
from PySide6.QtCore import QThread
import serial
import serial.tools.list_ports
import platform
from lib_six15_api.logger import Logger


class Serial_LogWatcher(QThread):

    def __init__(self, vid: int, pid: int, prefix:str = "  ") -> None:
        super().__init__()
        self.vid = vid
        self.pid = pid
        self.prefix = prefix

    def run(self):
        if (self != None):
            interruptFunc = self.isInterruptionRequested
        else:
            def noInterrupt():
                return False
            interruptFunc = noInterrupt
        while (not interruptFunc()):
            try:
                serial_device = None
                for port in serial.tools.list_ports.comports(include_links=False):
                    if (port.vid == self.vid and port.pid == self.pid):
                        serial_device = port
                        break
                if serial_device == None:
                    time.sleep(0.1)
                    continue
                if platform.system() == 'Windows':
                    # Logger.verbose("Delaying connection on Windows")
                    time.sleep(1)  # Windows takes forever at starting the CDC driver.
                time.sleep(0.5)  # To let rest of the GUI update first. This tends to make the log look nicer

                with serial.Serial(serial_device.device, 115200, timeout=0.1) as dev:
                    data = bytearray(0)
                    while (not interruptFunc()):
                        data += dev.readline()
                        if (len(data) == 0):
                            time.sleep(0.1)
                            continue
                        line = data.decode(errors='replace')
                        if (not line.endswith("\n")):
                            continue
                        data = bytearray(0)
                        Logger.log_prefixed(line.rstrip(), self.prefix)
            except serial.SerialException as e:
                # We sort of expect serial errors, since it will go away when the device disconnects.
                # Print them to the console, just because they might be interesting.
                print(f"Serial Err:{e}")
                time.sleep(0.5)


if __name__ == '__main__':
    logWatcher = Serial_LogWatcher.run(None)
