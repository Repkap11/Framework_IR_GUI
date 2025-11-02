from abc import ABC, abstractmethod
from typing import Optional, Callable


class Six15_API_Backend(ABC):
    API_VERSION = 1
    MAX_TX_SIZE = 448  # Currently limited by the HID backend to (512-64)
    HEADER_SIZE = 4  # 1 byte for version, 1 byte status, 2 bytes for size.

    verboseCallback: Optional[Callable[[str], None]] = None

    def sendVerboseCallback(self, message: str):
        if (self.verboseCallback):
            self.verboseCallback(message)

    def setVerboseListener(self, callback: Optional[Callable[[str], None]] = None):
        self.verboseCallback = callback

    @abstractmethod
    def sendCommand(self, write_buff: bytes, read_size: int, timeout: int = 1000) -> Optional[bytes]:
        pass

    @abstractmethod
    def isConnected(self) -> bool:
        pass

    @abstractmethod
    def close(self):
        pass

    # def findDevice()
    # Most backends also have a findDevice() static function which can find an instance of themselves,
    # Or a port/path that can be used to construct a backend of that type, along with any other needed information.
