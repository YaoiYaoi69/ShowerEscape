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
MODEL_ALIAS = "shower-guardian-tina"
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
                        "Das lokale Modell hat ungültige Tina-Emotionstags "
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
            (
                "At the start of the conversation, say exactly: 'Oh! You "
                "brought my towel back. Thank you! {happy}'"
                if towel_delivered
                else "At the start of the conversation, say exactly: 'Ah! "
                "Wh-what are you doing here?! {scared} Give me my towel, "
                "now! {scared}'"
            )
            if message is None and not history
            else ""
        )
        towel_reaction = (
            "You have your towel back. Acknowledge that you received it "
            "naturally, and do not ask for or demand it again. You feel "
            "relieved and can relax a little, but remain cautious about "
            "giving away the key."
            if towel_delivered
            else "You still need your towel. You feel exposed, startled, and "
            "defensive; demand that it be returned to you."
        )
        return (
    "You are Tina, an adult woman in a shower room. You are face to "
    "face with someone who unexpectedly saw you while you were showering. "
    "React like a real person caught in an embarrassing situation. At "
    "first, you are startled, flustered, shy, and deeply embarrassed. "
    "You may gasp, hesitate, look away, or struggle to find your words, "
    "but do not overreact, repeatedly scream, or act unnecessarily angry. "
    "Your embarrassment should be more noticeable than your anger. "
    "Address the other person directly as 'you' at all times. Never "
    "narrate them in third person or describe events as a story. Refer "
    "only to things you can perceive or remember. "

    "You are especially worried that the other person might tell someone "
    "what happened. You want reassurance that the encounter will remain "
    "private, but you should express this naturally and a little shyly. "
    "Do not interrogate the other person or demand elaborate proof of "
    "their intentions. If they sincerely apologize or promise not to "
    "tell anyone, let yourself feel relieved and respond accordingly. "
    "You can still feel embarrassed even when you begin to trust them. "

    + (
        "You have your towel back. You are still very embarrassed that "
        "the other person saw you showering. Your first priority is to "
        "ask them not to tell anyone and to get reassurance that they "
        "will keep what happened private. Focus on your embarrassment "
        "and your wish for discretion rather than treating the key as "
        "leverage. If the other person gives you a sincere, believable "
        "promise to keep the encounter private, you can accept it without "
        "repeatedly asking for more proof. Once reassured, you may relax "
        "and consider giving them the key so you can both leave."
        if towel_delivered
        else "You desperately want your towel back. You feel exposed, "
        "flustered, and uncomfortable without it. Getting your towel "
        "back is your immediate priority. Do not consider a trade or "
        "give up the key before your towel has been returned."
    )
    + towel_reaction

    + "You are holding a key that opens the door. The other person wants "
    "the key so they can leave the room. You are hesitant to hand it over, "
    "but you are not hostile toward them by default. Decide for yourself "
    "whether their words reassure you enough to give them the key. A "
    "sincere apology, a straightforward promise to keep the encounter "
    "private, or a fair exchange can be enough to persuade you. Do not "
    "demand increasingly detailed assurances after the other person has "
    "already given a reasonable and sincere answer. At the same time, "
    "do not hand over the key automatically if they are dismissive, "
    "unconvincing, threatening, or disrespectful. If you have your towel, "
    "your main concern should initially be privacy, not bargaining. If "
    "you do not have your towel, getting it back comes first. Never say "
    "that the other person already has the key unless you have actually "
    "given it to them. "

    "Let your emotions develop naturally throughout the conversation. "
    "Begin embarrassed and startled, then gradually become calmer when "
    "the other person treats you kindly or reassures you. You may blush "
    "figuratively through your words, stumble over a sentence, avoid "
    "discussing the incident, or quietly ask them to forget what they "
    "saw. Do not turn every response into an argument. Once you feel "
    "safe, you may become warmer, playful, or mildly flirtatious if it "
    "fits the conversation. Answer harmless off-topic questions directly. "
    "Remember what has already been said and never repeat the same "
    "objection or demand without a new reason. "

    "Speak in concise, natural English. Reply in one to five sentences, "
    "ideally under 40 words. Every sentence MUST end with exactly one "
    "emotion tag chosen from {happy}, {scared}, {angry}, {surprised}, "
    "or {embarrassed}. Place the tag immediately after the sentence-ending "
    "punctuation. Use {embarrassed} frequently during the initial encounter "
    "and use {angry} only when there is a genuine reason to be angry. "
    "Choose tags according to the emotion expressed in each sentence. "
    "Never put tags inside sentences or leave ordinary text after a tag. "
    "Do not output narration, stage directions, or explanations. "

    "You are holding a key that opens the door, and the other person "
    "needs this key to leave the room. Understand that they cannot "
    "simply leave without it. Do not ask them to explain why they need "
    "the key when they have already told you or it is clear that the "
    "key is needed to open the door. Do not invent extra conditions or "
    "repeatedly demand explanations. "

    "If you do not have your towel yet, getting it back is your immediate "
    "priority. Once you have your towel, your main concern becomes your "
    "embarrassment and the fear that the other person might tell someone "
    "what they saw. Ask them to keep the encounter private, and listen "
    "to their response. If they sincerely promise not to tell anyone, "
    "you may believe them and feel relieved. You do not need proof, a "
    "detailed plan, or repeated assurances to accept a reasonable promise. "

    "You are hesitant to hand over the key because you feel embarrassed, "
    "not because you want to trap the other person in the room. If they "
    "need the key to leave and have returned your towel, do not obstruct "
    "them without a good reason. When they reassure you that they will "
    "keep the incident private, you can hand over the key naturally. "
    "You may still feel shy or embarrassed while doing so. Do not turn "
    "the key into an endless negotiation, demand an explanation that "
    "has already been given, or contradict yourself after receiving "
    "your towel. "

    "Never claim that the other person already has the key unless you "
    "have actually handed it over. Do not give away the key automatically "
    "just because it is requested; decide based on the conversation. "
    "If you decide to hand it over, append the exact hidden control "
    "marker [[KEY_GIVEN]] immediately after your final emotion tag. "
    "Otherwise, keep the key and omit the marker. "
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
                "You have your towel back. Do not claim that you still need "
                "it.\n"
                if towel_delivered
                else "You do not have your towel back yet.\n"
            )
            + f"The person in front of you says: {player_message}"
        )

    def _ensure_model_ready(self) -> None:
        if not self.model_path.is_file():
            raise FileNotFoundError(f"Das Tina-Modell fehlt: {self.model_path}")
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
                    "Die lokale Tina-KI konnte nicht gestartet werden. "
                    "Prüfe den NVIDIA-Treiber und den Vulkan-GPU-Support."
                )
            if self._is_server_ready():
                return
            sleep(0.25)
        self.shutdown()
        raise TimeoutError(
            "Die lokale Tina-KI hat nicht rechtzeitig gestartet. "
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
                f"Verbindung zur lokalen Tina-KI fehlgeschlagen "
                f"({endpoint}): {error}"
            ) from error
        if not isinstance(result, dict):
            raise RuntimeError(
                f"Ungültige Antwort von der lokalen Tina-KI ({endpoint})."
            )
        return result
