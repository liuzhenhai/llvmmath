# -*- coding: utf-8 -*-

"""
Support for math as a postpass on LLVM IR.
"""

from __future__ import print_function, division, absolute_import

import os
import ctypes.util
from os.path import join, dirname
from itertools import imap
import collections

from numba import *
from numba.support import ctypes_support, llvm_support
from numba.pycc import compiler
from numba.support.math_support import symbols

import llvm.core
import numpy.core.umath

root = dirname(__file__)

# ______________________________________________________________________
# openlibm

# print("---------- OPENLIBM -----------")
symbol_data = open(os.path.join(os.path.dirname(__file__), "Symbol.map")).read()
openlibm_symbols = set(word.rstrip(';') for word in symbol_data.split())
openlibm = ctypes.CDLL(ctypes.util.find_library("openlibm"))
openlibm_library, openlibm_missing = symbols.get_symbols(
    openlibm, have_symbol=lambda libm, cname: cname in openlibm_symbols)

# ______________________________________________________________________
# NumPy umath

# print("---------- umath -----------")
umath = ctypes.CDLL(numpy.core.umath.__file__)
umath_mangler = lambda name, ty: 'npy_' + symbols.unary_math_suffix(name, ty)
umath_library, umath_missing = symbols.get_symbols(umath, umath_mangler)

# ______________________________________________________________________
# System's libmath

# print("---------- libm -----------")
libm = ctypes.CDLL(ctypes.util.find_library("m"))
libm_library, libm_missing = symbols.get_symbols(libm)

# ______________________________________________________________________

# print("---------- mathcode -----------")
def mathcode_mangler(name, ty):
    if name == 'abs':
        absname = symbols.absname(ty)
        if ty.kind == llvm.core.TYPE_INTEGER:
            return absname # abs(), labs(), llabs()
        elif ty.kind in symbols.float_kinds:
            return 'npy_' + absname
        else:
            return 'nc_' + absname
    elif ty.kind == llvm.core.TYPE_STRUCT:
        return 'nc_' + symbols.unary_math_suffix(name, ty.elements[0])
    else:
        return umath_mangler(name, ty)

dylib = 'mathcode' + compiler.find_shared_ending()
llvmmath = ctypes.CDLL(join(root, 'mathcode', dylib))
llvm_library, llvm_missing = symbols.get_symbols(llvmmath, mathcode_mangler)

# ______________________________________________________________________

def link_llvm_math_intrinsics(engine, module, library):
    """
    Add a runtime address for all global functions named numba.math.*
    """
    # find all known math intrinsics and implement them.
    return
    for gv in module.list_globals():
        name = gv.getName()
        if name.startswith("numba.math."):
            assert not gv.getInitializer()
            assert gv.type.kind == llvm.core.TYPE_FUNCTION

            signatures = library[gv.name]
            restype = gv.return_type
            argtype = gv.args[0]

            ptr = signatures[restype, argtype]
            engine.addGlobalMapping(gv, ptr)