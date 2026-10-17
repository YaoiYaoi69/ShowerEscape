import unittest
from io import StringIO
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

from voice_chat import (
    FRAME_SIZE,
    SPEECH_SPEED,
    VoiceChat,
    MIN_CUDA_FREE_BYTES,
    _prepare_kokoro_logging,
    _select_tts_device,
    pcm_rms,
)


class VoiceChatTests(unittest.TestCase):
    def test_pcm_rms_is_zero_for_silence(self):
        self.assertEqual(pcm_rms(bytes(FRAME_SIZE * 2)), 0)

    def test_pcm_rms_detects_voice_energy(self):
        voice_frame = b"\xe8\x03" * FRAME_SIZE

        self.assertEqual(pcm_rms(voice_frame), 1000)

    def test_kokoro_logging_has_a_sink_without_stderr(self):
        sink = StringIO()
        with (
            patch("voice_chat.sys.stderr", None),
            patch("voice_chat._kokoro_log_sink", sink),
        ):
            _prepare_kokoro_logging()

            self.assertIs(sys.stderr, sink)

    def test_speech_speed_is_faster_than_default(self):
        self.assertGreater(SPEECH_SPEED, 1.0)

    def test_selects_cuda_when_available_memory_meets_reserve(self):
        cuda = SimpleNamespace(
            is_available=lambda: True,
            mem_get_info=lambda: (MIN_CUDA_FREE_BYTES, 8 * 1024**3),
        )

        self.assertEqual(_select_tts_device(SimpleNamespace(cuda=cuda)), "cuda")

    def test_selects_cpu_when_cuda_memory_is_below_reserve(self):
        cuda = SimpleNamespace(
            is_available=lambda: True,
            mem_get_info=lambda: (MIN_CUDA_FREE_BYTES - 1, 8 * 1024**3),
        )

        self.assertEqual(_select_tts_device(SimpleNamespace(cuda=cuda)), "cpu")

    def test_selects_cpu_when_cuda_is_unavailable(self):
        cuda = SimpleNamespace(is_available=lambda: False)

        self.assertEqual(_select_tts_device(SimpleNamespace(cuda=cuda)), "cpu")

    def test_speech_chunks_are_synthesized_before_continuous_playback(self):
        generated = []
        chunks = [
            MagicMock(output=MagicMock(audio=MagicMock(
                numpy=MagicMock(return_value=np.full(4, value, dtype=np.float32))
            )))
            for value in (0.25, 0.5, 0.75)
        ]

        def synthesize(text, voice, speed):
            self.assertEqual(text, "First. Second. Third.")
            self.assertEqual(voice, "af_heart.pt")
            self.assertEqual(speed, SPEECH_SPEED)
            for chunk in chunks:
                generated.append(chunk)
                yield chunk

        audio_stream = MagicMock()
        audio_stream.__enter__ = MagicMock(return_value=audio_stream)
        audio_stream.__exit__ = MagicMock(return_value=None)
        chat = VoiceChat.__new__(VoiceChat)
        chat._speech_cancelled = MagicMock(is_set=MagicMock(return_value=False))
        chat._stop = MagicMock(is_set=MagicMock(return_value=False))

        with patch("sounddevice.OutputStream", return_value=audio_stream):
            chat._speak(synthesize, "af_heart.pt", "First. Second. Third.")

        audio_stream.write.assert_called_once()
        np.testing.assert_array_equal(
            audio_stream.write.call_args.args[0],
            np.array([0.25] * 4 + [0.5] * 4 + [0.75] * 4, dtype=np.float32),
        )
        self.assertEqual(len(generated), 3)


if __name__ == "__main__":
    unittest.main()
