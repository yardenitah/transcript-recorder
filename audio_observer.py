import logging
import queue
import threading
import json
import os
import time
from websockets.sync.client import connect
from agora.rtc.audio_frame_observer import IAudioFrameObserver, AudioFrame

logger = logging.getLogger(__name__)


class PcmAudioObserver(IAudioFrameObserver):
    def __init__(self, save_to_file: bool = False):
        super(PcmAudioObserver, self).__init__()
        self.audio_queue: "queue.Queue[bytes]" = queue.Queue()
        self.running = True
        self.transcription_thread = threading.Thread(target=self.run_soniox_websocket)
        self.transcription_thread.daemon = True
        self.transcription_thread.start()

    def on_playback_audio_frame_before_mixing(self, agora_local_user, channel_id: str, uid: str,
                                              frame: AudioFrame) -> int:
        if self.running:
            data = bytes(frame.buffer)
            self.audio_queue.put(data)

            print(".", end="", flush=True)
        return 1

    def run_soniox_websocket(self):
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

        logger.info(f"Connecting to Soniox via WebSocket: {uri}")

        while self.running:
            try:
                with connect(uri) as websocket:
                    logger.info("\n✅ Connected to Soniox WebSocket!")
                    websocket.send(json.dumps(config))

                    def read_responses():
                        try:
                            for message in websocket:
                                response = json.loads(message)

                                if "error_code" in response:
                                    print(f"\n❌ Error: {response['error_message']}")
                                    break

                                tokens = response.get("tokens", [])
                                final_text = ""
                                partial_text = ""

                                for t in tokens:
                                    if t.get("is_final"):
                                        final_text += t.get("text", "")
                                    else:
                                        partial_text += t.get("text", "")

                                if final_text.strip():
                                    print(f"\n✅ FINAL: {final_text}")
                                elif partial_text.strip():
                                    print(f"\r⏳ Partial: {partial_text}", end="", flush=True)

                        except Exception as e:
                            logger.error(f"Error reading from WS: {e}")

                    reader_thread = threading.Thread(target=read_responses)
                    reader_thread.daemon = True
                    reader_thread.start()

                    silence_chunk = b'\x00' * 3200

                    while self.running:
                        try:
                            chunk = self.audio_queue.get(timeout=0.1)
                            websocket.send(chunk)
                        except queue.Empty:
                            websocket.send(silence_chunk)
                        except Exception:
                            break

            except Exception as e:
                logger.error(f"Connection failed: {e}")
                time.sleep(2)

    def stop(self):
        self.running = False
        self.transcription_thread.join(timeout=2)