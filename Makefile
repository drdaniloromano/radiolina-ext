# SPDX-License-Identifier: MIT
.PHONY: build test test-shell test-resources security-check container-build container-refresh container-test container-resources container-security-check container-package container-shell-build container-shell-refresh container-shell-test container-aac-build container-aac-test

CONTAINER_ENGINE ?= podman
IMAGE ?= localhost/gnome-radio-dev:43
OOM_SCORE_ADJ ?= 500
SHELL_VERSIONS ?= 49 50
SHELL_IMAGE_PREFIX ?= localhost/radiolina-shell-test
SHELL_SCALE ?= 1
SHELL_THEME ?= dark
AAC_IMAGE ?= localhost/radiolina-aac-test:44
AAC_BASE_IMAGE ?= localhost/radiolina-shell-test:50
REQUIRE_AAC ?= 0
# Mount only build/test inputs, never the private workspace or repository metadata.
CONTAINER_SOURCES = $(foreach path,extension src scripts tests LICENSE,-v "$(CURDIR)/$(path):/project/$(path):ro")
CONTAINER_RUN_FLAGS = --rm --network=none --security-opt label=disable

build:
	python3 scripts/build.py --oom-score-adj "$(OOM_SCORE_ADJ)"

test:
	python3 scripts/test.py

test-resources:
	python3 scripts/test-resources.py

security-check:
	python3 scripts/security-check.py --environment desktop --output workspace/security-desktop.json

test-shell: build
	python3 scripts/test-shell.py

container-shell-build:
	python3 scripts/container-shell.py build --engine "$(CONTAINER_ENGINE)" \
	    --gnome $(SHELL_VERSIONS) --image-prefix "$(SHELL_IMAGE_PREFIX)"

container-shell-refresh:
	python3 scripts/container-shell.py build --refresh --engine "$(CONTAINER_ENGINE)" \
	    --gnome $(SHELL_VERSIONS) --image-prefix "$(SHELL_IMAGE_PREFIX)"

container-shell-test:
	python3 scripts/container-shell.py test --engine "$(CONTAINER_ENGINE)" \
	    --gnome $(SHELL_VERSIONS) --image-prefix "$(SHELL_IMAGE_PREFIX)" \
	    --scale "$(SHELL_SCALE)" --theme "$(SHELL_THEME)"

container-build:
	$(CONTAINER_ENGINE) build -t $(IMAGE) -f Dockerfile .

# Explicit refresh for security/release checks; ordinary builds may reuse cache.
container-refresh:
	@set -eu; version=$$($(CONTAINER_ENGINE) --version); \
	case "$$version" in \
	    podman\ *) pull=--pull=always ;; \
	    Docker\ *) pull=--pull ;; \
	    *) printf '%s\n' 'Unsupported container engine: choose Podman or Docker.' >&2; exit 1 ;; \
	esac; \
	$(CONTAINER_ENGINE) build $$pull --no-cache -t $(IMAGE) -f Dockerfile .

container-test:
	@set -eu; user_flags=$$(sh scripts/container-user-flags.sh $(CONTAINER_ENGINE)); \
	$(CONTAINER_ENGINE) run $(CONTAINER_RUN_FLAGS) $$user_flags \
	--env GNOME_RADIO_TEST_REQUIRE_AAC=$(REQUIRE_AAC) $(CONTAINER_SOURCES) $(IMAGE)

# The optional image inherits an already-built GNOME 50/Fedora 44 test image.
container-aac-build:
	$(CONTAINER_ENGINE) build --build-arg BASE_IMAGE="$(AAC_BASE_IMAGE)" \
	-t $(AAC_IMAGE) -f Dockerfile.aac .

container-aac-test:
	$(MAKE) container-test IMAGE="$(AAC_IMAGE)" REQUIRE_AAC=1

container-resources:
	@set -eu; user_flags=$$(sh scripts/container-user-flags.sh $(CONTAINER_ENGINE)); \
	$(CONTAINER_ENGINE) run $(CONTAINER_RUN_FLAGS) $$user_flags $(CONTAINER_SOURCES) \
	$(IMAGE) python3 scripts/test-resources.py

# This opt-in query needs repository network access; ordinary tests stay offline.
# JSON goes to stdout, diagnostics to stderr. No private output mount is exposed.
container-security-check:
	@set -eu; user_flags=$$(sh scripts/container-user-flags.sh $(CONTAINER_ENGINE)); \
	image_id=$$($(CONTAINER_ENGINE) image inspect --format '{{.Id}}' $(IMAGE)); \
	$(CONTAINER_ENGINE) run $(filter-out --network=none,$(CONTAINER_RUN_FLAGS)) \
	$$user_flags $(CONTAINER_SOURCES) $(IMAGE) python3 scripts/security-check.py \
	--environment container --image-id "$$image_id"

container-package:
	@set -eu; user_flags=$$(sh scripts/container-user-flags.sh $(CONTAINER_ENGINE)); \
	mkdir -p build; \
	$(CONTAINER_ENGINE) run $(CONTAINER_RUN_FLAGS) $$user_flags $(CONTAINER_SOURCES) \
	-v "$(CURDIR)/build:/project/build" $(IMAGE) python3 scripts/build.py --oom-score-adj "$(OOM_SCORE_ADJ)"
