#!/bin/sh
# SPDX-License-Identifier: MIT
# Print numeric identity flags; never chown or relabel the host checkout.
set -eu

version=$("$@" --version)
case "$version" in
    podman\ *)
        # Also covers distributions whose docker command wraps Podman.
        printf '%s\n' '--userns=keep-id'
        ;;
    Docker\ *)
        # Fail before mounting anything if daemon identity cannot be established.
        security=$("$@" info --format '{{json .SecurityOptions}}')
        case "$security" in
            *rootless*)
                # Rootless Docker maps container root to the daemon's host user.
                printf '%s\n' '--user=0:0'
                ;;
            *)
                # Disable daemon userns-remap for this unprivileged UID/GID only.
                printf '%s\n' "--userns=host --user=$(id -u):$(id -g)"
                ;;
        esac
        ;;
    *)
        printf '%s\n' 'Unsupported container engine: choose Podman or Docker.' >&2
        exit 1
        ;;
esac
