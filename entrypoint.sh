#!/bin/bash

# 1. ניקוי שאריות אם הקונטיינר הופעל מחדש
rm -rf /var/run/pulse /var/lib/pulse /root/.config/pulse

# 2. הפעלת PulseAudio במצב "מערכת" (System Mode) ללא הגבלות
# אנו טוענים מודול "Null Sink" שמתפקד גם כרמקול וגם כמיקרופון
pulseaudio -D --verbose --exit-idle-time=-1 --system --disallow-exit \
    --load="module-null-sink sink_name=DummyOutput sink_properties=device.description='Dummy_Output'" \
    --load="module-virtual-source source_name=DummyInput master=DummyOutput.monitor"

# 3. וידוא שהשרת עלה
sleep 2
echo "🔊 PulseAudio Status:"
pactl info || echo "⚠️ PulseAudio failed to start, but trying to continue..."

# 4. הרצת הבוט (מעביר את הפקודה המקורית)
exec "$@"