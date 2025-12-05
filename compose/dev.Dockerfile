FROM ubuntu:24.04

RUN apt update && apt install -y \
    python3.12 python3.12-venv python3-pip \
    libpq-dev build-essential cron && \
    apt clean

# Create venv OUTSIDE the app directory
RUN python3.12 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /opt/crownpipe

# Copy only requirements first for caching
COPY requirements.txt /opt/crownpipe/

RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy source code
COPY . /opt/crownpipe/
