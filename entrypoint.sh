#!/bin/bash

# 1. Start DBus
mkdir -p /var/run/dbus
dbus-daemon --system --fork

# 2. Cleanup old PulseAudio files
rm -rf /var/run/pulse /var/lib/pulse /root/.config/pulse

# 3. Start PulseAudio in System Mode (Allow Anonymous Access)
# --auth-anonymous=1 is the magic flag here!
pulseaudio -D --verbose --exit-idle-time=-1 --system --disallow-exit --auth-anonymous=1

echo "⏳ Waiting for PulseAudio..."
sleep 2

# 4. Create Dummy Output Sink
# We try multiple times just in case
for i in {1..5}; do
    pactl load-module module-null-sink sink_name=SpeakerOutput sink_properties=device.description="Dummy_Output" && break
    echo "⚠️ Retrying module load ($i)..."
    sleep 1
done

pactl set-default-sink SpeakerOutput || echo "⚠️ Failed to set default sink"

# 5. Verify Audio Server
echo "🔍 Audio Server Info:"
pactl info || echo "⚠️ Could not get info (might still work)"

# 6. Start the Bot
echo "🔊 Virtual Audio System Ready. Launching Bot..."
uvicorn main:app --host 0.0.0.0 --port 8000