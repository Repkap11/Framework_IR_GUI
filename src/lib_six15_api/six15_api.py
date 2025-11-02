from typing import Optional, Callable, Tuple, Dict, Any, Type
from abc import ABC, abstractmethod
from lib_six15_api.six15_api_backend import Six15_API_Backend
import struct
from lib_six15_api.logger import Logger
from threading import Lock


class Base_Response(ABC):
    @staticmethod
    @abstractmethod
    def format() -> Optional[str]:
        pass

    @staticmethod
    def decodeToStr(data: bytes) -> str:
        return data.decode('utf-8', errors='replace').strip('\0')

    @staticmethod
    def unpack_checked(format: str, buffer: bytes, resp_name: str) -> Tuple[Any, ...]:
        format_size = struct.calcsize(format)
        buffer_size = len(buffer)
        # raise RuntimeError(f"Response was size:{buffer_size} expected size:{format_size}")
        if (buffer_size < format_size):
            # This response isn't large enough for what we expect. Give up and hope the specific response type will try older versions.
            Logger.warn(f"Response \"{resp_name}\" size too small. Got size:{buffer_size} expected size:{format_size}")
            # raise RuntimeError("Too small")
            return None
        if (buffer_size > format_size):
            # Automatically remove any unexpected bytes.
            # This allows any future version of the response to be larger than the current currently expected value.
            Logger.warn(f"Response \"{resp_name}\" size too big. Got size:{buffer_size} expected size:{format_size}")
            buffer = buffer[0:format_size]
            # raise RuntimeError("Too big")
        return struct.unpack(format, buffer)


class Response_Default(Base_Response):
    @staticmethod
    def format() -> Optional[str]:
        return "<B"

    def __init__(self, resp):
        data = Base_Response.unpack_checked(self.format(), resp, self.__class__.__name__)

        if (data == None):
            raise ValueError(f"Device did not respond to: {self.__class__.__name__} as expected.")

        self.status = data[0]


class Base_CMD(ABC):
    value: int
    response: Type[Base_Response]


class Six15_API:

    def __init__(self, backend: Six15_API_Backend, fake: bool = False, *args) -> None:
        super().__init__(*args)
        self.backend = backend
        self.fake = fake
        self.comms_mutex = Lock()

    def isConnected(self) -> bool:
        return self.backend.isConnected()

    def close(self):
        self.backend.close()

    def sendSimpleCMD(self, cmd: Base_CMD, payload: Optional[bytes] = None, timeout: int = 1000) -> Optional[int]:
        resp: Response_Default = self.sendCommand(cmd, payload, timeout)
        if resp == None:
            return None
        return resp.status

    def sendCommand(self, cmd: Base_CMD, payload: Optional[bytes] = None, timeout: int = 1000) -> Optional[Base_Response]:
        with self.comms_mutex:
            cmdBuffer = bytearray(1)
            cmdBuffer[0] = cmd.value
            if (payload != None):
                cmdBuffer += payload
            # Use the backend to to the write
            if cmd.response == None:
                response_size = 0
            else:
                response_size = struct.calcsize(cmd.response.format())

            resp = self.backend.sendCommand(cmdBuffer, response_size, timeout)
            if (resp == None):
                return None
            # Parse the response into the response type
            resp = cmd.response(resp)
            return resp
