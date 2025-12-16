import logging
import queue
import threading
import json
import os
import time

from websockets.sync.client import connect
from agora.rtc.audio_frame_observer import IAudioFrameObserver, AudioFrame

logger = logging.getLogger(__name__)


class SonioxMixedWorker:
    def __init__(self):
        self.audio_queue: "queue.Queue[bytes]" = queue.Queue()
        self.running = True
        self.thread = threading.Thread(target=self._run_websocket_loop, daemon=True)
        self.thread.start()

    def add_audio(self, data: bytes):
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

        logger.info("🚀 Starting Mixed Stream Worker...")

        while self.running:
            try:
                with connect(uri) as websocket:
                    logger.info("✅ Connected to Soniox!")
                    websocket.send(json.dumps(config))

                    def read_task():
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
                                    logger.info(f"TRANSCRIPT [{current_speaker}]: {final_text}")
                        except Exception as e:
                            logger.error(f"Read Error: {e}")

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

    # --- DRAGNET: מימוש כל הפונקציות כדי לתפוס כל טיפת אודיו ---

    def on_playback_audio_frame(self, frame: AudioFrame) -> int:
        data = bytes(frame.buffer)
        if any(b != 0 for b in data[:100]):
            print("!", end="", flush=True)  # אודיו אמיתי!
            self.worker.add_audio(data)
        else:
            print(".", end="", flush=True)  # שקט
        return 1

    def on_mixed_audio_frame(self, frame: AudioFrame) -> int:
        # לפעמים האודיו מגיע לכאן במקום ל-playback
        data = bytes(frame.buffer)
        if any(b != 0 for b in data[:100]):
            print("M", end="", flush=True)  # M for Mixed
            self.worker.add_audio(data)
        return 1

    def on_playback_audio_frame_before_mixing(self, agora_local_user, channel_id, uid, frame):
        # לפעמים זה עובד למשתמשים בודדים
        # print(f"U{uid}", end="", flush=True)
        return 1

    def on_record_audio_frame(self, frame: AudioFrame) -> int:
        return 1

    def stop(self):
        self.worker.stop()