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
ARG BASE=ubuntu:24.04

FROM ${BASE} AS base
ARG PIXI_VERSION=v0.81.0
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git ffmpeg \
 && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://pixi.sh/install.sh | PIXI_VERSION=${PIXI_VERSION} PIXI_HOME=/usr/local PIXI_NO_PATH_UPDATE=1 bash \
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
CMD ["pixi", "run", "brasscribe", "serve", "--lan"]

# Engine plus every adapter on CPU PyTorch.
FROM base AS cpu
ARG ENVS="default swift-f0 basic-pitch muscriptor beat-this mega53 separator"
RUN for e in ${ENVS}; do pixi install --frozen -e "$e" || exit 1; done \
 && pixi clean cache --yes

# Engine plus CUDA 12 builds of the torch adapters (needs the NVIDIA container runtime to use the GPU).
FROM base AS cuda
ARG ENVS="default swift-f0 basic-pitch muscriptor-cuda beat-this-cuda mega53-cuda separator-cuda"
# No GPU is visible while building; declare the driver's CUDA version so the CUDA environments install.
RUN for e in ${ENVS}; do CONDA_OVERRIDE_CUDA=12.8 pixi install --frozen -e "$e" || exit 1; done \
 && pixi clean cache --yes
ENV BRASSCRIBE_CUDA=1
