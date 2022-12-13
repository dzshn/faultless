# faultless: catch 'em segfaults!

```py
import ctypes
from faultless import faultless, SegmentationFault


@faultless
def nullptr():
    return ctypes.c_void_p.from_address(0).value


try:
    nullptr()
except SegmentationFault:
    print("Safe!")
```

## Installation

Install with pip:

```sh
$ pip install git+https://github.com/dzshn/faultless
```

From source using [poetry](https://python-poetry.org):

```sh
$ poetry install
```

## wait what do you mean segfaults and python w-

uhhhhhhh
