import logging
import queue
import threading
import json
import os
import time

# Use the synchronous version because we are inside a Thread
from websockets.sync.client import connect
from agora.rtc.audio_frame_observer import IAudioFrameObserver, AudioFrame

logger = logging.getLogger(__name__)


class PcmAudioObserver(IAudioFrameObserver):
    def __init__(self, save_to_file: bool = False):
        super(PcmAudioObserver, self).__init__()
        self.audio_queue: "queue.Queue[bytes]" = queue.Queue()
        self.running = True

        # Background thread that manages the WebSocket connection to Soniox
        self.transcription_thread = threading.Thread(
            target=self.run_soniox_websocket
        )
        self.transcription_thread.daemon = True
        self.transcription_thread.start()

    def on_playback_audio_frame_before_mixing(
            self,
            agora_local_user,
            channel_id: str,
            uid: str,
            frame: AudioFrame,
    ) -> int:
        """Receives audio from Agora and pushes it into the queue"""
        if self.running:
            data = bytes(frame.buffer)
            self.audio_queue.put(data)
        return 1

    def run_soniox_websocket(self):
        """
        The winning logic: a direct WebSocket connection
        (exactly like the working implementation in main.py)
        """
        api_key = os.environ.get("SONIOX_API_KEY")
        if not api_key:
            logger.error("❌ Missing SONIOX_API_KEY")
            return

        # The exact same endpoint
        uri = "wss://stt-rt.soniox.com/transcribe-websocket"

        # The exact same JSON configuration (copied from the working code)
        config = {
            "api_key": api_key,
            "model": "stt-rt-preview",  # or stt-rt-v3, whichever worked for you
            "audio_format": "pcm_s16le",
            "sample_rate": 16000,
            "num_channels": 1,
            "enable_speaker_diarization": True,
            # Added for Hebrew support if the model supports it
            "enable_language_identification": True,
            "language_hints": ["he"]
        }

        logger.info(f"Connecting to Soniox via WebSocket: {uri}")

        while self.running:
            try:
                # Use synchronous connect (not async)
                with connect(uri) as websocket:
                    logger.info("✅ Connected to Soniox WebSocket!")

                    # 1. Send the configuration
                    websocket.send(json.dumps(config))

                    # 2. Internal function to read responses
                    # (so audio sending is not blocked)
                    def read_responses():
                        try:
                            for message in websocket:
                                response = json.loads(message)

                                # Error handling
                                if "error_code" in response:
                                    logger.error(f"Soniox Error: {response['error_message']}")
                                    break

                                # Extract transcript text
                                tokens = response.get("tokens", [])
                                final_text = ""
                                for t in tokens:
                                    if t.get("is_final"):
                                        final_text += t.get("text", "")

                                if final_text.strip():
                                    # Log output to prove it works
                                    print(f"🎤 TRANSCRIPT: {final_text}")
                                    logger.info(f"🎤 TRANSCRIPT: {final_text}")

                        except Exception as e:
                            logger.error(f"Error reading from WS: {e}")

                    # Start the reader in a separate thread
                    reader_thread = threading.Thread(target=read_responses)
                    reader_thread.daemon = True
                    reader_thread.start()

                    # 3. Audio sending loop
                    # This replaces the audio_generator
                    silence_chunk = b'\x00' * 3200

                    while self.running:
                        try:
                            # Pull audio from the queue (coming from Agora)
                            chunk = self.audio_queue.get(timeout=0.1)
                            websocket.send(chunk)
                        except queue.Empty:
                            # Keep-alive: send silence to prevent disconnect
                            websocket.send(silence_chunk)
                        except Exception as e:
                            logger.error(f"WebSocket send error: {e}")
                            break

            except Exception as e:
                logger.error(f"Connection failed: {e}")
                time.sleep(2)  # Retry after 2 seconds

    def stop(self):
        self.running = False
        self.transcription_thread.join(timeout=2)
