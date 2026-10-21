"""cssref.py — machine states for the CSS CPU's model (machine/csssim.py) and its tools: the machine at its first step with
ROM and RAM as the CSS compiler leaves them, from a program (load) or from a machine image (from_image)."""
import os, sys, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, 'compiler'), os.path.join(ROOT, 'machine')]
import cc_ref as R
LA = R.LAYOUT; ROMN = LA["rom_size"]; SDATA = R.SDATA; STRTAG = R.STRTAG; AMASK = R.AMASK
COLS, ROWS = LA['cols'], LA['rows']; OUT_BASE = ROMN + LA['ram_size'] - COLS * ROWS

def state(mem):
    return {'pc': LA['code_base'], 'fp': LA['sp0'], 'optr': 0, 'pst': 0, 'mem': mem, 'out': [], 'halt': False, 'steps': 0}

def load(path, lib=None):
    """the machine at its first step (pc = code_base, fp = sp0) for the program in path"""
    lib = lib or json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))
    return load_src(open(path).read(), lib)

def load_src(src, lib):
    c = R.Compiler(LA['data_base'], LA['code_base'], lib); words, data = c.compile(src)
    assert not c.err, c.err
    mem = {i: w for i, w in enumerate(lib['rom'])}
    mem.update(R.image_mem(c, words, data, lib.get('init')))
    return state(mem)

def from_image(im):
    """the same, from a mkimage-style image (rom + ram lists)"""
    mem = {i: w for i, w in enumerate(im['rom']) if w}
    mem.update({im['romSize'] + i: w for i, w in enumerate(im['ram']) if w})
    return state(mem)
