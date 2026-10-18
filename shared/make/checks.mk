# checks.mk — a check's pass as a make target, so make skips a check while nothing it depends on has changed.
# Included by the projects' Makefiles (shared/README.md#checks-in-make). A check is a rule whose target is its log:
#
#   FONTCPU := $(call id,$(B)/fontcpu,fontcpu,tests/suite_css.js $(HARNESS))
#   L3 := $(B)/l3.$(FONTCPU).log
#   $(L3): <every file it reads> $(RERUN_IF)
#   	$(LOGGED) $@ -p '^([0-9]+)/\1 pass$$' -- node tests/suite_css.js page.xhtml
#   l3: $(L3)
#   	$(call report,$<,25)
#
# logged.sh writes the log only on a pass, so make re-runs a check when it failed last time or when any prerequisite
# is newer than its last pass. What lives outside the repo (Node, Python, Playwright, the browser and its version, the
# environment variables the scripts read, found in their source by runid.js) goes into the log's name as a hash:
# another browser or a variable set is another target, so a pass under one configuration never stands for another,
# and switching back finds the old pass. <dir>/<name>.<hash>.id holds what a hash stands for.
#
# RERUN=1 runs every check asked for, up to date or not: the real run before a merge.
SHARED  := $(patsubst %/make/,%,$(dir $(lastword $(MAKEFILE_LIST))))
LOGGED  := $(SHARED)/make/logged.sh
RERUN_IF := $(if $(RERUN),FORCE)
CHECKS_START := $(shell date +%s%N)

# $(call id,dir/name,profile|-,script... VAR...): the hash of runid.js's output (writing dir/name.<hash>.id the first
# time). Use it with := (once per make, ~50 ms). Runs as make reads the Makefile, so make -n and -q agree with make.
# $(shell) doesn't see variables set on make's command line (`make l3 CHROME=…`), which recipes do: MAKEOVERRIDES
# passes them.
id = $(or $(shell mkdir -p $(dir $(1)) && t=$$(env $(MAKEOVERRIDES) node $(SHARED)/js/runid.js $(2) $(3)) && \
  h=$$(printf '%s\n' "$$t" | sha1sum | cut -c1-10) && { [ -f $(1).$$h.id ] || printf '%s\n' "$$t" > $(1).$$h.id; } && echo $$h),\
  $(error runid.js failed for $(1)))

# $(call report,logs,lines): for each check make found up to date (its log is older than this make), say so and show
# the last lines of the pass it stands for
report = @$(SHARED)/make/report.sh $(CHECKS_START) $(2) $(1)

.PHONY: FORCE
FORCE:
