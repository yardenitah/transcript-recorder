# audio_observer.py

import logging
import queue
import threading

from agora.rtc.audio_frame_observer import IAudioFrameObserver, AudioFrame
from soniox.transcribe_live import transcribe_stream
from soniox.speech_service import SpeechClient

logger = logging.getLogger(__name__)


class PcmAudioObserver(IAudioFrameObserver):
    """
    Audio frame observer that:
    1. Receives raw PCM frames from Agora.
    2. Pushes them into a queue (buffer).
    3. A background thread pulls from the queue and streams audio to Soniox.
    """

    def __init__(self, save_to_file: bool = False):
        super(PcmAudioObserver, self).__init__()
        self.save_to_file = save_to_file

        # Queue used as a buffer between Agora callbacks (producer)
        # and Soniox streaming thread (consumer).
        self.audio_queue: "queue.Queue[bytes]" = queue.Queue()

        # Flag to control background thread lifetime
        self.running = True

        # Background thread that talks with Soniox
        self.transcription_thread = threading.Thread(
            target=self.run_soniox_transcription
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
        """
        Called by Agora every ~10 ms with a new chunk of PCM audio.
        We must return quickly and avoid heavy work in this callback,
        so we only enqueue the frame and return.
        """
        if self.running:
            # frame.buffer is a memoryview; convert to immutable bytes
            data = bytes(frame.buffer)
            self.audio_queue.put(data)

        # 1 = continue processing
        return 1

    def audio_generator(self):
        """
        Generator used by Soniox: pulls audio chunks from the queue.
        """
        while self.running:
            try:
                chunk = self.audio_queue.get(timeout=1)
                yield chunk
            except queue.Empty:
                continue

    def run_soniox_transcription(self):
        """
        Background loop that connects to Soniox and prints recognized words.
        Requires SONIOX_API_KEY to be set in the environment.
        """
        logger.info("Starting Soniox transcription thread...")

        try:
            with SpeechClient() as client:
                logger.info("Connected to Soniox. Waiting for audio...")

                result_iter = transcribe_stream(
                    iter_audio=self.audio_generator(),
                    client=client,
                    # sample_rate=16000,      # Must match Agora PCM config
                    # num_audio_channels=1,
                )

                for result in result_iter:
                    for word in result.words:
                        text = word.text
                        print(f"🔤 Final Word: {text}")
                        # Here you can later send text to DB, queue, or HTTP callback

        except Exception as e:
            logger.error("Soniox error: %s", e)

    def stop(self):
        """
        Stop the background transcription thread and drain resources.
        """
        self.running = False
        self.transcription_thread.join(timeout=2)
