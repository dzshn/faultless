import ctypes
from faultless import faultless, SegmentationFault


@faultless
def nullptr():
    return ctypes.c_void_p.from_address(0).value


try:
    nullptr()
except SegmentationFault:
    print("Safe!")
