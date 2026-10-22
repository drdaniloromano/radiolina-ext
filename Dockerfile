# SPDX-License-Identifier: MIT
FROM registry.fedoraproject.org/fedora:43
RUN dnf -y upgrade --refresh && \
    dnf -y install gjs gstreamer1 gstreamer1-plugins-base gstreamer1-plugins-good \
    python3 python3-gobject dbus-daemon make openssl && dnf clean all
ARG TEST_UID=1000
ARG TEST_GID=1000
COPY scripts/container-identity.py /tmp/radiolina-container-identity.py
RUN python3 /tmp/radiolina-container-identity.py "$TEST_UID" "$TEST_GID" && \
    rm /tmp/radiolina-container-identity.py
WORKDIR /project
ENV GIO_USE_VFS=local
ENV PYTHONDONTWRITEBYTECODE=1
CMD ["python3", "scripts/test.py"]
