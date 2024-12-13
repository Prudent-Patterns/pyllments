FROM --platform=linux/amd64 debian:bookworm-slim as main

# Update and upgrade system packages, install all required dependencies in one layer
RUN apt-get -y update && \
    apt-get -y upgrade && \
    apt-get -y install wget git-all ffmpeg build-essential libopengl0 libsm6 libegl1 curl ca-certificates && \
    apt-get clean

# Install Quarto
RUN wget https://github.com/quarto-dev/quarto-cli/releases/download/v1.6.39/quarto-1.6.39-linux-amd64.deb && \
    dpkg -i quarto-1.6.39-linux-amd64.deb && \
    rm quarto-1.6.39-linux-amd64.deb

# Install UV
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin/:$PATH"

RUN uv venv

# Set the virtual environment path
ENV VIRTUAL_ENV=/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-install-workspace