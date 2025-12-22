import logging
import queue
import threading
import json
import os
import time
import sys
import struct

from websockets.sync.client import connect
from agora.rtc.audio_frame_observer import IAudioFrameObserver, AudioFrame

# Initialize Logging
# Changed to INFO to avoid binary spam from 'websockets' library
logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logger = logging.getLogger("AUDIO_PROCESSOR")


class SonioxMixedWorker:
    """
    Handles buffering audio chunks and sending them to Soniox STT via WebSocket.
    """

    def __init__(self):
        self.audio_queue: "queue.Queue[bytes]" = queue.Queue()
        self.running = True
        self.thread = threading.Thread(target=self._run_websocket_loop, daemon=True)
        self.thread.start()

    def add_audio(self, data: bytes, source: str):
        # Prevent queue from exploding if websocket gets stuck
        if self.audio_queue.qsize() > 2000:
            # Drop old packets if queue is too full
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                pass

        self.audio_queue.put(data)

    def stop(self):
        self.running = False
        self.thread.join(timeout=1)

    def _run_websocket_loop(self):
        api_key = os.environ.get("SONIOX_API_KEY")
        if not api_key:
            logger.error("❌ Missing SONIOX_API_KEY environment variable")
            return

        uri = "wss://stt-rt.soniox.com/transcribe-websocket"
        logger.info(f"🔄 Connecting to Soniox API...")

        config = {
            "api_key": api_key,
            "model": "stt-rt-preview",
            "audio_format": "pcm_s16le",
            "sample_rate": 16000,
            "num_channels": 1,
            "enable_speaker_diarization": True,
            "enable_language_identification": True,
            "language_hints": ["he"]
        }

        while self.running:
            try:
                with connect(uri) as websocket:
                    logger.info("✅ Connected to Soniox WebSocket!")
                    websocket.send(json.dumps(config))

                    # Sub-thread to read responses from Soniox
                    def read_task():
                        while True:
                            try:
                                for message in websocket:
                                    response = json.loads(message)
                                    tokens = response.get("tokens", [])
                                    final_text = ""
                                    current_speaker = "?"

                                    for t in tokens:
                                        if t.get("is_final"):
                                            final_text += t.get("text", "")
                                            spk = t.get("speaker", "?")
                                            current_speaker = f"Speaker {spk}"

                                    if final_text.strip():
                                        print(f"\n🎤 [{current_speaker}]: {final_text}")

                            except Exception as e:
                                logger.error(f"❌ Read Error from Soniox: {e}")
                                break

                    reader = threading.Thread(target=read_task, daemon=True)
                    reader.start()

                    # Silence packet to keep connection alive when no one talks
                    silence = b'\x00' * 3200

                    while self.running:
                        try:
                            # Try to get real audio with a short timeout
                            chunk = self.audio_queue.get(timeout=0.02)  # 20ms wait

                            # Only log occasionally to avoid flooding
                            if self.audio_queue.qsize() % 50 == 0:
                                logger.info(f"📤 Sending audio chunk to Soniox (Size: {len(chunk)})")

                            websocket.send(chunk)

                        except queue.Empty:
                            # Send silence if queue is empty
                            websocket.send(silence)
                        except Exception as e:
                            logger.error(f"❌ Send Loop Error: {e}")
                            break

            except Exception as e:
                logger.error(f"⚠️ Connection to Soniox failed (retrying in 3s): {e}")
                time.sleep(3)


class PcmAudioObserver(IAudioFrameObserver):
    def __init__(self, save_to_file: bool = False):
        super(PcmAudioObserver, self).__init__()
        self.worker = SonioxMixedWorker()
        self.frame_count = 0
        logger.info("✅ PcmAudioObserver INITIALIZED")

    def _process_frame(self, name, frame):
        try:
            self.frame_count += 1
            data = bytes(frame.buffer)

            # Debug log to verify frames are arriving (every 100 frames)
            if self.frame_count % 100 == 0:
                logger.info(f"🎧 Agora Audio Frame Received: {name} | Bytes: {len(data)}")

            # --- RMS Calculation (Simple Voice Activity Detection) ---
            rms = 0
            if len(data) > 0:
                count = len(data) // 2
                shorts = struct.unpack(f'<{count}h', data[:count * 2])
                sum_squares = sum(s ** 2 for s in shorts)
                import math
                rms = math.sqrt(sum_squares / count)

            # Log if sound is detected
            if rms > 100:
                # print(f"🔊 [{name}] Sound detected! RMS: {int(rms)}", end="\r")
                self.worker.add_audio(data, name)

            # Send 'before_mixing' always to ensure continuous stream if needed
            if "before_mixing" in name:
                self.worker.add_audio(data, name)

            return 1
        except Exception as e:
            logger.error(f"❌ Error processing frame in {name}: {e}")
            return 1


    def on_playback_audio_frame(self, agora_local_user, channelId, frame):
        logger.info(f"🔵 Callback: on_playback_audio_frame")
        return self._process_frame("on_playback", frame)

    def on_record_audio_frame(self, agora_local_user, channelId, frame):
        return 1

    def on_mixed_audio_frame(self, agora_local_user, channelId, frame):
        logger.info(f"🟣 Callback: on_mixed_audio_frame")
        return self._process_frame("on_mixed", frame)

    def on_playback_audio_frame_before_mixing(self, agora_local_user, channel_id, uid, frame):
        logger.info(f"🟠 Callback: before_mixing (UID: {uid})")
        return self._process_frame(f"before_mixing_u{uid}", frame)

    def on_ear_monitoring_audio_frame(self, agora_local_user, frame):
        return 1

    def stop(self):
        self.worker.stop()