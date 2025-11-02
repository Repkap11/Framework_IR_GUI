#!/usr/bin/env python3
import sys
import traceback
from lib_six15_api.logger import Logger

# From https://timlehr.com/python-exception-hooks-with-qt-message-box/


class SysExceptionHook:

    def __init__(self):
        # this registers the exception_hook() function as hook with the Python interpreter
        sys.excepthook = self.exception_hook

    def exception_hook(self, exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            # ignore keyboard interrupt to support console applications
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
        else:
            log_msg_full = '\n'.join([''.join(traceback.format_tb(exc_traceback)), '{0}: {1}'.format(exc_type.__name__, exc_value)])
            print("Uncaught exception:\n {0}".format(log_msg_full))
            log_msg_short = str(exc_value)

            Logger.critical_error(log_msg_short)
