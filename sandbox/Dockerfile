# NanoDeer Sandbox Image
# Minimal, ephemeral container for AI Agent tool execution.
# Network is enabled by default; control via network_mode in config.

FROM ubuntu:24.04

LABEL maintainer="NanoDeer"
LABEL description="NanoDeer AI Agent Sandbox - Ephemeral execution environment"
LABEL version="1.2"

# Install essential tools + Python data/web/scrape libs + code quality tools
RUN apt-get update && apt-get install -y \
    python3 python3-pip git jq curl bash vim \
    && rm -rf /var/lib/apt/lists/*

# Python packages for data analysis, web scraping, and code quality
RUN pip3 install --no-cache-dir --break-system-packages \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
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
    isort \
    && rm -rf /var/lib/cache/*

WORKDIR /workspace

RUN rm -rf /var/cache/* /tmp/*

RUN useradd -m -s /bin/bash agent && \
    chown -R agent:agent /workspace

USER agent

# Keep container alive; actual tool execution via docker exec
CMD ["sleep", "infinity"]