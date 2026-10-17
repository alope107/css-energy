# Build the page and run the test levels. `make help` lists targets. Outputs go to build/ (gitignored).
PY    ?= python3
NODE  ?= node
B     := build
CC    := compiler
SPECK ?= mtv
# reproducible builds: stable @property order (Python set iteration) and font timestamps (fontTools)
export PYTHONHASHSEED := 0
export SOURCE_DATE_EPOCH := 0
# A check (l2, l3, the l5s) is the file build/<name>.<config>.log, written only when it passes (../shared/make/checks.mk):
# make re-runs it only when something it depends on is newer than its last pass, or with RERUN=1. <config> is a hash
# of the Node, Python, browser and environment variables it runs with (build/<py|fontcpu|ui>.<config>.id).
include ../shared/make/checks.mk
SUITE   := tests/suite tests/suite_err tests/fizz.js $(wildcard tests/suite/*.js tests/suite/*.out tests/suite_err/*.js)
PYSRC   := $(wildcard $(CC)/*.py $(CC)/*.json machine/*.py readback/*.py)
HARNESS := $(wildcard tools/*.js $(SHARED)/js/*.js)
# what the checks depend on outside the repo, and the environment variables their scripts read
L2       := $(B)/l2.$(call id,$(B)/py,-,tests/cmp_dsl.py $(PYSRC)).log
L3       := $(B)/l3.$(call id,$(B)/fontcpu,fontcpu,tests/suite_css.js $(HARNESS)).log
UICONF   := $(call id,$(B)/ui,fontcpu,machine/ui_seq.js tests/editor_input.js $(HARNESS))

.PHONY: help all lib image font page dist test test-browser test-ui test-ui-smoke test-all \
        expect l1 l2 l2-generic l3 l4 l5 l5-smoke l5-input clean

help:
	@echo "make page           build/js_in_css.xhtml (lib -> image -> CPU font -> page, ~25 s)"
	@echo "make test           fast levels, no browser: Node oracle, L1 reference, L2 DSL, L4 machine model (~5 s)"
	@echo "make test-browser   L3: the generated CSS compiler in Chrome vs the reference (~1.5 min)"
	@echo "make test-ui-smoke  L5 on a few programs: the real page, typed like a user (~1 min)"
	@echo "make test-ui        L5 on every quick program (~10 min)"
	@echo "make dist           copy the built page to dist/"

all: page

# ---- runtime library -> ROM (jsc.js, the self-hosted subset compiler, compiles lib_src.js under Node)
lib: $(CC)/lib.json
$(CC)/lib.json: $(CC)/lib_src.js $(CC)/libbuild.js $(CC)/jsc.js $(CC)/layout.json
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
l2: $(L2)                                 # DSL (page's specialised variants) vs reference, level by level
	$(call report,$<,3)
$(L2): tests/cmp_dsl.py $(PYSRC) $(SUITE) $(RERUN_IF)
	SPEC=1 SPECK=$(SPECK) $(LOGGED) $@ -t 3 -p '^ALL OK' -- $(PY) tests/cmp_dsl.py tests/suite/*.js tests/suite_err/*.js
l2-generic:                               # same, unspecialised parser (slower)
	$(PY) tests/cmp_dsl.py tests/suite/*.js tests/suite_err/*.js | tail -3
l4:                                       # font CPU model (uarch4) runs every compiled image vs Node
	$(PY) tests/suite_machine.py
$(B)/suite_css.xhtml: $(wildcard $(CC)/*.py) $(CC)/lib.json tests/suite_css.py
	REBUILD=1 $(PY) tests/suite_css.py $@ > /dev/null
$(B)/suite_css.xhtml.exp.json: $(B)/suite_css.xhtml tests/suite_css.py $(PYSRC) $(SUITE)   # cc_ref's words for each test
	$(PY) tests/suite_css.py $(B)/suite_css.xhtml > /dev/null
l3: $(L3)                                 # generated CSS compiler in Chrome vs reference, word for word
	$(call report,$<,25)
$(L3): $(B)/suite_css.xhtml $(B)/suite_css.xhtml.exp.json tests/suite_css.js $(HARNESS) $(RERUN_IF)
	$(LOGGED) $@ -t 25 -p '^([0-9]+)/\1 pass$$' -- $(NODE) tests/suite_css.js $(B)/suite_css.xhtml
# the initial program (tests/fizz.js = tests/suite/fizzbuzz.js) is checked against Node's output too (EXP1)
# suite_ui.py writes the expected consoles to build/ui_exp and prints ui_seq.js's arguments: args-<maxsteps>-<limit>.txt
$(B)/ui_exp/args-%.txt: tests/suite_ui.py $(PYSRC) $(SUITE)
	@mkdir -p $(@D); $(PY) tests/suite_ui.py $(subst -, ,$*) > $@.tmp && mv $@.tmp $@
# ui_seq.js exits 0 whatever happens: a program passed if its line says "ok":true
UIOK := -p '"ok":true' -f '"ok":false'
UI   := $(B)/js_in_css.xhtml machine/ui_seq.js $(HARNESS) $(SUITE) $(RERUN_IF)
l5: $(B)/l5.$(UICONF).log                 # the real page, typed like a user; console vs Node
	$(call report,$<,4)
$(B)/l5.$(UICONF).log: $(B)/ui_exp/args-1500-1000000.txt $(UI)
	EXP1=$(B)/ui_exp/fizzbuzz.grid $(LOGGED) $@ $(UIOK) -- $(NODE) machine/ui_seq.js $(B)/js_in_css.xhtml $$(cat $<)
l5-smoke: $(B)/l5-smoke.$(UICONF).log
	$(call report,$<,4)
$(B)/l5-smoke.$(UICONF).log: $(B)/ui_exp/args-400-6.txt $(UI)
	EXP1=$(B)/ui_exp/fizzbuzz.grid $(LOGGED) $@ $(UIOK) -- $(NODE) machine/ui_seq.js $(B)/js_in_css.xhtml $$(cat $<)
l5-input: $(B)/l5-input.$(UICONF).log     # the editor under user input: what the scan reads is what the editor shows
	$(call report,$<,2)
$(B)/l5-input.$(UICONF).log: $(B)/ui_exp/args-400-0.txt tests/editor_input.js $(UI)
	EXP=$(B)/ui_exp/fizzbuzz.grid $(LOGGED) $@ -- $(NODE) tests/editor_input.js $(B)/js_in_css.xhtml

test: expect l1 l2 l4
test-browser: l3
test-ui: l5
test-ui-smoke: l5-smoke
test-all: test l3 l5

clean:
	rm -rf $(B)
