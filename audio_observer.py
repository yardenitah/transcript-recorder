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

# --- FULL DEBUG: SHOW ME EVERYTHING (INCLUDING ZEROS) ---
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logger = logging.getLogger("AUDIO_DEBUG")


class SonioxMixedWorker:
    def __init__(self):
        logger.debug("🔹 [Worker] __init__")
        self.audio_queue: "queue.Queue[bytes]" = queue.Queue()
        self.running = True
        logger.debug("🔹 [Worker] Starting thread...")
        self.thread = threading.Thread(target=self._run_websocket_loop, daemon=True)
        self.thread.start()

    def add_audio(self, data: bytes, source: str):
        # LOG EVERY SINGLE ADD TO QUEUE
        logger.debug(f"➕ [Queue] Adding {len(data)} bytes from {source}")

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

                    logger.debug(f"📤 [Worker] Sending Initial Config: {json.dumps(config)}")
                    websocket.send(json.dumps(config))
                    
                    def read_task():
                        logger.debug("🔹 [Reader] Reader thread started")
                        while True:
                            try:
                                for message in websocket:
                                    # LOG RAW RESPONSE FROM SONIOX
                                    logger.debug(f"📥 [Reader] Received: {message}")

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
                                logger.error(f"❌ [Reader] Exception: {e}")
                                break

                    reader = threading.Thread(target=read_task, daemon=True)
                    reader.start()

                    # Correct silence size: 16k * 20ms * 2bytes = 640 bytes
                    FRAME_MS = 20
                    SAMPLES_PER_FRAME = int(16000 * (FRAME_MS / 1000))
                    silence = b'\x00' * (SAMPLES_PER_FRAME * 2)

                    logger.debug(f"🔹 [Worker] Loop Start. Silence packet size: {len(silence)}")
                    while self.running:
                        try:
                            # 20ms timeout
                            chunk = self.audio_queue.get(timeout=0.02)

                            # LOG EVERY SEND (Real Audio)
                            logger.debug(f"⚡ [Worker] Sending REAL CHUNK: {len(chunk)} bytes")
                            websocket.send(chunk)

                        except queue.Empty:
                            # LOG EVERY SILENCE SEND
                            logger.debug("💤 [Worker] Queue empty -> Sending SILENCE")
                            websocket.send(silence)

                        except Exception as e:
                            logger.error(f"❌ [Worker] Loop Exception: {e}")
                            break

            except Exception as e:
                logger.error(f"⚠️ [Worker] Connection failed, retrying... Error: {e}")
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

            # LOG EVERY SINGLE FRAME RECEIVED FROM AGORA
            logger.debug(f"👂 [Observer] _process_frame call: '{name}' | {len(data)} bytes | Total: {self.frame_count}")

            # RMS CHECK
            rms = 0
            if len(data) > 0:
                count = len(data) // 2
                shorts = struct.unpack(f'<{count}h', data[:count * 2])
                sum_squares = sum(s ** 2 for s in shorts)
                import math
                rms = math.sqrt(sum_squares / count)

            # Log RMS for every frame
            logger.debug(f"📊 [Observer] Frame RMS: {rms:.2f}")

            if rms > 100:
                logger.debug(f"🔊 [Observer] SOUND! Adding to queue.")
                self.worker.add_audio(data, name)

            # FORCE SEND BEFORE_MIXING (Bypassing RMS check to ensure flow)
            if "before_mixing" in name:
                logger.debug(f"🚀 [Observer] Forcing send for {name}")
                self.worker.add_audio(data, name)

            return 1
        except Exception as e:
            logger.error(f"❌ [Observer] Error processing frame {name}: {e}")
            return 1


    def on_playback_audio_frame(self, agora_local_user, channelId, frame):
        logger.debug("🔵 [Callback] on_playback_audio_frame triggered")
        return self._process_frame("on_playback", frame)

    def on_record_audio_frame(self, agora_local_user, channelId, frame):
        logger.debug("🔴 [Callback] on_record_audio_frame triggered")
        return 1

    def on_mixed_audio_frame(self, agora_local_user, channelId, frame):
        logger.debug("🟣 [Callback] on_mixed_audio_frame triggered")
        return self._process_frame("on_mixed", frame)

    def on_playback_audio_frame_before_mixing(self, agora_local_user, channel_id, uid, frame):
        logger.debug(f"🟠 [Callback] on_playback_audio_frame_before_mixing triggered (UID={uid})")
        return self._process_frame(f"before_mixing_u{uid}", frame)

    def on_ear_monitoring_audio_frame(self, agora_local_user, frame):
        logger.debug("🎧 [Callback] on_ear_monitoring_audio_frame triggered")
        return 1

    def stop(self):
        self.worker.stop()