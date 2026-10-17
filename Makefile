# Checks shared by the projects. Each project has its own tests too: css-physics `bash tools/smoke.sh 16`,
# js-minus-js `make test`, paint `make test` (see their CLAUDE.md / AGENTS.md).
.PHONY: help test-shared engine-check engine-costs

help:
	@echo "make test-shared    unit tests of shared/ (no browser, ~1 s)"
	@echo "make engine-check   the Chrome behaviours css-physics and js-minus-js depend on, both browser profiles (~20 s)"
	@echo "make engine-costs   re-measure the style-engine cost table against the docs (~2 min; no other browser jobs)"

test-shared:
	node shared/test/test.js
	python3 shared/test/test_py.py

engine-check:
	node engine/check.js

engine-costs:
	node engine/costs.js
