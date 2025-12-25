import logging, queue, threading, json, os, time, sys

from websockets.sync.client import connect
from agora.rtc.audio_frame_observer import IAudioFrameObserver

# LOGGING SETUP
# logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
# logger = logging.getLogger("AUDIO_DEBUG")

logging.basicConfig(stream=sys.stdout, level=logging.INFO) # Change from DEBUG to INFO
logger = logging.getLogger("AUDIO_DEBUG")
logger.setLevel(logging.INFO)
logging.getLogger("websockets").setLevel(logging.WARNING)

class SonioxWorker:
    def __init__(self, worker_id="Mixed"):
        self.worker_id = worker_id
        self.audio_queue: "queue.Queue[bytes]" = queue.Queue()
        self.running = True
        self.has_frames = False  # becomes True after first real frame; avoids sending when alone
        logger.debug(f"🔹 [Worker {self.worker_id}] Init")  #
        self.thread = threading.Thread(target=self._connect_and_stream, daemon=True)
        self.thread.start()

    # def _run_websocket_loop(self):
    #     api_key = os.environ.get("SONIOX_API_KEY")
    #     if not api_key:
    #         logger.error("❌ [Worker] No API Key")
    #         return
    #
    #     uri = "wss://stt-rt.soniox.com/transcribe-websocket"
    #     config = {
    #         "api_key": api_key,
    #         "model": "stt-rt-preview",
    #         "audio_format": "pcm_s16le",
    #         "sample_rate": 16000,
    #         "num_channels": 1,
    #         "enable_speaker_diarization": False,
    #         "enable_language_identification": True,
    #         "language_hints": ["he"]
    #     }
    #     while self.running:
    #         try:
    #             with connect(uri, ping_interval=None) as websocket:
    #                 logger.info("✅ [Worker] Connected to Soniox!")
    #                 websocket.send(json.dumps(config))
    #
    #                 def read_task():
    #                     logger.info("🤘 [Worker][Messiah] We're in read_task now")
    #                     while True:
    #                         try:
    #                             for message in websocket:
    #                                 response = json.loads(message)
    #                                 tokens = response.get("tokens", [])
    #
    #                                 if not tokens:
    #                                     continue
    #
    #                                 final_sentence = ""
    #                                 partial_sentence = ""
    #                                 for t in tokens:
    #                                     text = t.get("text", "")
    #                                     if t.get("is_final", False):
    #                                         final_sentence += text
    #                                     else:
    #                                         partial_sentence += text
    #
    #                                 # 1. If we have a final (committed) sentence - print it permanently (new line)
    #                                 if final_sentence.strip():
    #                                     print(f"\r🎤 [{self.worker_id}]: {final_sentence}")  # Use \r to return to start of line and spaces to overwrite any previous partial text
    #                                 # 2. If we have partial text (instant feedback) - print on the same updating line
    #                                 elif partial_sentence.strip():
    #                                     print(f"\r⏳ [{self.worker_id}]: {partial_sentence}", end="", flush=True) # end="\r" keeps the cursor at the start of the line without creating a new line (animation effect)
    #
    #                         except Exception as err:
    #                             logger.error(f"❌ [Reader] Error: {err}")
    #                             break
    #
    #                 reader = threading.Thread(target=read_task, daemon=True)
    #                 reader.start()
    #
    #                 silence = b'\x00' * 640
    #                 while self.running:
    #                     try:
    #                         chunk = self.audio_queue.get(timeout=0.02)
    #                         # Log actual data sent (First 10 bytes)
    #                         # first_bytes = chunk[:10].hex()
    #                         # logger.debug(f"⚡ [Worker] Sending {len(chunk)} bytes | Header: {first_bytes}")
    #                         websocket.send(chunk)
    #                     except queue.Empty:
    #                         # If we never received frames, stay quiet (do not broadcast)
    #                         if not self.has_frames:
    #                             time.sleep(0.05)
    #                             continue
    #                         # Otherwise send silence to keep stream alive
    #                         logger.debug("💤 [Worker] Sending Silence (Queue Empty)")
    #                         websocket.send(silence)
    #                     except Exception as e:
    #                         logger.error(f"❌ [Worker] Loop Error: {e}")
    #                         break
    #
    #         except Exception as e:
    #             logger.error(f"⚠️ [Worker] Connection Fail: {e}")
    #             time.sleep(3)

    # 1. READ LOOP (Background Thread)
    def _read_loop(self, websocket):
        """Reads JSON responses from Soniox and prints transcripts."""
        logger.info(f"🤘 [Worker {self.worker_id}] Reader started")
        try:
            for message in websocket:
                if not self.running:
                    break
                try:
                    response = json.loads(message)
                    tokens = response.get("tokens", [])
                    if not tokens:
                        continue

                    final_sentence = ""
                    partial_sentence = ""

                    for t in tokens:
                        text = t.get("text", "")
                        if t.get("is_final", False):
                            final_sentence += text
                        else:
                            partial_sentence += text

                    # Print logic:
                    # Final sentence -> New line
                    if final_sentence.strip():
                        print(f"\r🎤 [{self.worker_id}]: {final_sentence}                                ")
                    # Partial sentence -> Update same line (Streaming effect)
                    elif partial_sentence.strip():
                        print(f"\r⏳ [{self.worker_id}]: {partial_sentence}", end="", flush=True)

                except json.JSONDecodeError:
                    logger.error(f"❌ [Reader {self.worker_id}] Invalid JSON")
        except Exception as e:
            # Only log if it's not a normal shutdown
            if self.running:
                logger.error(f"❌ [Reader {self.worker_id}] Error: {e}")

    # 2. WRITE LOOP (Main Worker Thread)
    def _write_loop(self, websocket):
        """Sends audio chunks from queue to Soniox."""
        silence = b'\x00' * 640
        while self.running:
            try:
                chunk = self.audio_queue.get(timeout=0.02)
                websocket.send(chunk)
            except queue.Empty:
                if not self.has_frames:
                    time.sleep(0.05)
                    continue
                # Send silence to keep connection alive if queue is empty
                websocket.send(silence)
            except Exception as e:
                logger.error(f"❌ [Writer {self.worker_id}] Error: {e}")
                break

    # 3. CONNECTION MANAGER
    def _connect_and_stream(self):
        """Main loop: Reconnects on failure and manages the session."""
        api_key = os.environ.get("SONIOX_API_KEY")
        if not api_key:
            logger.error(f"❌ [Worker {self.worker_id}] No API Key")
            return

        uri = "wss://stt-rt.soniox.com/transcribe-websocket"
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

        while self.running:
            try:
                logger.info(f"🔄 [Worker {self.worker_id}] Connecting...")
                with connect(uri, ping_interval=None) as websocket:
                    logger.info(f"✅ [Worker {self.worker_id}] Connected!")
                    # A. Handshake
                    websocket.send(json.dumps(config))
                    # B. Start Reader (in background)
                    reader_thread = threading.Thread(target=self._read_loop, args=(websocket,), daemon=True)
                    reader_thread.start()
                    # C. Start Writer (blocks here until error/stop)
                    self._write_loop(websocket)

            except Exception as e:
                logger.error(f"⚠️ [Worker {self.worker_id}] Connection Failed: {e}")
                time.sleep(3)  # Retry delay

    def mark_active(self):
        """Called when we process the first audio frame."""
        self.has_frames = True

    def add_audio(self, data: bytes):
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


class PcmAudioObserver(IAudioFrameObserver):
    def __init__(self, save_to_file: bool = False, separate_streams: bool = True):
        super(PcmAudioObserver, self).__init__()
        self.separate_streams = separate_streams
        self.workers = {}
        if not self.separate_streams:
            self.workers["Mixed"] = SonioxWorker("Mixed")

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

    def _process_frame(self, uid_key, frame):
        logger.debug(f"😎😎😎Start _process_frame function using {uid_key}, {frame}")
        try:
            data = bytes(frame.buffer) # 1. Extract raw PCM bytes from the frame
            is_silence = all(b == 0 for b in data) # Detailed Silence Check ( Check if the frame contains only zeros)
            if is_silence:
                return 1 # Silence filtering. It saves bandwidth for Soniox. Return 1 to keep the stream alive

            self.frame_count += 1
            # If in 'Separate' mode -> Use the user's UID (e.g., "123").
            # If in 'Mixed' mode -> Use the static label "Mixed".
            target_key = uid_key if self.separate_streams else "Mixed"
            # If we see a NEW user in separate mode, spawn a dedicated Soniox connection for them.
            if self.separate_streams and target_key not in self.workers:
                logger.info(f"🆕 [Observer] New speaker detected: {target_key}")
                self.workers[target_key] = SonioxWorker(target_key)
            # 5. Dispatch Audio
            # Send the audio chunk to the specific worker's queue.
            # The check verifies the worker exists (handled in init for Mixed, or just above for Separate).
            if target_key in self.workers:
                self.workers[target_key].add_audio(data)
                self.workers[target_key].mark_active()

            logger.debug(f"✅ [Observer] Successfully routed {len(data)} bytes >> Worker[{target_key}]")
            self.last_frame_ts = time.time()
            return 1
        except Exception as e:
            logger.error(f"❌ [Observer] Processing Error: {e}")
            return 1

    # --- CALLBACKS WITH MAX LOGGING ---

    def on_playback_audio_frame(self, agora_local_user, channelId, frame):
        logger.debug("🔵 Callback: on_playback_audio_frame called")
        return 0

    def on_record_audio_frame(self, agora_local_user, channelId, frame):
        logger.debug("🔴 Callback: on_record_audio_frame called")
        return 0

    def on_mixed_audio_frame(self, agora_local_user, channelId, frame):
        """ Mixed Audio: Contains all speakers combined. We only use this if separate_streams is FALSE  """
        logger.debug("🟣 Callback: on_mixed_audio_frame TRIGGERED")
        if not self.separate_streams:
            return self._process_frame("Mixed", frame)
        return 0


    def on_playback_audio_frame_before_mixing(self, agora_local_user, channelId, uid, frame, vad_result_state, vad_result_bytearray):
        # Role: To receive the raw audio coming from the remote user (me in the browser), before mixing it with the other users.
        """ Individual Audio: Raw stream per user. We only use this if separate_streams is TRUE (Default). """
        if self.separate_streams:
            logger.debug(f"🔥🔥🔥 [CALLBACK] BeforeMixing Triggered! and separate_streams is True. the UID={uid}")
            return self._process_frame(str(uid), frame)
        logger.debug(f"🔥 [CALLBACK] BeforeMixing Triggered! and separate_streams is False. the UID={uid}")
        return 0


    def on_ear_monitoring_audio_frame(self, agora_local_user, frame):
        return 1

    def stop(self):
        """ Gracefully stop all active Soniox workers. """
        logger.info(f"🛑 [Observer] Stopping {len(self.workers)} active workers...")
        for uid, worker in self.workers.items():
            worker.stop()



    # def on_playback_audio_frame_before_mixing(self, agora_local_user, channelId, uid, frame, vad_result_state, vad_result_bytearray):
    #     # Role: To receive the raw audio coming from the remote user (me in the browser), before mixing it with the other users.
    #     logger.debug(f"🔥🔥🔥 [CALLBACK] BeforeMixing Triggered! UID={uid}")
    #     return self._process_frame(f"before_mixing_u{uid}", frame)
    #
