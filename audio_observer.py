import logging
import queue
import threading
import json
import os
import time
from typing import Dict

# Synchronous WebSocket library
from websockets.sync.client import connect
from agora.rtc.audio_frame_observer import IAudioFrameObserver, AudioFrame

logger = logging.getLogger(__name__)

# --- Global Label Management (similar to Node.js logic) ---
uid_to_label: Dict[str, str] = {}
next_speaker_idx = 1
label_lock = threading.Lock()


def get_label_for_uid(uid: str) -> str:
    global next_speaker_idx
    with label_lock:
        if uid not in uid_to_label:
            uid_to_label[uid] = f"Speaker {next_speaker_idx}"
            next_speaker_idx += 1
        return uid_to_label[uid]


# --- Class handling a single user (one dedicated WS connection) ---
class SonioxWorker:
    def __init__(self, uid: str, label: str):
        self.uid = uid
        self.label = label
        self.audio_queue: "queue.Queue[bytes]" = queue.Queue()
        self.running = True

        # Start a dedicated Thread for this user
        self.thread = threading.Thread(target=self._run_websocket_loop, daemon=True)
        self.thread.start()

    def add_audio(self, data: bytes):
        """ Receives an audio chunk and pushes it to this user's queue """
        self.audio_queue.put(data)

    def stop(self):
        self.running = False
        self.thread.join(timeout=1)

    def _run_websocket_loop(self):
        api_key = os.environ.get("SONIOX_API_KEY")
        if not api_key:
            logger.error(f"[{self.label}] Missing API Key")
            return

        uri = "wss://stt-rt.soniox.com/transcribe-websocket"

        # Configuration per individual user
        # Note: diarization = False because this stream contains only one user!
        config = {
            "api_key": api_key,
            "model": "stt-rt-preview",
            "audio_format": "pcm_s16le",
            "sample_rate": 16000,
            "num_channels": 1,
            "enable_speaker_diarization": False,
            "enable_language_identification": True,
            "language_hints": ["he"]
        }

        logger.info(f"🚀 [{self.label}] Starting Worker for UID={self.uid}")

        while self.running:
            try:
                with connect(uri) as websocket:
                    logger.info(f"✅ [{self.label}] Connected to Soniox!")
                    websocket.send(json.dumps(config))

                    # Thread for reading responses (to avoid blocking the send loop)
                    def read_task():
                        try:
                            for message in websocket:
                                response = json.loads(message)

                                # Process transcript
                                tokens = response.get("tokens", [])
                                final_text = ""
                                partial_text = ""

                                for t in tokens:
                                    if t.get("is_final"):
                                        final_text += t.get("text", "")
                                    else:
                                        partial_text += t.get("text", "")

                                if final_text.strip():
                                    # Print final text with the speaker label
                                    print(f"\n🎤 [{self.label}]: {final_text}")
                                    logger.info(f"TRANSCRIPT [{self.label}]: {final_text}")

                                # Optional: Print partials (commented out to reduce noise)
                                # elif partial_text.strip():
                                #    print(f"\r⏳ [{self.label}] {partial_text}", end="", flush=True)

                        except Exception as e:
                            logger.error(f"[{self.label}] Read Error: {e}")

                    reader = threading.Thread(target=read_task, daemon=True)
                    reader.start()

                    # Audio sending loop
                    silence = b'\x00' * 3200
                    while self.running:
                        try:
                            chunk = self.audio_queue.get(timeout=0.1)
                            websocket.send(chunk)
                        except queue.Empty:
                            websocket.send(silence)  # Keep alive
                        except Exception:
                            break

            except Exception as e:
                logger.error(f"[{self.label}] Connection failed: {e}")
                time.sleep(3)


# --- Main Observer (Manages the Workers) ---
class PcmAudioObserver(IAudioFrameObserver):
    def __init__(self, save_to_file: bool = False):
        super(PcmAudioObserver, self).__init__()
        # Dictionary holding: UID -> SonioxWorker
        self.workers: Dict[str, SonioxWorker] = {}
        self.lock = threading.Lock()

    def on_playback_audio_frame_before_mixing(
            self,
            agora_local_user,
            channel_id: str,
            uid: str,  # Agora provides the UID here
            frame: AudioFrame,
    ) -> int:

        # Convert UID to String (sometimes it arrives as int)
        str_uid = str(uid)

        # Skip empty audio or SDK initialization artifacts
        if str_uid == "0" or str_uid == "None":
            return 1

        data = bytes(frame.buffer)

        # Thread-safe Worker management
        with self.lock:
            if str_uid not in self.workers:
                # New user detected! Assign a label and start a worker
                label = get_label_for_uid(str_uid)
                new_worker = SonioxWorker(str_uid, label)
                self.workers[str_uid] = new_worker
                print(f"\n👋 New participant detected: {label} (UID: {str_uid})")

            # Route audio to the specific worker for this UID
            self.workers[str_uid].add_audio(data)

        return 1

    def stop(self):
        """ Stop all workers """
        with self.lock:
            for uid, worker in self.workers.items():
                worker.stop()
            self.workers.clear()