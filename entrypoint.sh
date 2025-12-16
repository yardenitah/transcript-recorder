#!/bin/bash

# 1. Start DBus (Required for PulseAudio)
mkdir -p /var/run/dbus
dbus-daemon --system --fork

# 2. Clean up old locks
rm -rf /var/run/pulse /var/lib/pulse /root/.config/pulse

# 3. Start PulseAudio as System Daemon (Background)
# --disallow-exit ensures it stays alive
pulseaudio -D --verbose --exit-idle-time=-1 --system --disallow-exit

# 4. Wait for PulseAudio to start
echo "⏳ Waiting for PulseAudio..."
sleep 2

# 5. Create the "Dummy" Speaker (Null Sink)
# We use 'pactl' to configure the server we just started
pactl load-module module-null-sink sink_name=SpeakerOutput sink_properties=device.description="Dummy_Output" || echo "⚠️ Module load failed, but continuing..."
pactl set-default-sink SpeakerOutput || echo "⚠️ Set default sink failed, but continuing..."

# 6. Verify Audio Server Status
echo "🔍 Audio Server Info:"
pactl info || echo "⚠️ Could not get info"

# 7. Start the Bot (using full path to python just in case)
echo "🔊 Virtual Audio System Started. Launching Bot..."
# Use uvicorn directly if python command fails, or python -m
uvicorn main:app --host 0.0.0.0 --port 8000