FROM python:3.10-slim

# Install Audio Drivers (PulseAudio + ALSA)
RUN apt-get update --allow-releaseinfo-change && apt-get install -y --no-install-recommends \
    libasound2 \
    libasound2-plugins \
    libpulse0 \
    pulseaudio \
    pulseaudio-utils \
    libssl-dev \
    ca-certificates \
    libc++-dev \
    dbus \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENV AGORA_SDK_PATH=/usr/local/lib/python3.10/site-packages/agora/agora_sdk
COPY agora_rtc_sdk.zip /usr/local/lib/python3.10/site-packages/agora/agora_rtc_sdk.zip
COPY agora_sdk/ $AGORA_SDK_PATH/
RUN echo "$AGORA_SDK_PATH" > /etc/ld.so.conf.d/agora.conf && ldconfig

ENV LD_LIBRARY_PATH=$AGORA_SDK_PATH
ENV PYTHONPATH=/app

# Copy the entrypoint script and the app code
COPY entrypoint.sh .
COPY . .

# Give execution permissions to the script
RUN chmod +x entrypoint.sh

EXPOSE 8000

# Use the script to start the container
CMD ["./entrypoint.sh"]