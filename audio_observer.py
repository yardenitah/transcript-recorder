import logging
import queue
import threading
import json
import os
import time
import sys

from websockets.sync.client import connect
from agora.rtc.audio_frame_observer import IAudioFrameObserver

# LOGGING SETUP
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logger = logging.getLogger("AUDIO_DEBUG")


class SonioxMixedWorker:
    def __init__(self):
        self.audio_queue: "queue.Queue[bytes]" = queue.Queue()
        self.running = True
        self.has_frames = False  # becomes True after first real frame; avoids sending when alone
        logger.debug("🔹 [Worker] Init")
        self.thread = threading.Thread(target=self._run_websocket_loop, daemon=True)
        self.thread.start()

    def mark_active(self):
        """Called when we process the first audio frame."""
        self.has_frames = True

    def add_audio(self, data: bytes, source: str):
        # Monitor Queue Size
        qsize = self.audio_queue.qsize()
        if qsize % 50 == 0 and qsize > 0:
            logger.debug(f"📊 [Queue] Current size: {qsize}")

        if qsize > 2000:
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                logger.debug(f"🫙 Queue is empty. Retrying")
                pass
        self.audio_queue.put(data)

    def stop(self):
        self.running = False
        self.thread.join(timeout=1)

    def _run_websocket_loop(self):
        api_key = os.environ.get("SONIOX_API_KEY")
        if not api_key:
            logger.error("❌ [Worker] No API Key")
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

        while self.running:
            try:
                logger.info(f"🔄 [Worker] Connecting to Soniox...")
                with connect(uri, ping_interval=None) as websocket:
                    logger.info("✅ [Worker] Connected to Soniox!")
                    websocket.send(json.dumps(config))

                    def read_task():
                        while True:
                            try:
                                for message in websocket:
                                    response = json.loads(message)
                                    # Log only if meaningful
                                    if response.get("tokens"):
                                        logger.info(f"📝 [Soniox] {message}")

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

                    silence = b'\x00' * 640

                    while self.running:
                        try:
                            chunk = self.audio_queue.get(timeout=0.02)
                            # Log actual data sent (First 10 bytes)
                            first_bytes = chunk[:10].hex()
                            logger.debug(f"⚡ [Worker] Sending {len(chunk)} bytes | Header: {first_bytes}")
                            websocket.send(chunk)
                        except queue.Empty:
                            # If we never received frames, stay quiet (do not broadcast)
                            if not self.has_frames:
                                time.sleep(0.05)
                                continue
                            # Otherwise send silence to keep stream alive
                            logger.debug("💤 [Worker] Sending Silence (Queue Empty)")
                            websocket.send(silence)
                        except Exception as e:
                            logger.error(f"❌ [Worker] Loop Error: {e}")
                            break

            except Exception as e:
                logger.error(f"⚠️ [Worker] Connection Fail: {e}")
                time.sleep(3)


class PcmAudioObserver(IAudioFrameObserver):
    def __init__(self, save_to_file: bool = False):
        super(PcmAudioObserver, self).__init__()
        self.worker = SonioxMixedWorker()
        self.frame_count = 0
        logger.info("✅ [Observer] Initialized and Ready")
        # Monitor if we ever get frames; helps detect missing subscription/remote audio
        self.last_frame_ts = time.time()
        self._monitor_thread = threading.Thread(target=self._monitor_frames, daemon=True)
        self._monitor_thread.start()

    def get_status(self):
        """Expose health info for debugging."""
        now = time.time()
        return {
            "frame_count": self.frame_count,
            "last_frame_ts": self.last_frame_ts,
            "seconds_since_last_frame": now - self.last_frame_ts,
        }

    def _monitor_frames(self):
        while True:
            time.sleep(5)
            elapsed = time.time() - self.last_frame_ts
            if elapsed > 5:
                logger.warning(
                    f"⏳ [Observer] No audio frames received for {int(elapsed)}s "
                    f"(check remote publishing + subscriptions)"
                )

    def _process_frame(self, name, frame):
        logger.debug(f"😎😎😎Start _process_frame function using {name}, {frame}")
        try:
            self.frame_count += 1
            data = bytes(frame.buffer)

            # Detailed Silence Check
            is_silence = all(b == 0 for b in data)
            frame_type = "🔇 SILENCE" if is_silence else "🔊 AUDIO"

            # LOGS: Only log AUDIO or 1 out of 100 frames to save terminal space
            if not is_silence:
                logger.info(f"👂 [Observer] GOT AUDIO! Source: {name} | Size: {len(data)}")
            elif self.frame_count % 100 == 0:
                logger.debug(f"👂 [Observer] Source: {name} | {frame_type} | (Alive check)")

            self.worker.add_audio(data, name)
            # Mark that we have actual frames; enables silence padding when needed
            self.worker.mark_active()
            self.last_frame_ts = time.time()
            return 1
        except Exception as e:
            logger.error(f"❌ [Observer] Processing Error: {e}")
            return 1

    # --- CALLBACKS WITH MAX LOGGING ---

    def on_playback_audio_frame(self, agora_local_user, channelId, frame):
        logger.debug("🔵 Callback: on_playback_audio_frame called")
        return self._process_frame("on_playback", frame)

    def on_record_audio_frame(self, agora_local_user, channelId, frame):
        logger.debug("🔴 Callback: on_record_audio_frame called")
        return self._process_frame("on_record", frame)

    def on_mixed_audio_frame(self, agora_local_user, channelId, frame):
        # If this logs, Mixed audio is working
        logger.debug("🟣 Callback: on_mixed_audio_frame TRIGGERED")
        return self._process_frame("on_mixed", frame)

    def on_playback_audio_frame_before_mixing(self, agora_local_user, channelId, uid, frame, vad_result_state, vad_result_bytearray):
        # Role: To receive the raw audio coming from the remote user (me in the browser), before mixing it with the other users.
        logger.debug(f"🔥🔥🔥 [CALLBACK] BeforeMixing Triggered! UID={uid}")
        return self._process_frame(f"before_mixing_u{uid}", frame)

    # def on_playback_audio_frame_before_mixing(self, agora_local_user, channelId, uid, frame, vad_result_state,vad_result_bytearray):        # If this logs, we are getting remote user audio!
    #     # Role: To receive the raw audio coming from the remote user (me in the browser), before mixing it with the other users.
    #     logger.debug(f"🔥 [CALLBACK] BeforeMixing Triggered! UID={uid}")
    #     return self._process_frame(f"before_mixing_u{uid}", frame)

    def on_ear_monitoring_audio_frame(self, agora_local_user, frame):
        return 1

    def stop(self):
        self.worker.stop()


