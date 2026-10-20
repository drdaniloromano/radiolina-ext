# SPDX-License-Identifier: MIT
.PHONY: build test test-shell container-build container-test container-package

CONTAINER_ENGINE ?= podman
IMAGE ?= localhost/gnome-radio-dev:43
OOM_SCORE_ADJ ?= 500
# Mount only build/test inputs, never the private workspace or repository metadata.
CONTAINER_SOURCES = $(foreach path,extension src scripts tests LICENSE,-v "$(CURDIR)/$(path):/project/$(path):ro")
CONTAINER_RUN_FLAGS = --rm --network=none --security-opt label=disable

build:
	python3 scripts/build.py --oom-score-adj "$(OOM_SCORE_ADJ)"

test:
	python3 scripts/test.py

test-shell: build
	python3 scripts/test-shell.py

container-build:
	$(CONTAINER_ENGINE) build -t $(IMAGE) -f Dockerfile .

container-test:
	@set -eu; user_flags=$$(sh scripts/container-user-flags.sh $(CONTAINER_ENGINE)); \
	$(CONTAINER_ENGINE) run $(CONTAINER_RUN_FLAGS) $$user_flags $(CONTAINER_SOURCES) $(IMAGE)

container-package:
	@set -eu; user_flags=$$(sh scripts/container-user-flags.sh $(CONTAINER_ENGINE)); \
	mkdir -p build; \
	$(CONTAINER_ENGINE) run $(CONTAINER_RUN_FLAGS) $$user_flags $(CONTAINER_SOURCES) \
	-v "$(CURDIR)/build:/project/build" $(IMAGE) python3 scripts/build.py --oom-score-adj "$(OOM_SCORE_ADJ)"
