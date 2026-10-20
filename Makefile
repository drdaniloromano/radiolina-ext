.PHONY: build test test-shell container-build container-test container-package

CONTAINER_ENGINE ?= podman
IMAGE ?= localhost/gnome-radio-dev:43

build:
	python3 scripts/build.py

test:
	python3 scripts/test.py

test-shell: build
	python3 scripts/test-shell.py

container-build:
	$(CONTAINER_ENGINE) build -t $(IMAGE) -f Containerfile .

container-test:
	$(CONTAINER_ENGINE) run --rm --network=none --userns=keep-id --security-opt label=disable -e PYTHONDONTWRITEBYTECODE=1 -v "$(CURDIR):/project:ro" $(IMAGE)

container-package:
	$(CONTAINER_ENGINE) run --rm --network=none --userns=keep-id --security-opt label=disable -v "$(CURDIR):/project" $(IMAGE) python3 scripts/build.py
