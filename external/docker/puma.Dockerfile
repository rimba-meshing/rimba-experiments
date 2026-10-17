FROM ubuntu:20.04@sha256:8feb4d8ca5354def3d8fce243717141ce31e2c428701f6682bd2fafe15388214
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR=/tmp/matplotlib
RUN apt-get update && apt-get install -y --no-install-recommends     build-essential ca-certificates git curl python3 python3-dev python3-pip     libgl1 libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /opt/requirements.txt
RUN python3 -m pip install --no-cache-dir pip==23.3.2     && python3 -m pip install --no-cache-dir -r /opt/requirements.txt
RUN curl -fsSL https://github.com/embree/embree/releases/download/v2.17.7/embree-2.17.7.x86_64.linux.tar.gz -o /tmp/embree.tar.gz     && echo '2c4bdacd8f3c3480991b99e85b8f584975ac181373a75f3e9675bf7efae501fe  /tmp/embree.tar.gz' | sha256sum -c -     && tar -xzf /tmp/embree.tar.gz --strip-components=1 -C /usr/local     && rm /tmp/embree.tar.gz && ldconfig     && python3 -m pip install --no-cache-dir --no-build-isolation        https://github.com/scopatz/pyembree/releases/download/0.1.6/pyembree-0.1.6.tar.gz
COPY source /opt/source
RUN python3 -m pip install --no-cache-dir --no-build-isolation --no-deps /opt/source
COPY inventory.py /opt/inventory.py
COPY build-input.json /opt/build-input.json
RUN python3 /opt/inventory.py > /opt/environment.json
ENTRYPOINT []
