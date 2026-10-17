FROM ubuntu:22.04@sha256:0a9887931b0e38af2e3487ed39e29436b0535c4f3f52e57745baaf79d1898956
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR=/tmp/matplotlib
RUN apt-get update && apt-get install -y --no-install-recommends     build-essential ca-certificates cmake git python3 python3-dev python3-pip     libeigen3-dev libopenvdb-dev pybind11-dev libegl1 libgl1 libgomp1     && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /opt/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /opt/requirements.txt
COPY source /opt/source
ENV CMAKE_BUILD_PARALLEL_LEVEL=2
RUN python3 -m pip install --no-cache-dir --no-build-isolation --no-deps /opt/source
COPY inventory.py /opt/inventory.py
COPY build-input.json /opt/build-input.json
RUN python3 /opt/inventory.py > /opt/environment.json
ENTRYPOINT []
