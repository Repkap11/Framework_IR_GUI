# This backend talks over i2c, via an FTDI USB breakout board, normally requiring a VGA/HDMI breakout board connected to DDC/EDID pins
# Uses the python "pyftdi" package.
# Compatible with Windows and Linux.

from typing import Optional, Callable
from pyftdi.i2c import I2cController, I2cPort, I2cIOError, I2cNackError
from pyftdi.ftdi import FtdiError
import usb
import time
import struct
from lib_six15_api.logger import Logger
from lib_six15_api.six15_api_backend import Six15_API_Backend


# https://github.com/eblot/pyftdi/issues/186#issuecomment-619944788


class Six15_API_Backend_FTDI(Six15_API_Backend):
    VID_FTDI_I2C = 0x0403
    PID_FTDI_I2C = 0x6014

    verboseCallback: Optional[Callable[[str], None]] = None

    def __init__(self, i2c: I2cController, device_addr: int):
        self.i2c = i2c
        self.has_seen_i2c_device = False
        self.i2c_port = i2c.get_port(device_addr)

    def sendCommand(self, write_buff: bytes, read_size: int, timeout: int = 1000) -> Optional[bytes]:
        if len(write_buff) > Six15_API_Backend.MAX_TX_SIZE:
            Logger.error(f"Write size:{len(write_buff)} too big. Max supported size is:{Six15_API_Backend.MAX_TX_SIZE}")
        if (self.i2c_port == None):
            Logger.error("Can't sendCommand, device is closed")
            return None
        cmdBuffer = struct.pack("<HH", Six15_API_Backend.API_VERSION, len(write_buff))
        cmdBuffer = cmdBuffer + write_buff
        # Logger.info(f"Writing:{len(cmdBuffer)} reading:{read_size}")
        try:
            self.i2c_port.write(cmdBuffer)
            alsoRead = read_size > 0
            if not alsoRead:
                return None
        except I2cIOError as e:
            self.has_seen_i2c_device = False
            Logger.error(f"sendCommand err:{e}")
            return None

        # Logger.info(f"Read: 0x{read_buff.hex()}")
        start_time = time.monotonic()
        first_iteration = True
        while True:
            try:
                read_buff = self.i2c_port.read(Six15_API_Backend_FTDI.HEADER_SIZE+read_size)
                [version, device_read_size] = struct.unpack("<HH", read_buff[0:Six15_API_Backend.HEADER_SIZE])
                # Logger.info(f"version:{version}")
                # Logger.info(f"expected_read_len:{expected_read_len}")
                # Logger.info(f"buff_len:{len(read_buff)}")
                if (version != 1):
                    Logger.error(f"Unexpected version:{version} expected:{1}")
                    return None
                break

            except I2cNackError as e:
                if (not first_iteration):
                    time.sleep(0.01)
                first_iteration = False
                pass  # continue the loop

            current_time = time.monotonic()
            diff_time_ms = (current_time - start_time)*1000
            if (diff_time_ms > timeout):
                Logger.error("Timeout waiting for busy flag to clear.")
                # Timed out
                self.has_seen_i2c_device = False
                return None
            # Logger.info(f"Busy, reading again:{diff_time_ms}/{timeout}")

        if (device_read_size != read_size):
            Logger.error(f"Response packet size:0x{device_read_size:02X}({device_read_size}) wasn't the size we expected:0x{read_size:02X}({read_size}) for cmd:0x{write_buff[0]:02X}")
            return None

        read_size_min = device_read_size if device_read_size < read_size else read_size
        payload_buff = read_buff[Six15_API_Backend_FTDI.HEADER_SIZE:Six15_API_Backend_FTDI.HEADER_SIZE+read_size_min]
        # Logger.info(f"Returning len:{len(payload_buff)}")
        return payload_buff

    def isConnected(self) -> bool:
        debug_connection = False

        def ignore(*args):
            pass
        printFunc = Logger.verbose if debug_connection else ignore

        if (self.i2c == None or self.i2c_port == None):
            # Closed devices are not connected
            printFunc("isConnected: No: Closed")
            return False
        try:
            try:
                # It would be better to do something that has no potential side affects, but there doesn't seem to be anything less impactful than flush.
                self.i2c.flush()
            except FtdiError as e:
                self.has_seen_i2c_device = False
                printFunc("isConnected: No: FTDI")
                return False

            # We've found the FTDI chip, what about the device at our address?
            if (self.has_seen_i2c_device):
                # We've already seen our device over I2C, don't talk to it again. Background loops that check connected shouldn't cause I2C messages.
                printFunc("isConnected: Yes: already seen")
                return True
            try:
                ack = self.i2c_port.poll(True)
            except I2cIOError as e:
                printFunc("isConnected: No: I2C err")
                return False
            if (not ack):
                printFunc("isConnected: No: I2C NACK")
                return False
            self.has_seen_i2c_device = True
            printFunc("isConnected: Yes: newly seen")
            return True
        except:
            printFunc("isConnected: No: Other (race condition)")
            return False

    def close(self):
        if (self.i2c != None):
            self.i2c.close()
        self.i2c = None
        self.i2c_port = None
        self.has_seen_i2c_device = False

    @staticmethod
    def findDevice(frequency: int = 30000) -> Optional[I2cController]:
        devices = list(usb.core.find(idVendor=Six15_API_Backend_FTDI.VID_FTDI_I2C, idProduct=Six15_API_Backend_FTDI.PID_FTDI_I2C, find_all=True))
        if len(devices) == 0:
            # Logger.warn("No ftdi usb device")
            return None
        if len(devices) != 1:
            Logger.warn("Error, more than 1 FTDI device connected, please only connect 1 at a time")
            return None
        dev = devices[0]

        i2c = I2cController()

        try:
            i2c.configure(dev, clockstretching=True, frequency=frequency, rdoptim=False)
        except FtdiError as e:
            Logger.error(f"Err opening i2c:{e}")
            i2c.close()
            return None

        i2c.set_retry_count(1)
        return i2c
