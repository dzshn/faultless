"""Catch abnormal program state. Allows handling segfaults & more."""

import os
import gc
import pickle
import signal
from multiprocessing.shared_memory import SharedMemory
from typing import Any


class Interrupt(OSError):
    """OS or program interrupt caught."""
    def __init__(self, exit_code: int) -> None:
        self.exit_code = exit_code
        super().__init__(exit_code)

    def __str__(self) -> str:
        return f"caught non-zero status: {self.exit_code}"


class SignalInterrupt(Interrupt):
    """Signal interrupt caught."""
    def __str__(self) -> str:
        sig = -self.exit_code
        desc = signal.strsignal(sig)
        name = signal.Signals(sig).name
        msg = f"{name} caught: {desc}"
        if os.WCOREDUMP(self.exit_code):
            msg += " (core dumped)"
        return msg


class SegmentationFault(SignalInterrupt):
    """Segmentation fault (SIGSEGV) caught."""
    def __init__(self) -> None:
        super().__init__(exit_code=-signal.SIGSEGV)


def faultless(func):
    """Decorate a function so abnormal state can be caught.

    Raises
    ------
    Interrupt, SignalInterrupt, SegmentationFault
        Function returned with non-zero status, or was terminated via signal.
    """
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        mem = SharedMemory(create=True, size=256)
        gc.freeze()
        pid = os.fork()
        if pid == 0:
            ret = pickle.dumps(func(*args, **kwargs))
            mem.buf[0] = len(ret)
            mem.buf[1:len(ret)+1] = ret
            os._exit(0)

        try:
            _, code = os.wait()
            exit_code = os.waitstatus_to_exitcode(code)
            if exit_code == -signal.SIGSEGV:
                raise SegmentationFault
            if exit_code < 0:
                raise SignalInterrupt(exit_code)
            if exit_code != 0:
                raise Interrupt(exit_code)
            length = mem.buf[0]
            return pickle.loads(mem.buf[1:length+1])
        finally:
            gc.unfreeze()
            mem.unlink()

    return wrapper
