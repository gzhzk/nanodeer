# NanoDeer Sandbox Image
# Minimal, ephemeral container for AI Agent tool execution.
# Security: read-only rootfs, no network, tmpfs for /tmp (configured at runtime)

FROM python:3.11-slim

LABEL maintainer="NanoDeer"
LABEL description="NanoDeer AI Agent Sandbox - Ephemeral execution environment"
LABEL version="1.0"

# Build args (defaults: Tsinghua mirror for China users)
ARG APT_MIRROR=mirrors.tuna.tsinghua.edu.cn
ARG PIP_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple

# APT sources
RUN sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources && \
    apt-get update && apt-get install -y \
    git jq curl bash findutils coreutils \
    && rm -rf /var/lib/apt/lists/*

# Pip packages
RUN pip install --no-cache-dir --break-system-packages \
    -i ${PIP_MIRROR} \
    numpy pandas openpyxl xlrd matplotlib beautifulsoup4 requests lxml \
    pylint black mypy isort

WORKDIR /workspace

RUN rm -rf /var/cache/* /tmp/*

RUN useradd -m -s /bin/bash agent && \
    chown -R agent:agent /workspace

USER agent

# Keep container alive; actual tool execution via docker exec
CMD ["sleep", "infinity"]
