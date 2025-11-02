# This backend talks over USB HID
# Uses the python "hid" package.
# Compatible with Windows and Linux.

import hid
import platform
import struct
from lib_six15_api.six15_api_backend import Six15_API_Backend
from typing import Callable, Optional, Tuple
from lib_six15_api.logger import Logger


class Six15_API_Backend_HID(Six15_API_Backend):

    REPORT_ID_IN = 1
    REPORT_ID_OUT = 2
    HID_REPORT_SIZE = 64

    HID_API_HEADER_SIZE = 2 + Six15_API_Backend.HEADER_SIZE  # 2 extra bytes for the HID header

    def __init__(self, usb_device: hid.device, hid_path: str, vid: str, pid: str):
        self.dev = usb_device
        self.hid_path = hid_path
        self.vid = vid
        self.pid = pid

    def isConnected(self) -> bool:
        if self.dev == None or self.hid_path == None:
            return False
        device_dict = hid.enumerate(self.vid, self.pid)
        if (device_dict is None or len(device_dict) != 1):
            return False
        device_props = device_dict[0]
        hid_path = device_props["path"]
        paths_match = hid_path == self.hid_path
        return paths_match

    def writePacket(self, buf: bytes):
        # time.sleep(0.025)
        buf_len = len(buf)
        if buf_len > Six15_API_Backend.MAX_TX_SIZE:
            raise ValueError("Write too large")

        num_bytes_sent = 0
        while (num_bytes_sent < buf_len):
            num_byes_remaining = buf_len - num_bytes_sent
            if (num_bytes_sent == 0):
                header_bytes = struct.pack('<HHH', Six15_API_Backend_HID.REPORT_ID_OUT, Six15_API_Backend.API_VERSION, buf_len)
            else:
                header_bytes = struct.pack('<HH', Six15_API_Backend_HID.REPORT_ID_OUT, Six15_API_Backend.API_VERSION)
            header_len = len(header_bytes)
            max_payload_len = Six15_API_Backend_HID.HID_REPORT_SIZE - header_len
            if (num_byes_remaining < max_payload_len):
                payload_len = num_byes_remaining
                padding_len = max_payload_len - num_byes_remaining
            else:
                payload_len = max_payload_len
                padding_len = 0
            padding_bytes = bytearray(padding_len)
            final_buf = header_bytes + buf[num_bytes_sent:num_bytes_sent+payload_len] + padding_bytes
            if len(final_buf) != 64:
                Logger.error(len(final_buf))
                raise AssertionError('Paul is bad a math')
            self.sendVerboseCallback("Write:0x" + buf.hex())
            self.dev.write(final_buf)
            num_bytes_sent = num_bytes_sent+payload_len

    def readPacket(self, timeout=1000, retries=3) -> bytes:
        if (self.dev == None):
            return None
        # time.sleep(0.025)
        tries = 0
        buffer = bytearray(0)
        expectedReadSize = Six15_API_Backend_HID.HID_REPORT_SIZE
        payload_len = 0
        while (len(buffer) < expectedReadSize):
            readLen = Six15_API_Backend_HID.HID_REPORT_SIZE - (len(buffer) % Six15_API_Backend_HID.HID_REPORT_SIZE)
            new_buffer = bytes(self.dev.read(readLen, timeout))
            buffer = buffer + new_buffer
            if (len(new_buffer) == 0):
                tries = tries + 1
            else:
                tries = 0
            if (tries > retries):
                raise TimeoutError(f"Timeout waiting for payload report. Read:{len(buffer)} bytes out of {expectedReadSize}")
            if (len(buffer) > Six15_API_Backend_HID.HID_API_HEADER_SIZE):
                # We have enough data to read the header.
                [hid_header, version, payload_len] = struct.unpack_from('<HHH', buffer)
                if (hid_header != Six15_API_Backend_HID.REPORT_ID_IN):
                    raise ValueError(f"Unexpected HID Header value: {hid_header}")
                if (version != Six15_API_Backend.API_VERSION):
                    raise ValueError(f"Unexpected API Version value: {version}")

                pkt_size = payload_len + Six15_API_Backend_HID.HID_API_HEADER_SIZE
                expectedReadSize = pkt_size + (Six15_API_Backend_HID.HID_REPORT_SIZE - pkt_size) % Six15_API_Backend_HID.HID_REPORT_SIZE
                pass
        payload = bytearray()
        index = 0
        while index + Six15_API_Backend_HID.HID_REPORT_SIZE <= len(buffer):
            size = Six15_API_Backend_HID.HID_REPORT_SIZE - Six15_API_Backend_HID.HID_API_HEADER_SIZE
            if (size + len(payload) > payload_len):
                size = payload_len - len(payload)
            payload.extend(buffer[index + Six15_API_Backend_HID.HID_API_HEADER_SIZE: index + Six15_API_Backend_HID.HID_API_HEADER_SIZE + size])
            index += Six15_API_Backend_HID.HID_REPORT_SIZE
        # payload = buffer[Six15_API.HID_API_HEADER_SIZE:(Six15_API.HID_API_HEADER_SIZE+payload_len)]
        self.sendVerboseCallback("Read:0x" + payload.hex())
        return payload

    def sendCommand(self, write_buff: bytes, read_size: int, timeout: int = 1000) -> Optional[bytes]:
        self.writePacket(write_buff)
        if (read_size == 0):
            return None
        return self.readPacket(timeout)

    def close(self):
        if (self.dev != None):
            self.dev.close()
        self.dev = None
        self.hid_path = None

    @staticmethod
    def findDevice(vid: int, pid: int) -> Tuple[Optional[hid.device], Optional[str]]:
        device_dict = hid.enumerate(vid, pid)

        # Remove any duplicate devices which have the same path, these are not actually unique devices.
        device_dict = {device["path"]: device for device in device_dict}
        device_dict = list(device_dict.values())

        if (device_dict is None or len(device_dict) != 1):
            return None, None

        hid_device: hid.device = hid.device()
        device_props = device_dict[0]
        hid_path: str = device_props["path"]

        hid_device.open_path(hid_path)

        return hid_device, hid_path
