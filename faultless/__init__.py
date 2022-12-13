"""Catch abnormal program state. Allows handling segfaults & more."""

import os
import functools
import gc
import math
import pickle
import signal
import socket
from multiprocessing.shared_memory import SharedMemory
from typing import Any, Literal


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


def faultless(
    *args: Any,
    method: Literal["buffer", "socket", "none"] = "buffer",
    return_buffer: int = 255,
):
    """Decorate a function so abnormal state can be caught.

    Arguments
    ---------
    method : {"buffer", "socket", "none"}, default = "buffer"
        Defines how the (pickled) return value of the function is passed back.

        - `none`: don't return anything
        - `buffer`: allocate shared memory for the object
        - `socket`: transfer the object over a socket pair

    return_buffer : int, default = 255
        If `method` is `buffer`, this will be the preallocated memory for the
        return value.

    Raises
    ------
    Interrupt, SignalInterrupt, SegmentationFault
        Function returned with non-zero status, or was terminated via signal.
    """

    def decorator(func):
        if method == "socket":
            return _wrapper_socket(func)
        if method == "buffer":
            return _wrapper_shared_mem(func, return_buffer)
        if method == "none":
            return _wrapper_none(func)
        raise ValueError("method expects one of 'buffer', 'socket' or 'none'")

    if args and callable(args[0]):
        return decorator(args[0])

    if len(args) == 2:
        method, return_buffer = args
    if len(args) == 1:
        method = args[0]
    return decorator


def _wrapper_shared_mem(func, size: int):
    size_length = math.ceil(size.bit_length() / 8)

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        mem = SharedMemory(create=True, size=size+size_length)
        gc.freeze()
        pid = os.fork()
        if pid == 0:
            try:
                res = (False, func(*args, **kwargs))
            except Exception as exc:
                res = (True, exc)
            data = pickle.dumps(res)
            mem.buf[:size_length] = len(data).to_bytes(size_length, "little")
            mem.buf[size_length:len(data)+size_length] = data
            os._exit(0)

        try:
            _, code = os.wait()
            exit_code = os.waitstatus_to_exitcode(code)
            if mem.buf[0]:
                length = int.from_bytes(mem.buf[:size_length], "little")
                err, obj = pickle.loads(mem.buf[size_length:length+size_length])
                if err:
                    raise obj
                return obj

            raise _interrupt(exit_code)

        finally:
            gc.unfreeze()
            mem.unlink()

    return wrapper


def _wrapper_socket(func):
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        parent, child = socket.socketpair()
        parent.setblocking(False)
        gc.freeze()
        pid = os.fork()
        if pid == 0:
            try:
                ret = pickle.dumps(func(*args, **kwargs))
            except Exception as e:
                child.send(b"\1")
                child.send(pickle.dumps(e))
            else:
                child.send(b"\0")
                child.send(ret)
            os._exit(0)

        try:
            _, code = os.wait()
            exit_code = os.waitstatus_to_exitcode(code)
            res = bytearray()
            while True:
                try:
                    res.extend(parent.recv(4096))
                except BlockingIOError:
                    break
            if res:
                obj = pickle.loads(res[1:])
                if res[0]:
                    raise obj
                return obj

            raise _interrupt(exit_code)

        finally:
            gc.unfreeze()

    return wrapper


def _wrapper_none(func):
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        gc.freeze()
        pid = os.fork()
        if pid == 0:
            func(*args, **kwargs)
            os._exit(0)

        try:
            _, code = os.wait()
            exit_code = os.waitstatus_to_exitcode(code)
            if exit_code != 0:
                raise _interrupt(exit_code)

        finally:
            gc.unfreeze()

    return wrapper


def _interrupt(exit_code: int) -> Interrupt:
    if exit_code == -signal.SIGSEGV:
        return SegmentationFault()
    if exit_code < 0:
        return SignalInterrupt(exit_code)
    if exit_code != 0:
        return Interrupt(exit_code)
    raise RuntimeError("attempted to raise zero status (return data unset?)")
