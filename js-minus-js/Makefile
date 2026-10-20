# Build the page and run the test levels. `make help` lists targets. Outputs go to build/ (gitignored).
PY    ?= python3
NODE  ?= node
B     := build
CC    := compiler
SPECK ?= mtv
# browsers the browser levels (l3, fuzz-l3, the l5s) run in at once; their verdicts don't depend on it (SHARDS=1 for timing)
SHARDS ?= 6
# reproducible builds: stable @property order (Python set iteration) and font timestamps (fontTools)
export PYTHONHASHSEED := 0
export SOURCE_DATE_EPOCH := 0
# A check (l2, l3, the l5s) is the file build/<name>.<config>.log, written only when it passes (../shared/make/checks.mk):
# make re-runs it only when something it depends on is newer than its last pass, or with RERUN=1. <config> is a hash
# of the Node, Python, browser and environment variables it runs with (build/<py|fontcpu|ui>.<config>.id).
include ../shared/make/checks.mk
SUITE   := tests/suite tests/suite_err tests/fizz.js $(wildcard tests/suite/*.js tests/suite/*.out tests/suite_err/*.js)
PYSRC   := $(wildcard $(CC)/*.py $(CC)/*.json machine/*.py readback/*.py) $(SHARED)/py/csslabel.py
HARNESS := $(wildcard tools/*.js $(SHARED)/js/*.js)
# what the checks depend on outside the repo, and the environment variables their scripts read
L2       := $(B)/l2.$(call id,$(B)/py,-,tests/cmp_dsl.py $(PYSRC)).log
FUZZ     := $(B)/fuzz.$(call id,$(B)/py,-,tests/cmp_dsl.py tests/fuzz/fuzz.py tests/fuzz/oracle.js tests/fuzz/all.sh $(PYSRC)).log
# The browser's part needs `npm install`. Goals that launch no browser skip it (CI deploys with `make dist` and no
# npm packages: ../deploy/README.md), and those checks' logs get a name no pass is ever written under.
NOBROWSER := help all lib image page dist expect l1 l2 l2-generic c1 fuzz fuzz-quick test clean
BCONF     = $(if $(filter-out $(NOBROWSER),$(MAKECMDGOALS)),$(call id,$(1),fontcpu,$(2)),no-browser)
L3       := $(B)/l3.$(call BCONF,$(B)/fontcpu,tests/suite_css.js $(HARNESS)).log
UICONF   := $(call BCONF,$(B)/ui,machine/ui_seq.js tests/editor_input.js $(HARNESS))
C2       := $(B)/c2.$(call BCONF,$(B)/fontcpu,tests/csscpu_pages.js $(HARNESS)).log
CSSCPU   := machine/gen_css.py machine/csssim.py machine/cssref.py

.PHONY: help all lib image page dist test test-browser test-ui test-ui-smoke test-all \
        expect l1 l2 l2-generic l3 l5 l5-smoke l5-input c1 c2 fuzz fuzz-quick fuzz-l3 clean

help:
	@echo "make page           build/js_in_css.xhtml (lib -> image -> page: editor, compile chain, CSS CPU; ~40 s)"
	@echo "make test           fast levels, no browser: Node oracle, L1 reference, quick fuzz, L2 DSL, C1 CPU model (~10 s)"
	@echo "make fuzz           differential tests against Node on thousands of programs, L1 + L2 + C1 (~1.5 min)"
	@echo "make test-browser   L3: the generated CSS compiler in Chrome vs the reference (~40 s)"
	@echo "make fuzz-l3        L3 on 300 generated and mutated programs (~2 min)"
	@echo "make test-ui-smoke  L5 on a few programs: the real page, typed like a user (~30 s)"
	@echo "make test-ui        L5 on every quick program (~5.5 min)"
	@echo "make c2             a CPU-only page per quick program runs to HALT (~30 s)"
	@echo "make dist           copy the built page to dist/"

all: page

# ---- runtime library -> ROM (jsc.js, the self-hosted subset compiler, compiles lib_src.js under Node)
lib: $(CC)/lib.json
$(CC)/lib.json: $(CC)/lib_src.js $(CC)/libbuild.js $(CC)/jsc.js $(CC)/layout.json $(CC)/rtlib.py machine/uarch.py
	$(PY) $(CC)/rtlib.py $@

# ---- image (ROM = lib) -> page (editor + readback + CSS compiler + CSS CPU; machine/gen_css.py)
image: $(B)/ccimg.json
$(B)/ccimg.json: $(CC)/lib.json $(CC)/cc_ref.py $(CC)/mkimage.py tests/fizz.js
	@mkdir -p $(B)
	$(PY) $(CC)/mkimage.py tests/fizz.js $@

page: $(B)/js_in_css.xhtml
$(B)/js_in_css.xhtml: $(B)/ccimg.json machine/gen_css.py machine/memtree.py machine/uipage.py machine/uarch.py $(wildcard $(CC)/*.py readback/*.py) $(SHARED)/py/csslabel.py
	UI=1 $(PY) machine/gen_css.py $(B)/ccimg.json $@

dist: page
	cp $(B)/js_in_css.xhtml dist/js_in_css.xhtml

# ---- tests (see docs/ARCHITECTURE.md#5-tests)
expect:                                   # Node is the oracle: writes tests/suite/*.out
	$(NODE) tests/suite_expect.js tests/suite
l1: lib                                   # reference compiler + 20-bit simulator vs Node
	$(PY) tests/suite_ref.py
l2: $(L2)                                 # DSL (page's specialised variants) vs reference, level by level
	$(call report,$<,3)
$(L2): tests/cmp_dsl.py tests/par.py $(PYSRC) $(SUITE) $(RERUN_IF)
	SPEC=1 SPECK=$(SPECK) $(LOGGED) $@ -t 3 -p '^ALL OK' -- $(PY) tests/cmp_dsl.py tests/suite/*.js tests/suite_err/*.js
l2-generic:                               # same, unspecialised parser (slower)
	$(PY) tests/cmp_dsl.py tests/suite/*.js tests/suite_err/*.js | tail -3
c1: lib                                   # the CSS CPU's design (machine/csssim.py) runs every compiled image vs Node
	$(PY) tests/csscpu_sim.py
# C2: a CPU-only page per program (machine/gen_css.py) runs to HALT in Chrome; console vs Node, steps vs cc_ref
$(B)/c2/list.txt: tests/csscpu_pages.py tests/csscpu_sim.py $(CSSCPU) $(PYSRC) $(SUITE)
	$(PY) tests/csscpu_pages.py $(B)/c2
c2: $(C2)
	$(call report,$<,3)
$(C2): $(B)/c2/list.txt tests/csscpu_pages.js $(HARNESS) $(RERUN_IF)
	SHARDS=$(SHARDS) $(LOGGED) $@ -t 3 -p '^([0-9]+)/\1 pass$$' -- $(NODE) tests/csscpu_pages.js $(B)/c2
# differential tests against Node without a browser (tests/fuzz/fuzz.py): the suite reformatted, generated programs,
# one-token mutations. fuzz-quick is part of `make test`; fuzz is the full run (L2 and C1 too, ~1.5 min)
fuzz-quick: lib
	$(PY) tests/fuzz/fuzz.py fmt && $(PY) tests/fuzz/fuzz.py gen -n 500 && $(PY) tests/fuzz/fuzz.py mut -n 1000
fuzz: $(FUZZ)
	$(call report,$<,6)
$(FUZZ): tests/fuzz/fuzz.py tests/fuzz/progen.py tests/fuzz/oracle.js tests/fuzz/all.sh tests/cmp_dsl.py tests/par.py $(PYSRC) $(SUITE) $(RERUN_IF)
	$(LOGGED) $@ -p '^ALL OK' -- sh tests/fuzz/all.sh
$(B)/suite_css.xhtml: $(wildcard $(CC)/*.py) $(CC)/lib.json tests/suite_css.py
	REBUILD=1 $(PY) tests/suite_css.py $@ > /dev/null
$(B)/suite_css.xhtml.exp.json: $(B)/suite_css.xhtml tests/suite_css.py $(PYSRC) $(SUITE)   # cc_ref's words for each test
	$(PY) tests/suite_css.py $(B)/suite_css.xhtml > /dev/null
# L3 on programs from the fuzzers that fit the editor (the same page; tests/fuzz/fuzz.py dump writes them)
FUZZL3 := $(B)/fuzz-l3.$(call BCONF,$(B)/fontcpu,tests/suite_css.js $(HARNESS)).log
fuzz-l3: $(FUZZL3)
	$(call report,$<,3)
$(FUZZL3): $(B)/suite_css.xhtml tests/suite_css.py tests/suite_css.js tests/fuzz/fuzz.py tests/fuzz/progen.py $(PYSRC) $(HARNESS) $(RERUN_IF)
	$(PY) tests/fuzz/fuzz.py dump -n $(or $(N),150) --dir $(B)/fuzz-l3 && ln -sf suite_css.xhtml $(B)/fuzz-l3.xhtml && \
	  $(PY) tests/suite_css.py $(B)/fuzz-l3.xhtml $(B)/fuzz-l3 > /dev/null
	SHARDS=$(SHARDS) $(LOGGED) $@ -t 3 -p '^([0-9]+)/\1 pass$$' -- $(NODE) tests/suite_css.js $(B)/fuzz-l3.xhtml
l3: $(L3)                                 # generated CSS compiler in Chrome vs reference, word for word
	$(call report,$<,25)
$(L3): $(B)/suite_css.xhtml $(B)/suite_css.xhtml.exp.json tests/suite_css.js $(HARNESS) $(RERUN_IF)
	SHARDS=$(SHARDS) $(LOGGED) $@ -t 25 -p '^([0-9]+)/\1 pass$$' -- $(NODE) tests/suite_css.js $(B)/suite_css.xhtml
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
	SHARDS=$(SHARDS) EXP1=$(B)/ui_exp/fizzbuzz.grid $(LOGGED) $@ $(UIOK) -- $(NODE) machine/ui_seq.js $(B)/js_in_css.xhtml $$(cat $<)
l5-smoke: $(B)/l5-smoke.$(UICONF).log
	$(call report,$<,4)
$(B)/l5-smoke.$(UICONF).log: $(B)/ui_exp/args-400-6.txt $(UI)
	SHARDS=$(SHARDS) EXP1=$(B)/ui_exp/fizzbuzz.grid $(LOGGED) $@ $(UIOK) -- $(NODE) machine/ui_seq.js $(B)/js_in_css.xhtml $$(cat $<)
l5-input: $(B)/l5-input.$(UICONF).log     # the editor under user input: what the scan reads is what the editor shows
	$(call report,$<,2)
$(B)/l5-input.$(UICONF).log: $(B)/ui_exp/args-400-0.txt tests/editor_input.js $(UI)
	SHARDS=$(SHARDS) EXP=$(B)/ui_exp/fizzbuzz.grid $(LOGGED) $@ -- $(NODE) tests/editor_input.js $(B)/js_in_css.xhtml

test: expect l1 fuzz-quick l2 c1
test-browser: l3
test-ui: l5
test-ui-smoke: l5-smoke
test-all: test l3 l5

clean:
	rm -rf $(B)
