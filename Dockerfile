# Multi-arch base (works on linux/amd64 and linux/arm64)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1


# before pip installs / in the same layer as other apt installs
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 
 
# Optional: OpenBLAS helps numpy and (if compiled) llama-cpp
RUN apt-get update && apt-get install -y --no-install-recommends \
      libopenblas-dev ca-certificates curl 

RUN rm -rf /var/lib/apt/lists/*

# RUN apt-get install libgomp1

WORKDIR /app

RUN python -m pip install --upgrade pip
# install TA-Lib wheels (includes the native C lib)
RUN pip install --only-binary=:all: "TA-Lib>=0.6.5"

# 2) CPU wheels for llama-cpp-python (avoid source builds)
#    This index hosts prebuilt CPU wheels for amd64 & arm64.
ARG LLAMA_CPP_VERSION=0.3.2
RUN pip install --only-binary=:all: \
    --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu \
    "llama-cpp-python==${LLAMA_CPP_VERSION}"
    
# Copy just requirements first for better caching
COPY requirements-docker.txt requirements.txt
RUN pip install -r requirements.txt

# Copy the rest of your project (agent.py, llm.py, features_talib.py, paper_broker.py, auth.py, config.yaml, etc.)
COPY . .

# Model lives outside the image; mount /models with your GGUF and point config.yaml to it.
RUN mkdir /models
# ~/.apikeys is mounted read-only for credentials.
CMD ["python", "agent.py"]
