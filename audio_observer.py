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

# --- FULL DEBUG MODE ---
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logger = logging.getLogger("AUDIO_DEBUG")


class SonioxMixedWorker:
    def __init__(self):
        self.audio_queue: "queue.Queue[bytes]" = queue.Queue()
        self.running = True
        logger.debug("🔹 [Worker] Initializing thread...")
        self.thread = threading.Thread(target=self._run_websocket_loop, daemon=True)
        self.thread.start()

    def add_audio(self, data: bytes, source: str):
        # Log adding to queue
        logger.debug(f"➕ [Queue] Add {len(data)} bytes from {source}")

        if self.audio_queue.qsize() > 2000:
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                pass
        self.audio_queue.put(data)

    def stop(self):
        logger.debug("🛑 [Worker] Stopping...")
        self.running = False
        self.thread.join(timeout=1)

    def _run_websocket_loop(self):
        api_key = os.environ.get("SONIOX_API_KEY")
        if not api_key:
            logger.error("❌ [Worker] Missing SONIOX_API_KEY")
            return

        uri = "wss://stt-rt.soniox.com/transcribe-websocket"
        logger.info(f"🔄 [Worker] Connecting to: {uri}")

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
                with connect(uri, ping_interval=None) as websocket:
                    logger.info("✅ [Worker] WebSocket Connected!")
                    websocket.send(json.dumps(config))

                    def read_task():
                        logger.debug("🔹 [Reader] Started listening...")
                        while True:
                            try:
                                for message in websocket:
                                    # Show raw response
                                    logger.debug(f"📥 [Reader] Msg: {message}")

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
                                logger.error(f"❌ [Reader] Error: {e}")
                                break

                    reader = threading.Thread(target=read_task, daemon=True)
                    reader.start()

                    # Correct silence size (640 bytes for 20ms)
                    FRAME_MS = 20
                    SAMPLES_PER_FRAME = int(16000 * (FRAME_MS / 1000))
                    silence = b'\x00' * (SAMPLES_PER_FRAME * 2)

                    logger.debug(f"🔹 [Worker] Loop Start. Silence size: {len(silence)}")

                    while self.running:
                        try:
                            chunk = self.audio_queue.get(timeout=0.02)
                            # Log sending real audio
                            logger.debug(f"⚡ [Worker] Sending REAL CHUNK: {len(chunk)} bytes")
                            websocket.send(chunk)
                        except queue.Empty:
                            # Log sending silence
                            logger.debug("💤 [Worker] Queue empty -> Sending SILENCE")
                            websocket.send(silence)
                        except Exception as e:
                            logger.error(f"❌ [Worker] Loop Error: {e}")
                            break

            except Exception as e:
                logger.error(f"⚠️ [Worker] Connection failed: {e}")
                time.sleep(3)


class PcmAudioObserver(IAudioFrameObserver):
    def __init__(self, save_to_file: bool = False):
        super(PcmAudioObserver, self).__init__()
        self.worker = SonioxMixedWorker()
        self.frame_count = 0
        logger.info("✅ [Observer] Initialized")

    def _process_frame(self, name, frame):
        try:
            self.frame_count += 1
            data = bytes(frame.buffer)

            # Log every frame received
            logger.debug(f"👂 [Observer] Got Frame: {name} | Size: {len(data)}")

            # Pass everything to worker
            self.worker.add_audio(data, name)

            return 1
        except Exception as e:
            logger.error(f"❌ [Observer] Error: {e}")
            return 1

    def on_playback_audio_frame(self, agora_local_user, channelId, frame):
        return self._process_frame("on_playback", frame)

    def on_record_audio_frame(self, agora_local_user, channelId, frame):
        return 1

    def on_mixed_audio_frame(self, agora_local_user, channelId, frame):
        logger.debug("🟣 [Callback] on_mixed triggered")
        return self._process_frame("on_mixed", frame)

    def on_playback_audio_frame_before_mixing(self, agora_local_user, channel_id, uid, frame):
        logger.debug(f"🟠 [Callback] before_mixing triggered (UID={uid})")
        return self._process_frame(f"before_mixing_u{uid}", frame)

    def on_ear_monitoring_audio_frame(self, agora_local_user, frame):
        return 1

    def stop(self):
        self.worker.stop()