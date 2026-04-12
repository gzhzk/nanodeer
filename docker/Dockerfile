# NanoDeer Sandbox Image
# Minimal, ephemeral container for AI Agent tool execution.
# Security: read-only rootfs, no network, tmpfs for /tmp (configured at runtime)

FROM python:3.11-slim

LABEL maintainer="NanoDeer"
LABEL description="NanoDeer AI Agent Sandbox - Ephemeral execution environment"
LABEL version="1.3"

# Install essential system tools
RUN apt-get update && apt-get install -y \
    git \
    jq \
    curl \
    bash \
    findutils \
    coreutils \
    && rm -rf /var/lib/apt/lists/*

# Install Python libraries for data analysis, web scraping, and code quality
RUN pip install --no-cache-dir --break-system-packages \
    numpy \
    pandas \
    openpyxl \
    xlrd \
    matplotlib \
    beautifulsoup4 \
    requests \
    lxml \
    pylint \
    black \
    mypy \
    isort

WORKDIR /workspace

RUN rm -rf /var/cache/* /tmp/*

RUN useradd -m -s /bin/bash agent && \
    chown -R agent:agent /workspace

USER agent

# Keep container alive; actual tool execution via docker exec
CMD ["sleep", "infinity"]
