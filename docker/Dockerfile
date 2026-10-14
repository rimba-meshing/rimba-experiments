FROM nvidia/cuda:13.2.0-devel-ubuntu24.04@sha256:f9492f2eea77fbc3d0c14fa8738f35946b42da72917bf5959d284ca39b4f209a AS protocol

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    build-essential ca-certificates git python3 python3-venv time \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/repro \
    && /opt/repro/bin/pip install --no-cache-dir cmake==4.2.3
ENV PATH="/opt/repro/bin:${PATH}"
ENV MPLBACKEND=Agg
ENV MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /workspace
CMD ["python3", "tools/run_paper_protocol.py", "--help"]

FROM protocol AS figures
COPY requirements-figures.txt /opt/requirements-figures.txt
COPY requirements.lock.txt /opt/requirements.lock.txt
RUN pip install --no-cache-dir -r /opt/requirements-figures.txt \
    --constraint /opt/requirements.lock.txt

FROM figures AS quality
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    libegl1 libgl1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-quality.txt /opt/requirements-quality.txt
RUN pip install --no-cache-dir -r /opt/requirements-quality.txt \
    --constraint /opt/requirements.lock.txt
RUN git clone https://github.com/RuanJY/TanksAndTemples.git /opt/TanksAndTemples \
    && git -C /opt/TanksAndTemples checkout --detach 06f6537b471fd939eaed78678b3c0ebd22bd398a \
    && git config --system --add safe.directory /opt/TanksAndTemples
ENV RI_TNT_RUNNER=/opt/TanksAndTemples/python_toolbox/evaluation/run.py
