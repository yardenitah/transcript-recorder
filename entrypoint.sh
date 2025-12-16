#!/bin/bash

# 1. Start DBus (Required for PulseAudio)
mkdir -p /var/run/dbus
dbus-daemon --system --fork

# 2. Clean up old locks
rm -rf /var/run/pulse /var/lib/pulse /root/.config/pulse

# 3. Start PulseAudio as System Daemon (Virtual Audio Driver)
pulseaudio -D --verbose --exit-idle-time=-1 --system --disallow-exit

# 4. Create the "Dummy" Speaker (Null Sink)
# This tricks Agora into thinking there is a speaker output
pactl load-module module-null-sink sink_name=SpeakerOutput sink_properties=device.description="Dummy_Output"
pactl set-default-sink SpeakerOutput

# 5. Start the Bot
echo "🔊 Virtual Audio System Started. Launching Bot..."
exec python main.py