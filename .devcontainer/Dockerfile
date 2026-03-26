FROM debian:bookworm-slim AS main

# Install system packages required for local development and publishing
RUN apt-get update && \
    apt-get install -y wget git-all ffmpeg build-essential libopengl0 libsm6 libegl1 curl ca-certificates nano && \
    rm -rf /var/lib/apt/lists/*

# Install Quarto
RUN wget https://github.com/quarto-dev/quarto-cli/releases/download/v1.6.39/quarto-1.6.39-linux-amd64.deb && \
    dpkg -i quarto-1.6.39-linux-amd64.deb && \
    rm quarto-1.6.39-linux-amd64.deb

# Install uv
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin:$PATH"

# Create and set working directory
WORKDIR /workspaces/pyllments

# Create virtual environment in container-local directory
RUN mkdir -p /opt/venv && uv venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Set UV link mode to avoid hardlink warning (Fix for second warning)
ENV UV_LINK_MODE=copy

# Install locked dependencies without the project source. The workspace mount
# will provide the package code later, and `postCreateCommand` will sync it.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock,readonly \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml,readonly \
    uv sync --active --frozen --no-install-project --extra full --extra dev