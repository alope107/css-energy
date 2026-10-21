#!/usr/bin/env python3
"""rtlib.py lib.json — the runtime in ROM for the register machine. Empty for now: the language without strings built at run
time, arrays and objects needs no runtime library. (The stack machine's runtime, compiled by jsc from lib_src.js with
hand-written routines, is in git history: commit 212175a.)"""
import sys, os, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE]; import cc_ref as R
L = R.LAYOUT

def build(out):
    lib = dict(rom=[], entries={}, romSize=L['rom_size'], dataBase=L['data_base'], codeBase=L['code_base'], init=L['init'])
    json.dump(lib, open(out, 'w'))

if __name__ == '__main__':
    build(sys.argv[1])
