# Minimal Python sandbox image for VibeCoder.
# Build: docker build -t vibecoder-sandbox sandbox/
#
# Security measures:
#   - Runs as non-root user
#   - No network access (enforced by `docker run --network none`)
#   - Read-only root filesystem
#   - Memory and CPU limits (enforced at runtime)
#   - No package installer — only stdlib is available

FROM python:3.12-slim

# Remove pip/setuptools to prevent installs inside the sandbox
RUN pip uninstall -y pip setuptools wheel 2>/dev/null; \
    rm -rf /usr/local/lib/python3.12/ensurepip

# Create non-root user
RUN useradd -m -s /bin/bash sandbox
USER sandbox

WORKDIR /workspace
