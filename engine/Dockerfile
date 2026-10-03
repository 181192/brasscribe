# syntax=docker/dockerfile:1
#
# Linux image for benchmark runners and headless engines (the repository root is the build context).
#
#   CPU (linux/amd64 or linux/arm64):
#     docker build -f engine/Dockerfile --target cpu -t brasscribe:cpu .
#   NVIDIA (linux/amd64, run with --gpus all):
#     docker build -f engine/Dockerfile --target cuda \
#       --build-arg BASE=nvidia/cuda:12.8.1-runtime-ubuntu24.04 -t brasscribe:cuda .
#
#   docker run --rm -v "$PWD/data:/data" -p 8765:8765 brasscribe:cpu              # engine, LAN pairing code printed
#   docker run --rm brasscribe:cpu pixi run test                                   # unit tests
#   docker run --rm brasscribe:cpu sh -c 'pixi run python -m brasscribe_eval.ci_data --out /tmp/ci && \
#       BRASSCRIBE_DATA=/tmp/ci pixi run brasscribe bench ci --require-data'      # CI benchmark gate
#
# Model weights and datasets are not in the image; mount a data directory at /data (and models at /brasscribe/models).
# The Rust core's command line (brasscribe-core, for the bass-tab profile) is built from core/ in its own stage.
ARG BASE=ubuntu:24.04
ARG RUST_VERSION=1.91

# The core's command line, built for the image's own architecture.
FROM rust:${RUST_VERSION}-slim-bookworm AS core
WORKDIR /core
COPY core/Cargo.toml core/Cargo.lock ./
COPY core/.cargo .cargo
# Every member of the workspace: cargo refuses a workspace with one missing.
COPY core/brasscribe-core brasscribe-core
COPY core/brasscribe-ffi brasscribe-ffi
COPY core/brasscribe-cli brasscribe-cli
COPY core/target-fretted target-fretted
COPY core/tools tools
RUN cargo build --release --locked -p brasscribe-cli

FROM ${BASE} AS base
# The pixi version CI pins (.pixi-version); --build-arg PIXI_VERSION=v0.x.y overrides it.
ARG PIXI_VERSION=
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git ffmpeg \
 && rm -rf /var/lib/apt/lists/*
COPY .pixi-version /tmp/pixi-version
RUN v="${PIXI_VERSION:-v$(tr -d ' \r\n' < /tmp/pixi-version | sed 's/^v//')}" \
 && curl -fsSL https://pixi.sh/install.sh | PIXI_VERSION="$v" PIXI_HOME=/usr/local PIXI_NO_PATH_UPDATE=1 bash \
 && pixi --version
WORKDIR /brasscribe
COPY pixi.toml pixi.lock ./
COPY music music
COPY eval eval
COPY engine engine
COPY ml ml
COPY qa qa
ENV BRASSCRIBE_ADAPTER_RUNNER=pixi \
    BRASSCRIBE_DATA=/data \
    BRASSCRIBE_PYTHON=/brasscribe/.pixi/envs/default/bin/python
EXPOSE 8765
# mDNS from a bridged container would advertise the container's own address.
CMD ["pixi", "run", "brasscribe", "serve", "--lan", "--no-advertise"]

# Engine plus every adapter on CPU PyTorch.
FROM base AS cpu
ARG ENVS="default swift-f0 basic-pitch muscriptor beat-this mega53 separator"
RUN for e in ${ENVS}; do pixi install --frozen -e "$e" || exit 1; done \
 && pixi clean cache --yes
# After the environments, so a change to the core does not install them again.
COPY --from=core /core/target/release/brasscribe-core /usr/local/bin/brasscribe-core
ENV BRASSCRIBE_CORE_CLI=/usr/local/bin/brasscribe-core

# Engine plus CUDA 12 builds of the torch adapters (needs the NVIDIA container runtime to use the GPU).
FROM base AS cuda
ARG ENVS="default swift-f0 basic-pitch muscriptor-cuda beat-this-cuda mega53-cuda separator-cuda"
# No GPU is visible while building; declare the driver's CUDA version so the CUDA environments install.
RUN for e in ${ENVS}; do CONDA_OVERRIDE_CUDA=12.8 pixi install --frozen -e "$e" || exit 1; done \
 && pixi clean cache --yes
COPY --from=core /core/target/release/brasscribe-core /usr/local/bin/brasscribe-core
ENV BRASSCRIBE_CUDA=1 \
    BRASSCRIBE_CORE_CLI=/usr/local/bin/brasscribe-core
