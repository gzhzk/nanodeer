# NanoDeer Sandbox Image
# Minimal, secure, ephemeral container for AI Agent tool execution.

FROM ubuntu:24.04

LABEL maintainer="NanoDeer"
LABEL description="NanoDeer AI Agent Sandbox - Ephemeral execution environment"
LABEL version="1.0"

# Install essential tools
RUN apt-get update && apt-get install -y \
    python3 python3-pip git jq curl bash vim \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

RUN rm -rf /var/cache/* /tmp/*

RUN useradd -m -s /bin/bash agent && \
    chown -R agent:agent /workspace

USER agent

# Keep container alive; actual tool execution via docker exec
CMD ["sleep", "infinity"]