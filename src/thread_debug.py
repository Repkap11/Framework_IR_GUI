
# Setting this to true will break builds, but is needed for setting break points in other threads in the debugger
DEBUG_THREADS: bool = False

if DEBUG_THREADS:
    import debugpy

    def debug_this_thread():
        debugpy.debug_this_thread()
else:
    def debug_this_thread():
        pass
