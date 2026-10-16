# Builds the Flutter Linux desktop app without installing a toolchain on the host.
# Same base as the host (Ubuntu 24.04 / Pop!_OS 24.04) so the binary runs there.
FROM ubuntu:24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl unzip xz-utils ca-certificates \
        clang g++ cmake ninja-build pkg-config libgtk-3-dev liblzma-dev \
    && rm -rf /var/lib/apt/lists/*

ARG FLUTTER_VERSION=3.47.7
RUN git clone --depth 1 -b ${FLUTTER_VERSION} https://github.com/flutter/flutter.git /opt/flutter \
    && chown -R ubuntu:ubuntu /opt/flutter

# ubuntu = uid 1000, so files written to the mounted output folder belong to the host user
USER ubuntu
ENV PATH=/opt/flutter/bin:$PATH PUB_CACHE=/home/ubuntu/.pub-cache
RUN flutter config --no-analytics --no-cli-animations \
    && flutter precache --linux --no-android --no-ios --no-web \
    && flutter --version

COPY --chown=ubuntu:ubuntu docker/build-linux.sh /usr/local/bin/build-linux
WORKDIR /work
ENTRYPOINT ["build-linux"]
