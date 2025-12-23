#FROM python:3.10-slim
#
## Install minimal system dependencies required for Agora SDK and Audio
#RUN apt-get update --allow-releaseinfo-change && apt-get install -y --no-install-recommends \
#    libasound2 \
#    libssl-dev \
#    ca-certificates \
#    libc++-dev \
#    && rm -rf /var/lib/apt/lists/*
#
#WORKDIR /app
#
## Install Python dependencies
#COPY requirements.txt .
#RUN pip install --no-cache-dir -r requirements.txt
#
## Configure Agora SDK paths
#ENV AGORA_SDK_PATH=/usr/local/lib/python3.10/site-packages/agora/agora_sdk
#COPY agora_rtc_sdk.zip /usr/local/lib/python3.10/site-packages/agora/agora_rtc_sdk.zip
#COPY agora_sdk/ $AGORA_SDK_PATH/
#RUN echo "$AGORA_SDK_PATH" > /etc/ld.so.conf.d/agora.conf && ldconfig
#
#ENV LD_LIBRARY_PATH=$AGORA_SDK_PATH
#ENV PYTHONPATH=/app
#
## Copy application code
#COPY . .
#
#EXPOSE 8000
#
## Start the application using Uvicorn
#CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.10-slim

# Install system dependencies
RUN apt-get update --allow-releaseinfo-change && apt-get install -y --no-install-recommends \
    libasound2 \
    libssl-dev \
    ca-certificates \
    libc++-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Configure Agora SDK paths
ENV AGORA_SDK_PATH=/usr/local/lib/python3.10/site-packages/agora/agora_sdk
COPY agora_rtc_sdk.zip /usr/local/lib/python3.10/site-packages/agora/agora_rtc_sdk.zip
COPY agora_sdk/ $AGORA_SDK_PATH/
RUN echo "$AGORA_SDK_PATH" > /etc/ld.so.conf.d/agora.conf && ldconfig

ENV LD_LIBRARY_PATH=$AGORA_SDK_PATH
ENV PYTHONPATH=/app

# --- SHINUI: PATCH THE SDK BUG ---
# התיקון הזה מונע את השגיאה TypeError: '>=' not supported between instances of 'NoneType' and 'int'
RUN sed -i 's/if custome_specified >= 0:/if custome_specified is not None and custome_specified >= 0:/g' /usr/local/lib/python3.10/site-packages/agora/rtc/rtc_connection.py

# Copy application code
COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]