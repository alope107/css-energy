.PHONY: help serve build selftest-site test test-selftest test-e2e

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

test-selftest:
	node tools/selftest.js

test-e2e:
	node tools/e2e.js
