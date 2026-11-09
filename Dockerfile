# syntax=docker/dockerfile:1
# bitnet.cpp's llama-server (the fast engine; setting "Engine" = bitnet.cpp). Static, no OpenMP, so the slim image needs no extra libraries.
FROM python:3.12-slim AS cpp
RUN apt-get update && apt-get install -y --no-install-recommends git cmake clang make ca-certificates && rm -rf /var/lib/apt/lists/*
# Pinned to June 2025: later BitNet versions changed the i2_s kernels, and with Microsoft's GGUF they gave wrong answers that never end.
ARG BITNET_CPP_REF=404980eecae38affa4871c3e419eae3f44536a95
RUN git clone https://github.com/microsoft/BitNet /bitnet && cd /bitnet && git checkout "$BITNET_CPP_REF"  && git submodule update --init --recursive --depth 1
WORKDIR /bitnet
# This BitNet version needs include/bitnet-lut-kernels.h to build, even though i2_s does not use it: make it as setup_env.py does for the 2B-4T model.
RUN if [ "$(uname -m)" = x86_64 ]; then python utils/codegen_tl2.py --model bitnet_b1_58-3B --BM 160,320,320 --BK 96,96,96 --bm 32,32,32;     else python utils/codegen_tl1.py --model bitnet_b1_58-3B --BM 160,320,320 --BK 64,128,64 --bm 32,64,32; fi
RUN CC=clang CXX=clang++ cmake -B build -DBUILD_SHARED_LIBS=OFF -DGGML_OPENMP=OFF -DBITNET_X86_TL2=OFF -DCMAKE_BUILD_TYPE=Release       -DLLAMA_BUILD_SERVER=ON -DLLAMA_BUILD_COMMON=ON -DLLAMA_BUILD_TOOLS=ON -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_UI=OFF -DLLAMA_USE_PREBUILT_UI=OFF  && cmake --build build --target llama-server -j"$(nproc)"

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv
ENV SERVICE_WEB_DIR=/app/web SERVICE_TOKENS_FILE=/data/tokens.json PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH" HF_HOME=/models SERVICE_HOST=0.0.0.0
WORKDIR /app

# uv.lock pins torch to the CPU-only index (see pyproject.toml), so no CUDA/Triton wheels are pulled.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
RUN python -c "import torch; assert torch.version.cuda is None and torch.version.hip is None, 'CPU-only torch required'"
COPY --from=cpp /bitnet/build/bin/llama-server /usr/local/bin/llama-server
COPY src ./src
COPY web ./web

ENV SERVICE_PORT=29201
EXPOSE 29201
CMD ["python", "src/app.py"]
