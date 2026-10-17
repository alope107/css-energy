# The builds and checks of tools/smoke.sh, which runs `make -k smoke N=<count>` (its header lists the checks).
# A check is the file out/smoke_<N>.<gen>_…<check>.<browser>.<config>.log, written only when it passes
# (../shared/make/checks.mk): make re-runs it only when its page or its harness changed since its last pass, or with
# RERUN=1. <gen> and <config> are hashes of the Python, browser and environment variables the generator and the
# checks run with (out/gen.<gen>.id, out/<browser>.<config>.id), so each configuration has its own pages and passes.
include ../shared/make/checks.mk
.PHONY: smoke statcheck
.SECONDARY:
N  ?= 16
MS ?= 12000
O  := out
BR := $(if $(filter firefox,$(BROWSER)),firefox,chromium)
SCENES  := tower rain stack
JS      := $(wildcard tools/lib/*.js $(SHARED)/js/*.js)
# what the pages and checks depend on outside the repo, and the environment variables their scripts read
P  := $(O)/smoke_$(N).$(call id,$(O)/gen,-,$(wildcard src/*.py))
C  := $(BR).$(call id,$(O)/$(BR),$(if $(filter firefox,$(BR)),firefox,physics),tools/smoke.js tools/floatcheck.js tools/overlaycheck.js tools/grabtest.js $(JS))
HARNESS := $(JS) $(RERUN_IF)

$(P)_%.html: $(wildcard src/*)
	SCENE=$* COUNTS=$(N) PLAIN=1 python3 src/build3d.py $@ 2>/dev/null
# (a spread-out field with no gravity, shaken awake: other bodies drift freely, so a leaked grab force shows)
$(P)_field.html: $(wildcard src/*)
	SCENE=field FIELD_GAP=30 COUNTS=$(N) PLAIN=1 python3 src/build3d.py $@ 2>/dev/null

$(P)_%.smoke-$(MS).$(C).log: $(P)_%.html tools/smoke.js $(HARNESS)
	@$(LOGGED) $@ -- node tools/smoke.js $< $(MS)
$(P).float.$(C).log: $(P)_tower.html $(P)_rain.html tools/floatcheck.js $(HARNESS)
	@$(LOGGED) $@ -- node tools/floatcheck.js $(P)_tower.html $(P)_rain.html
$(P).overlay.$(C).log: $(P)_tower.html tools/overlaycheck.js $(HARNESS)
	@$(LOGGED) $@ -- node tools/overlaycheck.js $<
$(P).grab.$(C).log: $(P)_field.html tools/grabtest.js $(HARNESS)
	@$(LOGGED) $@ -- node tools/grabtest.js $<
statcheck: $(SCENES:%=$(P)_%.html)                # static and quick: always runs
	@rc=0; for f in $^; do python3 tools/statcheck.py $$f || rc=1; done; exit $$rc

CHECKS := $(SCENES:%=$(P)_%.smoke-$(MS).$(C).log) $(P).float.$(C).log $(P).overlay.$(C).log $(P).grab.$(C).log
smoke: $(CHECKS) statcheck
	$(call report,$(CHECKS),20)
