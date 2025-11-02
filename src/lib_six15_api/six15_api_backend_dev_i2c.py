# This backend talks over i2c, via an FTDI USB breakout board, normally requiring a VGA/HDMI breakout board connected to DDC/EDID pins
# Uses the python "pyftdi" package.
# Compatible with Windows and Linux.

from typing import Optional, Callable, Set
from periphery import I2C, I2CError
import usb
import time
import struct
from lib_six15_api.logger import Logger
from lib_six15_api.six15_api_backend import Six15_API_Backend
import pyedid
import subprocess
import glob
import os


class Six15_API_Backend_Dev_I2C(Six15_API_Backend):

    verboseCallback: Optional[Callable[[str], None]] = None

    def __init__(self, i2c: I2C, device_addr: int):
        self.i2c = i2c
        self.device_addr = device_addr
        self.has_seen_i2c_device = False

    def sendCommand(self, write_buff: bytes, read_size: int, timeout: int = 1000) -> Optional[bytes]:
        if len(write_buff) > Six15_API_Backend.MAX_TX_SIZE:
            Logger.error(f"Write size:{len(write_buff)} too big. Max supported size is:{Six15_API_Backend.MAX_TX_SIZE}")
        if (self.i2c == None):
            Logger.error("Can't sendCommand, device is closed")
            return None
        cmdBuffer = struct.pack("<HH", Six15_API_Backend.API_VERSION, len(write_buff))
        cmdBuffer = cmdBuffer + write_buff
        # Logger.info(f"Writing:{len(cmdBuffer)} reading:{read_size}")
        try:
            msgs = [I2C.Message(cmdBuffer, read=False)]
            self.i2c.transfer(self.device_addr, msgs)
            alsoRead = read_size > 0
            if not alsoRead:
                return None
        except I2CError as e:
            self.has_seen_i2c_device = False
            Logger.error(f"sendCommand err:{e}")
            return None

        # Logger.info(f"Read: 0x{read_buff.hex()}")
        start_time = time.monotonic()
        first_iteration = True
        while True:
            try:
                read_buff = bytearray(Six15_API_Backend_Dev_I2C.HEADER_SIZE+read_size)
                msgs = [I2C.Message(read_buff, read=True, flags=I2C._I2C_M_STOP)]
                self.i2c.transfer(self.device_addr, msgs)
                read_buff = msgs[0].data

                [version, device_read_size] = struct.unpack("<HH", read_buff[0:Six15_API_Backend.HEADER_SIZE])
                # Logger.info(f"version:{version}")
                # Logger.info(f"expected_read_len:{expected_read_len}")
                # Logger.info(f"buff_len:{len(read_buff)}")
                if (version != 1):
                    Logger.error(f"Unexpected version:{version} expected:{1}")
                    return None
                break

            except I2CError as e:
                if (not first_iteration):
                    time.sleep(0.01)
                first_iteration = False
                pass  # continue the loop or timeout

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
        payload_buff = read_buff[Six15_API_Backend_Dev_I2C.HEADER_SIZE:Six15_API_Backend_Dev_I2C.HEADER_SIZE+read_size_min]
        # Logger.info(f"Returning len:{len(payload_buff)}")
        return payload_buff

    def isConnected(self) -> bool:
        debug_connection = False

        def ignore(*args):
            pass
        printFunc = Logger.verbose if debug_connection else ignore

        if (self.i2c == None):
            # Closed devices are not connected
            printFunc("isConnected: No: Closed")
            return False
        try:
            if (self.has_seen_i2c_device):
                # We've already seen our device over I2C, don't talk to it again. Background loops that check connected shouldn't cause I2C messages.
                printFunc("isConnected: Yes: already seen")
                return True
            try:
                empty_buff = bytearray()
                msgs = [I2C.Message(empty_buff, read=False)]
                self.i2c.transfer(self.device_addr, msgs)
            except I2CError as e:
                printFunc(f"isConnected: No: I2C NACK:{e}")
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
        self.has_seen_i2c_device = False

    @staticmethod
    def findDevice_pi() -> Optional[I2C]:
        # The pi doesn't have a video output or EDID associated with it's I2C pins, so just assume it's I2C1.
        try:
            i2c = I2C("/dev/i2c-11")
        except I2CError as e:
            Logger.error(f"Err opening i2c:{e}")
            return None

        return i2c

    @staticmethod
    def findDevices_edid_product_id(product_id: int, manufacturer_pnp_id: str = "TDG") -> Set[I2C]:
        # I see that sometimes there is more than 1 valid i2c_dev_path and drm device for the same physical display.
        # When this happens, only 1 of them actually works. This function will find and return all of them.
        # It's up to the caller to check if they can actually talk to their device over the bus.
        results: Set = set()
        drm_paths = glob.glob("/sys/class/drm/*")
        drm_paths = list(reversed(drm_paths))

        for drm_path in drm_paths:
            edid_path = f"{drm_path}/edid"
            if not os.path.isfile(edid_path):
                continue
            with open(edid_path, 'rb') as edid_file:
                edid_bin = edid_file.read()
            try:
                edid = pyedid.parse_edid(edid_bin)
            except ValueError:
                # This happens sometimes when the edid is bad.
                continue
            if edid is None:
                continue
            if edid.manufacturer_pnp_id != manufacturer_pnp_id:
                continue

            def swap(num: int, length_bytes: int) -> int:
                return int.from_bytes(num.to_bytes(length_bytes, "little"), "big")

            # Fix bug in library.
            edid_product_id = swap(edid.product_id, 2)
            # edid_serial = swap(edid.serial, 4)

            if (edid_product_id != product_id):
                continue

            # print(f"product_id:{product_id}")
            # print(f"serial:{serial}")
            i2c_paths = glob.glob("*", root_dir=f"{drm_path}/ddc/i2c-dev")
            if len(i2c_paths) != 1:
                continue
            i2c_path = i2c_paths[0]
            i2c_dev_path = f"/dev/{i2c_path}"
            if not os.path.exists(i2c_dev_path):
                continue
            # print(drm_path)
            # print(edid)
            # print(i2c_dev_path)

            try:
                i2c = I2C(i2c_dev_path)
                results.add(i2c)
            except I2CError as e:
                Logger.error(f"Err opening i2c:{e}")
                continue
        return results


def main():
    devices = Six15_API_Backend_Dev_I2C.findDevices_edid_product_id(569)
    for device in devices:
        print(device)
        device.close()


if __name__ == "__main__":
    main()
