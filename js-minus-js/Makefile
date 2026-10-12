# Build the page and run the test levels. `make help` lists targets. Outputs go to build/ (gitignored).
PY    ?= python3
NODE  ?= node
B     := build
CC    := compiler
SPECK ?= mtv
# reproducible builds: stable @property order (Python set iteration) and font timestamps (fontTools)
export PYTHONHASHSEED := 0
export SOURCE_DATE_EPOCH := 0

.PHONY: help all lib image font page dist test test-browser test-ui test-ui-smoke test-all \
        expect l1 l2 l2-generic l3 l4 l5 l5-smoke clean

help:
	@echo "make page           build/js_in_css.xhtml (lib -> image -> CPU font -> page, ~45 s)"
	@echo "make test           fast levels, no browser: Node oracle, L1 reference, L2 DSL, L4 machine model (~10 s)"
	@echo "make test-browser   L3: the generated CSS compiler in Chrome vs the reference (~3 min)"
	@echo "make test-ui-smoke  L5 on a few programs: the real page, typed like a user (~2 min)"
	@echo "make test-ui        L5 on every quick program (~45 min)"
	@echo "make dist           copy the built page to dist/"

all: page

# ---- runtime library -> ROM (jsc.js, the self-hosted subset compiler, compiles lib_src.js under Node)
lib: $(CC)/lib.json
$(CC)/lib.json: $(CC)/lib_src.js $(CC)/libbuild.js $(CC)/jsc.js
	$(NODE) $(CC)/libbuild.js $@

# ---- image (ROM = lib) -> CPU font (ROM baked into GSUB) -> page (editor + readback + CSS compiler + font CPU)
image: $(B)/ccimg.json
$(B)/ccimg.json: $(CC)/lib.json $(CC)/cc_ref.py $(CC)/mkimage.py tests/fizz.js
	@mkdir -p $(B)
	$(PY) $(CC)/mkimage.py tests/fizz.js $@

font: $(B)/f4cc_16.woff2
$(B)/f4cc_16.woff2: $(B)/ccimg.json $(wildcard machine/cpu4.py machine/cpugen.py machine/otl.py machine/uarch*.py machine/fontbase.py machine/fvm_build.py)
	CPUMOD=cpu4 $(PY) machine/fvm_build.py $(B)/ccimg.json 16 32 $(B)/f4cc_16

page: $(B)/js_in_css.xhtml
$(B)/js_in_css.xhtml: $(B)/f4cc_16.woff2 $(wildcard $(CC)/*.py machine/*.py readback/*.py)
	UI=1 $(PY) machine/gen_fvm4.py $(B)/ccimg.json $(B)/f4cc_16 $@

dist: page
	cp $(B)/js_in_css.xhtml dist/js_in_css.xhtml

# ---- tests (see docs/ARCHITECTURE.md#tests)
expect:                                   # Node is the oracle: writes tests/suite/*.out
	$(NODE) tests/suite_expect.js tests/suite
l1:                                       # reference compiler + 20-bit simulator vs Node
	$(PY) tests/suite_ref.py
l2:                                       # DSL (page's specialised variants) vs reference, level by level
	SPEC=1 SPECK=$(SPECK) $(PY) tests/cmp_dsl.py tests/suite/*.js tests/suite_err/*.js | tail -3
l2-generic:                               # same, unspecialised parser (slower)
	$(PY) tests/cmp_dsl.py tests/suite/*.js tests/suite_err/*.js | tail -3
l4:                                       # font CPU model (uarch4) runs every compiled image vs Node
	$(PY) tests/suite_machine.py
$(B)/suite_css.xhtml: $(wildcard $(CC)/*.py) $(CC)/lib.json tests/suite_css.py
	REBUILD=1 $(PY) tests/suite_css.py $@ > /dev/null
l3: $(B)/suite_css.xhtml                  # generated CSS compiler in Chrome vs reference, word for word
	$(PY) tests/suite_css.py $(B)/suite_css.xhtml > /dev/null
	$(NODE) tests/suite_css.js $(B)/suite_css.xhtml | tail -25
# the initial program (tests/fizz.js = tests/suite/fizzbuzz.js) is checked against Node's output too (EXP1)
l5: page                                  # the real page, typed like a user; console vs Node
	ARGS="$$($(PY) tests/suite_ui.py 1500)"; EXP1=$(B)/ui_exp/fizzbuzz.grid $(NODE) machine/ui_seq.js $(B)/js_in_css.xhtml $$ARGS
l5-smoke: page
	ARGS="$$($(PY) tests/suite_ui.py 400 6)"; EXP1=$(B)/ui_exp/fizzbuzz.grid $(NODE) machine/ui_seq.js $(B)/js_in_css.xhtml $$ARGS

test: expect l1 l2 l4
test-browser: l3
test-ui: l5
test-ui-smoke: l5-smoke
test-all: test l3 l5

clean:
	rm -rf $(B)
