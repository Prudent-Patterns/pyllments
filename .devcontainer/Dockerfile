FROM --platform=linux/amd64 debian:bookworm-slim AS main

# Update and upgrade system packages, install all required dependencies in one layer
RUN apt-get -y update && \
    apt-get -y upgrade && \
    apt-get -y install wget git-all ffmpeg build-essential libopengl0 libsm6 libegl1 curl ca-certificates nano && \
    apt-get clean

# Install Quarto
RUN wget https://github.com/quarto-dev/quarto-cli/releases/download/v1.6.39/quarto-1.6.39-linux-amd64.deb && \
    dpkg -i quarto-1.6.39-linux-amd64.deb && \
    rm quarto-1.6.39-linux-amd64.deb

# Install UV
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin/:$PATH"

# RUN uv venv

# Create and set working directory
WORKDIR /workspaces/pyllments

# Create virtual environment in container-local directory
RUN mkdir -p /opt/venv && uv venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Set UV link mode to avoid hardlink warning (Fix for second warning)
# ENV UV_LINK_MODE=copy

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=../uv.lock,target=uv.lock \
    --mount=type=bind,source=../pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project

# Copy both the pyproject.toml and uv.lock files into the container
COPY ../pyproject.toml ../uv.lock ./

# Sync the project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen