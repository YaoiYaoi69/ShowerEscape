from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
from threading import Lock
from time import monotonic, sleep
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

from emotion_tags import (
    BARE_EMOTION_PATTERN,
    TAG_PATTERN,
    normalize_tagged_response,
    parse_emotion_tags,
)


MAX_HISTORY_MESSAGES = 8
MAX_RESPONSE_TOKENS = 96
MODEL_ALIAS = "shower-guardian-yumenko"
KEY_GIVEN_MARKER = "[[KEY_GIVEN]]"


@dataclass(frozen=True)
class GuardianResponse:
    raw_text: str
    tagged_text: str
    text: str
    emotions: tuple[str, ...]
    key_given: bool = False


class GuardianAI:
    def __init__(self, project_dir: Path, model_path: Path) -> None:
        self.project_dir = project_dir
        self.model_path = model_path
        self.llama_dir = project_dir / "tools" / "llama.cpp"
        self.server_exe = self.llama_dir / "llama-server.exe"
        self.base_url = "http://127.0.0.1:11435"
        self._server: subprocess.Popen[bytes] | None = None
        self._opener = build_opener(ProxyHandler({}))
        self._request_lock = Lock()

    def shutdown(self) -> None:
        with self._request_lock:
            server = self._server
            if server is None:
                return
            self._server = None
            if server.poll() is not None:
                return
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)

    def warm_up(self) -> None:
        with self._request_lock:
            self._ensure_model_ready()
            self._request_json(
                "/v1/chat/completions",
                {
                    "model": MODEL_ALIAS,
                    "messages": [
                        {
                            "role": "system",
                            "content": self._system_prompt(None, []),
                        },
                        {
                            "role": "user",
                            "content": (
                                "You are holding a key and need your towel back. "
                                "Speak naturally to the person standing in front "
                                "of you."
                            ),
                        },
                    ],
                    "max_tokens": 1,
                    "temperature": 0,
                    "stream": False,
                },
            )

    def reply(
        self,
        message: str | None,
        has_key: bool,
        history: list[dict[str, str]],
        towel_delivered: bool = False,
    ) -> GuardianResponse:
        with self._request_lock:
            self._ensure_model_ready()
            messages = [
                {
                    "role": "system",
                    "content": self._system_prompt(
                        message, history, towel_delivered
                    ),
                },
                *history[-MAX_HISTORY_MESSAGES:],
                {
                    "role": "user",
                    "content": self._game_state_message(
                        message, has_key, towel_delivered
                    ),
                },
            ]
            response = self._request_json(
                "/v1/chat/completions",
                {
                    "model": MODEL_ALIAS,
                    "messages": messages,
                    "max_tokens": MAX_RESPONSE_TOKENS,
                    "temperature": 0.75,
                    "top_p": 0.9,
                    "stream": False,
                },
            )
            try:
                answer = response["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as error:
                raise RuntimeError(
                    "Das lokale Modell hat eine ungültige Chat-Antwort geliefert."
                ) from error
            if not isinstance(answer, str) or not answer.strip():
                raise RuntimeError("Das lokale Modell hat eine leere Antwort geliefert.")
            raw_text = answer.strip()
            key_given = raw_text.endswith(KEY_GIVEN_MARKER)
            if key_given:
                raw_text = raw_text[: -len(KEY_GIVEN_MARKER)].rstrip()
            try:
                tagged_text = normalize_tagged_response(raw_text)
            except ValueError as error:
                if (
                    TAG_PATTERN.search(raw_text) is not None
                    or BARE_EMOTION_PATTERN.search(raw_text) is not None
                ):
                    raise RuntimeError(
                        "Das lokale Modell hat ungültige Yumenko-Emotionstags "
                        "geliefert."
                    ) from error
                tagged_text = raw_text
                display_text = raw_text
                emotions = []
            else:
                display_text, emotions = parse_emotion_tags(tagged_text)
            if not display_text:
                raise RuntimeError("Das lokale Modell hat keinen Anzeigetext geliefert.")
            return GuardianResponse(
                raw_text,
                tagged_text,
                display_text,
                tuple(emotions),
                key_given and towel_delivered and not has_key,
            )

    @staticmethod
    def _system_prompt(
        message: str | None,
        history: list[dict[str, str]],
        towel_delivered: bool = False,
    ) -> str:
        greeting = (
            "At the start of the conversation, say exactly: 'Ah! Wh-what are "
            "you doing here?! {scared} Give me my towel, now! {scared}'"
            if message is None and not history
            else ""
        )
        towel_reaction = (
            "The person has just handed your towel back to you. You have the "
            "towel now; recognize this and acknowledge the return in your next "
            "reply. You feel relieved and can relax a little, but remain "
            "cautious about giving away the key."
            if towel_delivered
            else "You still need your towel. You feel exposed, startled, and "
            "defensive; demand that it be returned to you."
        )
        return (
            "You are Yumenko, an adult woman in a shower room. You are face to "
            "face with someone who surprised you while you were showering. "
            "React like a real person in this moment: you are alarmed, panicked, "
            "embarrassed, and defensive. Scream out a first. Address the other person directly as "
            "'you' at all times. Never narrate them in third person or describe "
            "the situation as a story; react as if they are standing in front "
            "of you now. Refer only to things you could perceive or remember. "
            "You want yout towel desperatly. and are willing to trade itbut first you want your towel"
            + towel_reaction
            + "You are holding a key for opening the door. You are hesitant to hand it over, "
            "and decide for yourself whether what you hear persuades you. The other"
            "person wants the key for leaving the room but they saw you showering. "
            "You are embarrased and want them to not tell anyone. Never "
            "say that the other person already has the key unless that is true. "
            "Once you feel safe, you may become warmer and more playful, "
            "stay natural with some flirtation. Answer harmless "
            "off-topic questions directly. Speak in concise, natural English. "
            "Stay in character and do not repeat answers. "
            "Reply in one to five concise sentences, ideally under 40 words. "
            "Every sentence MUST end with exactly one emotion tag, "
            "chosen from {happy}, {scared}, {angry}, {surprised}, or "
            "{embarrassed}; place the tag after its sentence-ending punctuation. "
            "Do not put tags inside a sentence or leave text after a tag. "
            "Do not hand over the key just because the person asks or demands "
            "it. Hand it over only if what they say genuinely persuades you "
            "with a compelling reason or a fair trade. If you decide in "
            "character to hand over the key, append the exact hidden control "
            "marker [[KEY_GIVEN]] always after your final emotion tag. Otherwise, "
            "keep the key and do not include that marker."
            + greeting
        )

    @staticmethod
    def _game_state_message(
        message: str | None,
        has_key: bool,
        towel_delivered: bool = False,
    ) -> str:
        player_message = message or ""
        return (
            "[Current scene facts — use these even if earlier messages say otherwise]\n"
            f"You are holding the brass key: {'no' if has_key else 'yes'}.\n"
            + (
                "The person has just handed your towel back. You have the towel "
                "now; acknowledge receiving it in your reply.\n"
                if towel_delivered
                else "You do not have your towel back yet.\n"
            )
            + f"The person in front of you says: {player_message}"
        )

    def _ensure_model_ready(self) -> None:
        if not self.model_path.is_file():
            raise FileNotFoundError(f"Das Yumenko-Modell fehlt: {self.model_path}")
        if not self.server_exe.is_file():
            raise FileNotFoundError(
                "Die lokale KI-Laufzeit fehlt. Starte SetupGame.cmd, um llama.cpp "
                f"herunterzuladen: {self.server_exe}"
            )

        if self._is_server_ready():
            return

        environment = os.environ.copy()
        environment["PATH"] = (
            f"{self.llama_dir}{os.pathsep}{environment.get('PATH', '')}"
        )
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._server = subprocess.Popen(
            [
                str(self.server_exe),
                "--model",
                str(self.model_path),
                "--alias",
                MODEL_ALIAS,
                "--host",
                "127.0.0.1",
                "--port",
                "11435",
                "--device",
                "Vulkan0",
                "--n-gpu-layers",
                "99",
                "--ctx-size",
                "4096",
                "--no-webui",
                "--jinja",
            ],
            cwd=str(self.project_dir),
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
        deadline = monotonic() + 120
        while monotonic() < deadline:
            if self._server.poll() is not None:
                raise RuntimeError(
                    "Die lokale Yumenko-KI konnte nicht gestartet werden. "
                    "Prüfe den NVIDIA-Treiber und den Vulkan-GPU-Support."
                )
            if self._is_server_ready():
                return
            sleep(0.25)
        self.shutdown()
        raise TimeoutError(
            "Die lokale Yumenko-KI hat nicht rechtzeitig gestartet. "
            "Prüfe, ob die GPU verfügbar ist."
        )

    def _is_server_ready(self) -> bool:
        try:
            response = self._request_json("/v1/models", {}, timeout=2)
        except (OSError, RuntimeError, URLError):
            return False
        models = response.get("data")
        return isinstance(models, list) and any(
            isinstance(model, dict) and model.get("id") == MODEL_ALIAS
            for model in models
        )

    def _request_json(
        self,
        endpoint: str,
        payload: dict,
        timeout: int = 1800,
    ) -> dict:
        is_post = endpoint == "/v1/chat/completions"
        request = Request(
            f"{self.base_url}{endpoint}",
            data=json.dumps(payload).encode("utf-8") if is_post else None,
            headers={"Content-Type": "application/json"},
            method="POST" if is_post else "GET",
        )
        try:
            with self._opener.open(request, timeout=timeout) as response:
                result = json.load(response)
        except URLError as error:
            raise RuntimeError(
                f"Verbindung zur lokalen Yumenko-KI fehlgeschlagen "
                f"({endpoint}): {error}"
            ) from error
        if not isinstance(result, dict):
            raise RuntimeError(
                f"Ungültige Antwort von der lokalen Yumenko-KI ({endpoint})."
            )
        return result
