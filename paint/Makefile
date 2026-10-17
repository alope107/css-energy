.PHONY: help serve build selftest-site test test-selftest test-e2e
# A test is the file build/<name>.<config>.log, written only when it passes (../shared/make/checks.mk): make re-runs it only
# when the site it serves, the tools, the browser or a variable they read changed since its last pass, or with RERUN=1.
include ../shared/make/checks.mk
B  := build
JS := tools/lib.js serve.js $(wildcard $(SHARED)/js/*.js)
# what the tests depend on outside the repo, and the environment variables their scripts read (build/physics.<config>.id)
C  := $(call id,$(B)/physics,physics,tools/selftest.js tools/e2e.js $(JS))

help:
	@echo "make serve          the site on http://localhost:8080/ (node serve.js site)"
	@echo "make build          rebuild site/ (python3 build.py; keeps site/d/*.png)"
	@echo "make selftest-site  rebuild selftest/site/"
	@echo "make test           test-selftest, then test-e2e (~7 min)"
	@echo "make test-selftest  the self-test page against simulated host faults (~1 min)"
	@echo "make test-e2e       the canvas end to end with real clicks (~6 min)"

serve:
	node serve.js site

build:
	python3 build.py

selftest-site:
	python3 selftest/build.py

test: test-selftest test-e2e

test-selftest: $(B)/selftest.$(C).log
	$(call report,$<,5)
$(B)/selftest.$(C).log: tools/selftest.js $(JS) $(shell find selftest/site) $(RERUN_IF)
	@$(LOGGED) $@ -- node tools/selftest.js

test-e2e: $(B)/e2e.$(C).log
	$(call report,$<,13)
$(B)/e2e.$(C).log: tools/e2e.js $(JS) $(shell find site) $(RERUN_IF)
	@$(LOGGED) $@ -- node tools/e2e.js
