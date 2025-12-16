import logging
import queue
import threading
import json
import os
import time
import sys

from websockets.sync.client import connect
from agora.rtc.audio_frame_observer import IAudioFrameObserver, AudioFrame

# הגדרת לוגר שכותב מיד לטרמינל (בלי Buffering)
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logger = logging.getLogger("DEBUG_OBSERVER")


class SonioxMixedWorker:
    def __init__(self):
        self.audio_queue: "queue.Queue[bytes]" = queue.Queue()
        self.running = True
        self.thread = threading.Thread(target=self._run_websocket_loop, daemon=True)
        self.thread.start()

    def add_audio(self, data: bytes, source: str):
        # לוג כל 100 צ'אנקים כדי לא להציף, אבל שנדע שזה חי
        if self.audio_queue.qsize() % 100 == 0:
            logger.debug(f"Queue Status: Added audio from {source}. Queue size: {self.audio_queue.qsize()}")
        self.audio_queue.put(data)

    def stop(self):
        self.running = False
        self.thread.join(timeout=1)

    def _run_websocket_loop(self):
        api_key = os.environ.get("SONIOX_API_KEY")
        if not api_key:
            logger.error("❌ Missing SONIOX_API_KEY")
            return

        uri = "wss://stt-rt.soniox.com/transcribe-websocket"

        # דיבאג לקונפיגורציה
        logger.info(f"Connecting to Soniox with API KEY ending in ...{api_key[-4:]}")

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

                    def read_task():
                        while True:
                            try:
                                for message in websocket:
                                    response = json.loads(message)
                                    # נדפיס רק הודעות עם תוכן כדי לא להספים
                                    if "tokens" in response and response["tokens"]:
                                        logger.debug(f"Received from Soniox: {len(str(message))} bytes")

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
                                logger.error(f"Read Error: {e}")
                                break

                    reader = threading.Thread(target=read_task, daemon=True)
                    reader.start()

                    silence = b'\x00' * 3200
                    while self.running:
                        try:
                            chunk = self.audio_queue.get(timeout=0.1)
                            websocket.send(chunk)
                        except queue.Empty:
                            websocket.send(silence)
                        except Exception:
                            break

            except Exception as e:
                logger.error(f"Connection failed: {e}")
                time.sleep(3)


class PcmAudioObserver(IAudioFrameObserver):
    def __init__(self, save_to_file: bool = False):
        super(PcmAudioObserver, self).__init__()
        self.worker = SonioxMixedWorker()
        self.frame_count = 0
        logger.info("--- PcmAudioObserver INITIALIZED ---")

    # פונקציית עזר לדיבאג של הפריימים
    def _debug_frame(self, name, frame):
        try:
            self.frame_count += 1
            data = bytes(frame.buffer)
            is_silent = all(b == 0 for b in data)
            
            # Calculate audio level (RMS) to detect if there's actual audio
            if len(data) > 0:
                import struct
                samples = struct.unpack(f'<{len(data)//2}h', data[:len(data)//2*2])
                rms = int((sum(s*s for s in samples) / len(samples)) ** 0.5) if samples else 0
            else:
                rms = 0
            
            # Log first frame, every 100th frame, or when non-silent audio is detected
            if self.frame_count == 1 or self.frame_count % 100 == 0 or (not is_silent and rms > 100):
                sample_preview = list(data[:10])
                logger.info(f"[CALLBACK] {name} | Frame #{self.frame_count} | Size: {len(data)} | Silent: {is_silent} | RMS: {rms} | Samples: {sample_preview}")
            
            return data
        except Exception as e:
            logger.error(f"Error reading frame in {name}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return b''

    def on_playback_audio_frame(self, frame: AudioFrame) -> int:
        data = self._debug_frame("on_playback_audio_frame", frame)
        if data: self.worker.add_audio(data, "playback")
        return 1

    def on_record_audio_frame(self, frame: AudioFrame) -> int:
        self._debug_frame("on_record_audio_frame", frame)
        return 1

    def on_mixed_audio_frame(self, frame: AudioFrame) -> int:
        data = self._debug_frame("on_mixed_audio_frame", frame)
        if data: self.worker.add_audio(data, "mixed")
        return 1

    def on_playback_audio_frame_before_mixing(self, agora_local_user, channel_id, uid, frame):
        # כאן הלוגיקה קצת שונה כי יש UID
        try:
            data = bytes(frame.buffer)
            
            # Calculate RMS to detect actual audio
            if len(data) > 0:
                import struct
                samples = struct.unpack(f'<{len(data)//2}h', data[:len(data)//2*2])
                rms = int((sum(s*s for s in samples) / len(samples)) ** 0.5) if samples else 0
            else:
                rms = 0
            
            # Always send audio to Soniox (even silence), but log when we detect real audio
            if rms > 100:  # Threshold for detecting actual audio
                logger.info(f"[CALLBACK] on_playback_audio_frame_before_mixing | UID: {uid} | RMS: {rms} | 🔊 AUDIO DETECTED!")
            
            # Send all audio data (including silence) to maintain stream continuity
            self.worker.add_audio(data, f"user_{uid}")
            
            # Log periodically even for silence
            if self.frame_count % 200 == 0:
                logger.debug(f"[CALLBACK] on_playback_audio_frame_before_mixing | UID: {uid} | RMS: {rms} | Frames processed: {self.frame_count}")
                
        except Exception as e:
            logger.error(f"Error in before_mixing: {e}")
            import traceback
            logger.debug(traceback.format_exc())
        return 1

    def on_ear_monitoring_audio_frame(self, frame: AudioFrame) -> int:
        self._debug_frame("on_ear_monitoring_audio_frame", frame)
        return 1

    def stop(self):
        self.worker.stop()