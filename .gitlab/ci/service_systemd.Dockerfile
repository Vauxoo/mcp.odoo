# A Debian image whose PID 1 is systemd, so `odoo-mcp service` runs against a
# real user manager. Needs a privileged container:
#
#   docker build -f .gitlab/ci/service_systemd.Dockerfile -t odoo-mcp-systemd .
#   docker run -d --name odoo-mcp-systemd --privileged --cgroupns=host \
#     -v /sys/fs/cgroup:/sys/fs/cgroup:rw -v "$PWD":/src:ro odoo-mcp-systemd
#   docker exec odoo-mcp-systemd bash /src/.gitlab/ci/service_systemd.sh
ARG PYTHON=3.12
FROM python:${PYTHON}-slim-bookworm
RUN apt-get update \
    && apt-get install -y --no-install-recommends systemd systemd-sysv dbus dbus-user-session procps \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash tester
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
