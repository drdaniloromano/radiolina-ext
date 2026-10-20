# SPDX-License-Identifier: MIT
FROM registry.fedoraproject.org/fedora:43
RUN dnf -y install gjs gstreamer1 gstreamer1-plugins-base gstreamer1-plugins-good \
    python3 python3-gobject dbus-daemon make && dnf clean all
WORKDIR /project
ENV GIO_USE_VFS=local
ENV PYTHONDONTWRITEBYTECODE=1
CMD ["python3", "scripts/test.py"]
