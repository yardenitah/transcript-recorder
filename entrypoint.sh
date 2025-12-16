#!/bin/bash

# 1. Start DBus
mkdir -p /var/run/dbus
dbus-daemon --system --fork

# 2. Cleanup old PulseAudio files
rm -rf /var/run/pulse /var/lib/pulse /root/.config/pulse

# 3. Configure PulseAudio for Anonymous Access (The Fix!)
# במקום דגל, אנחנו עורכים את קובץ ההגדרות הפנימי ומאפשרים גישה לכולם
if [ -f /etc/pulse/system.pa ]; then
    sed -i 's/load-module module-native-protocol-unix/load-module module-native-protocol-unix auth-anonymous=1/' /etc/pulse/system.pa
fi

# 4. Start PulseAudio (System Mode, No bad flags)
pulseaudio -D --verbose --exit-idle-time=-1 --system --disallow-exit

echo "⏳ Waiting for PulseAudio..."
sleep 2

# 5. Create Dummy Output Sink
# We try multiple times just in case
for i in {1..5}; do
    pactl load-module module-null-sink sink_name=SpeakerOutput sink_properties=device.description="Dummy_Output" && break
    echo "⚠️ Retrying module load ($i)..."
    sleep 1
done

pactl set-default-sink SpeakerOutput || echo "⚠️ Failed to set default sink"

# 6. Verify Audio Server
echo "🔍 Audio Server Info:"
pactl info || echo "⚠️ Could not get info (might still work)"

# 7. Start the Bot
echo "🔊 Virtual Audio System Ready. Launching Bot..."
uvicorn main:app --host 0.0.0.0 --port 8000