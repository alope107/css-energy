# The builds and checks of tools/smoke.sh, which runs `make -k smoke N=<count>` (its header lists the checks).
# A check is the file out/smoke_<N>.<gen>_…<check>.<browser>.<config>.log, written only when it passes
# (../shared/make/checks.mk): make re-runs it only when its page or its harness changed since its last pass, or with
# RERUN=1. <gen> and <config> are hashes of the Python, browser and environment variables the generator and the
# checks run with (out/gen.<gen>.id, out/<browser>.<config>.id), so each configuration has its own pages and passes.
# BROWSER=firefox|webkit: that browser (Playwright's), and xcheck.js against Chromium. NOIF=1: the checks run on
# copies of the pages with if( renamed iff(, as a browser without if() sees them (Firefox; Safari before 27.x).
include ../shared/make/checks.mk
.PHONY: smoke statcheck
.SECONDARY:
N  ?= 16
MS ?= 12000
O  := out
BR := $(or $(filter firefox webkit,$(BROWSER)),chromium)
V  := $(if $(NOIF),.noif)
SCENES  := tower rain stack
JS      := $(wildcard tools/lib/*.js $(SHARED)/js/*.js)
# what the pages and checks depend on outside the repo, and the environment variables their scripts read
P  := $(O)/smoke_$(N).$(call id,$(O)/gen,-,$(wildcard src/*.py))
C  := $(BR).$(call id,$(O)/$(BR),$(if $(filter chromium,$(BR)),physics,$(BR)),tools/smoke.js tools/floatcheck.js tools/overlaycheck.js tools/grabtest.js tools/touchcheck.js tools/xcheck.js $(JS))
HARNESS := $(JS) $(RERUN_IF)

$(P)_%.html: $(wildcard src/*) $(SHARED)/py/csslabel.py
	SCENE=$* COUNTS=$(N) PLAIN=1 python3 src/build3d.py $@ 2>/dev/null
# (a spread-out field with no gravity, shaken awake: other bodies drift freely, so a leaked grab force shows)
$(P)_field.html: $(wildcard src/*) $(SHARED)/py/csslabel.py
	SCENE=field FIELD_GAP=30 COUNTS=$(N) PLAIN=1 python3 src/build3d.py $@ 2>/dev/null

# (NOIF=1: the page as a browser without if() reads it; xcheck.js checks the fallback that takes over)
$(P)_%.noif.html: $(P)_%.html
	sed 's/if(/iff(/g' $< > $@

$(P)_%$(V).smoke-$(MS).$(C).log: $(P)_%$(V).html tools/smoke.js $(HARNESS)
	@$(LOGGED) $@ -- node tools/smoke.js $< $(MS)
$(P)$(V).float.$(C).log: $(P)_tower$(V).html $(P)_rain$(V).html tools/floatcheck.js $(HARNESS)
	@$(LOGGED) $@ -- node tools/floatcheck.js $(P)_tower$(V).html $(P)_rain$(V).html
$(P)$(V).overlay.$(C).log: $(P)_tower$(V).html tools/overlaycheck.js $(HARNESS)
	@$(LOGGED) $@ -- node tools/overlaycheck.js $<
$(P)$(V).grab.$(C).log: $(P)_field$(V).html tools/grabtest.js $(HARNESS)
	@$(LOGGED) $@ -- node tools/grabtest.js $<
# (touch gestures go through Chromium's gesture recognizer over CDP: Chromium only)
$(P).touch.$(C).log: $(P)_tower.html tools/touchcheck.js $(HARNESS)
	@$(LOGGED) $@ -- node tools/touchcheck.js $<
# (other browsers: every value on every level against Chromium's, on a state this browser reached, with and without
# if(); static, so not real time. Its registers read back a hair off, unlike Chromium's: the sleep tests' margins)
$(P).xcheck.$(C).log: $(P)_tower.html tools/xcheck.js $(HARNESS)
	@$(LOGGED) $@ -- env XFROM=$(BR) node tools/xcheck.js $< 3000 $(BR) $(BR):noif
statcheck: $(SCENES:%=$(P)_%.html)                # static and quick: always runs
	@rc=0; for f in $^; do python3 tools/statcheck.py $$f || rc=1; done; exit $$rc

CHECKS := $(SCENES:%=$(P)_%$(V).smoke-$(MS).$(C).log) $(P)$(V).float.$(C).log $(P)$(V).overlay.$(C).log $(P)$(V).grab.$(C).log \
          $(if $(filter chromium,$(BR)),$(if $(V),,$(P).touch.$(C).log),$(P).xcheck.$(C).log)
smoke: $(CHECKS) statcheck
	$(call report,$(CHECKS),20)
