# Checks shared by the projects. Each project has its own tests too: css-physics `bash tools/smoke.sh 16`,
# js-minus-js `make test`, paint `make test` (see their CLAUDE.md / AGENTS.md).
.PHONY: help test-shared engine-check engine-costs
# engine-check is the file engine/build/check.<config>.log, written only when it passes (shared/make/checks.mk): make re-runs
# it only when the probes, the shared harness or either browser changed since its last pass, or with RERUN=1.
include shared/make/checks.mk
EB := engine/build
ENGINE := $(EB)/check.$(subst $() ,-,$(foreach p,physics fontcpu,$(call id,$(EB)/$(p),$(p),engine/check.js $(wildcard shared/js/*.js)))).log

help:
	@echo "make test-shared    unit tests of shared/ (no browser, ~2 s)"
	@echo "make engine-check   the Chrome behaviours css-physics and js-minus-js depend on, both browser profiles (~20 s)"
	@echo "make engine-costs   re-measure the style-engine cost table against the docs (~2 min; no other browser jobs)"

test-shared:
	node shared/test/test.js
	python3 shared/test/test_py.py
	python3 shared/test/test_checks.py

engine-check: $(ENGINE)
	$(call report,$<,1)
$(ENGINE): engine/check.js $(wildcard shared/js/*.js) $(RERUN_IF)
	@$(LOGGED) $@ -- node engine/check.js

engine-costs:
	node engine/costs.js
