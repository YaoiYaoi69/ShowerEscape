from __future__ import annotations

from array import array
from collections import deque
from math import sqrt
import os
from pathlib import Path
from queue import Empty, Queue
import sys
from threading import Event, Thread
from typing import Iterator, Protocol, TextIO, TypeAlias


VoiceEvent: TypeAlias = tuple[str, str | None]
VoiceCommand: TypeAlias = tuple[str, str | None]


class AudioOutput(Protocol):
    audio: object


class AudioChunk(Protocol):
    output: AudioOutput


class SpeechPipeline(Protocol):
    def __call__(
        self,
        text: str,
        voice: str,
        speed: float = 1,
    ) -> Iterator[AudioChunk]: ...


class CudaRuntime(Protocol):
    def is_available(self) -> bool: ...

    def mem_get_info(self) -> tuple[int, int]: ...


class TorchRuntime(Protocol):
    cuda: CudaRuntime


SAMPLE_RATE = 16_000
FRAME_SIZE = 320
FRAME_SECONDS = FRAME_SIZE / SAMPLE_RATE
SILENCE_SECONDS = 0.7
MIN_SPEECH_SECONDS = 0.25
MAX_SPEECH_SECONDS = 20
SPEECH_SPEED = 1.2
MIN_CUDA_FREE_BYTES = 2 * 1024**3
_kokoro_log_sink: TextIO | None = None


def _prepare_kokoro_logging() -> None:
    global _kokoro_log_sink
    if sys.stderr is None:
        if _kokoro_log_sink is None:
            _kokoro_log_sink = open(os.devnull, "w", encoding="utf-8")
        sys.stderr = _kokoro_log_sink


def _select_tts_device(torch_module: TorchRuntime) -> str:
    cuda = torch_module.cuda
    if not cuda.is_available():
        return "cpu"
    free_bytes, _total_bytes = cuda.mem_get_info()
    return "cuda" if free_bytes >= MIN_CUDA_FREE_BYTES else "cpu"


def pcm_rms(audio: bytes) -> float:
    samples = array("h")
    samples.frombytes(audio)
    if not samples:
        return 0
    return sqrt(sum(sample * sample for sample in samples) / len(samples))


class VoiceChat:
    def __init__(self, project_dir: Path, events: Queue[VoiceEvent]) -> None:
        voice_dir = project_dir / ".runtime" / "voice"
        self.model_path = voice_dir / "whisper-base"
        self.kokoro_model_path = voice_dir / "kokoro"
        self.events = events
        self.commands: Queue[VoiceCommand] = Queue()
        self._stop = Event()
        self._paused = Event()
        self._speech_cancelled = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()

    def listen(self) -> None:
        self._paused.clear()
        self._speech_cancelled.clear()
        self.commands.put(("listen", None))

    def pause(self) -> None:
        self._paused.set()
        self.commands.put(("pause", None))

    def speak(self, text: str) -> None:
        self._paused.set()
        self._speech_cancelled.clear()
        self.commands.put(("speak", text))

    def cancel_speech(self) -> None:
        self._speech_cancelled.set()

    def stop(self) -> None:
        self._stop.set()
        self._paused.set()
        self.commands.put(("stop", None))
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1)

    def _run(self) -> None:
        try:
            import numpy as np
            import sounddevice as sd
            import torch
            from faster_whisper import WhisperModel
            _prepare_kokoro_logging()
            from kokoro import KModel, KPipeline

            if not (self.model_path / "model.bin").is_file():
                raise FileNotFoundError(
                    f"Das lokale Spracherkennungsmodell fehlt: {self.model_path}"
                )
            kokoro_config = self.kokoro_model_path / "config.json"
            kokoro_weights = self.kokoro_model_path / "kokoro-v1_0.pth"
            kokoro_voice = self.kokoro_model_path / "voices" / "af_heart.pt"
            if not kokoro_config.is_file() or not kokoro_weights.is_file():
                raise FileNotFoundError(
                    f"Das lokale Kokoro-Sprachmodell fehlt: {self.kokoro_model_path}"
                )
            if not kokoro_voice.is_file():
                raise FileNotFoundError(
                    f"Die lokale Kokoro-Stimme fehlt: {kokoro_voice}"
                )

            recognizer = WhisperModel(
                str(self.model_path),
                device="cpu",
                compute_type="int8",
                cpu_threads=4,
                num_workers=1,
                local_files_only=True,
            )
            tts_device = _select_tts_device(torch)
            tts_model = KModel(
                repo_id="hexgrad/Kokoro-82M",
                config=str(kokoro_config),
                model=str(kokoro_weights),
            ).to(tts_device).eval()
            voice = KPipeline(
                lang_code="a",
                repo_id="hexgrad/Kokoro-82M",
                model=tts_model,
            )
            voice.load_voice(str(kokoro_voice))
            sd.check_input_settings(samplerate=SAMPLE_RATE, channels=1, dtype="int16")
            sd.check_output_settings(samplerate=24_000, channels=1, dtype="float32")
            self.events.put(("ready", tts_device))

            while not self._stop.is_set():
                command, text = self.commands.get()
                if command == "stop":
                    break
                if command == "speak" and text:
                    self._speak(voice, str(kokoro_voice), text)
                    self.events.put(("spoken", None))
                elif command == "listen":
                    self.events.put(("listening", None))
                    utterance = self._record_utterance()
                    if utterance is None:
                        if not self._paused.is_set() and not self._stop.is_set():
                            self.commands.put(("listen", None))
                        continue
                    audio = np.frombuffer(utterance, dtype="<i2").astype(np.float32)
                    audio /= 32768.0
                    segments, _ = recognizer.transcribe(
                        audio,
                        beam_size=3,
                        condition_on_previous_text=False,
                        temperature=0,
                        vad_filter=False,
                    )
                    if self._paused.is_set() or self._stop.is_set():
                        continue
                    transcript = " ".join(
                        segment.text.strip()
                        for segment in segments
                        if segment.text.strip()
                    ).strip()
                    if transcript:
                        self.events.put(("transcript", transcript))
                    elif not self._paused.is_set() and not self._stop.is_set():
                        self.events.put(("listening", None))
                        self.commands.put(("listen", None))
        except Exception as error:
            if not self._stop.is_set():
                self.events.put(("error", f"{type(error).__name__}: {error}"))

    def _record_utterance(self) -> bytes | None:
        import sounddevice as sd

        pre_roll: deque[bytes] = deque(maxlen=12)
        frames: list[bytes] = []
        noise_level = 100.0
        speech_seconds = 0.0
        silence_seconds = 0.0
        interrupted = False

        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            blocksize=FRAME_SIZE,
            channels=1,
            dtype="int16",
        ) as stream:
            while not self._stop.is_set() and not self._paused.is_set():
                try:
                    command, _ = self.commands.get_nowait()
                except Empty:
                    pass
                else:
                    if command == "stop":
                        self._stop.set()
                        interrupted = True
                        break
                    if command in {"pause", "speak"}:
                        self._paused.set()
                        interrupted = True
                        break

                audio, _overflowed = stream.read(FRAME_SIZE)
                frame = bytes(audio)
                level = pcm_rms(frame)
                threshold = max(280.0, noise_level * 2.5)

                if level >= threshold:
                    if not frames:
                        frames.extend(pre_roll)
                    frames.append(frame)
                    speech_seconds += FRAME_SECONDS
                    silence_seconds = 0
                elif frames:
                    frames.append(frame)
                    silence_seconds += FRAME_SECONDS
                    if silence_seconds >= SILENCE_SECONDS:
                        break
                else:
                    noise_level = noise_level * 0.97 + level * 0.03
                    pre_roll.append(frame)

                if len(frames) * FRAME_SECONDS >= MAX_SPEECH_SECONDS:
                    break

        if interrupted or speech_seconds < MIN_SPEECH_SECONDS:
            return None
        return b"".join(frames)

    def _speak(self, voice: SpeechPipeline, voice_path: str, text: str) -> None:
        import numpy as np
        import sounddevice as sd

        audio_chunks = []
        for chunk in voice(
            text,
            voice=voice_path,
            speed=SPEECH_SPEED,
        ):
            if self._speech_cancelled.is_set() or self._stop.is_set():
                return
            audio_chunks.append(chunk.output.audio.numpy())

        if not audio_chunks or self._speech_cancelled.is_set() or self._stop.is_set():
            return

        audio = np.concatenate(audio_chunks)
        with sd.OutputStream(
            samplerate=24_000,
            channels=1,
            dtype="float32",
        ) as stream:
            stream.write(audio)
