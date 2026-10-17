from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from threading import Lock
from time import monotonic, sleep
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener


class GuardianAI:
    def __init__(self, project_dir: Path, model_path: Path) -> None:
        self.project_dir = project_dir
        self.model_path = model_path
        self.ollama_dir = project_dir / "tools" / "ollama"
        self.ollama_exe = self.ollama_dir / "ollama.exe"
        self.ollama_models_dir = project_dir / "models" / "ollama"
        self.modelfile = project_dir / "guardian.Modelfile"
        self.base_url = "http://127.0.0.1:11435"
        self.model_name = "shower-guardian"
        self._server: subprocess.Popen[bytes] | None = None
        self._environment: dict[str, str] | None = None
        self._opener = build_opener(ProxyHandler({}))
        self._request_lock = Lock()

    def shutdown(self) -> None:
        with self._request_lock:
            if self._server is not None and self._server.poll() is None:
                self._unload_model()
                self._server.terminate()
                try:
                    self._server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._server.kill()
                    self._server.wait(timeout=5)

    def warm_up(self) -> None:
        with self._request_lock:
            self._ensure_model_ready()
            self._request_json(
                "/api/chat",
                {
                    "model": self.model_name,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                "You are ready to chat. Reply naturally in the "
                                "language the player uses."
                            ),
                        }
                    ],
                    "stream": False,
                    "think": False,
                    "keep_alive": -1,
                    "options": {
                        "num_ctx": 2048,
                        "num_predict": 1,
                        "temperature": 0,
                    },
                },
            )

    def reply(
        self,
        message: str | None,
        has_key: bool,
        history: list[dict[str, str]],
    ) -> str:
        with self._request_lock:
            self._ensure_model_ready()
            key_status = (
                "YES — the brass key is in the player's inventory."
                if has_key
                else "NO — the brass key is NOT in the player's inventory."
            )
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a helpful, friendly conversational AI in ShowerEscape. "
                        "The player can talk to you about anything; you are not limited "
                        "to roleplay. Answer the latest message directly and naturally. "
                        "For harmless off-topic requests, jokes, general questions, "
                        "opinions, and small talk, answer normally. Never refuse or "
                        "redirect just because a topic is outside the game or breaks "
                        "immersion. Answer the specific latest message, not a generic "
                        "conversation starter. Do not repeat previous answers, stock "
                        "greetings, or the same opening phrase; vary your wording "
                        "naturally. Use clear, simple language, and reply in the "
                        "language of the latest message; if unclear, use English. "
                        "For game questions, the inventory status in the latest player "
                        "message is authoritative, even if older chat says otherwise. "
                        "The brass key is found in the chest. The locked exit is east "
                        "and requires the key. Do not invent game locations or rules. "
                        "Do not mention the game or key for unrelated topics."
                        + (
                            " The player has just arrived; greet them naturally and "
                            "invite them to chat about anything."
                            if message is None and not history
                            else ""
                        )
                    ),
                },
                *history,
            ]
            player_message = (
                message
                if message is not None
                else "Begrüße den Spieler kurz und frage, ob du helfen kannst."
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "[CURRENT GAME STATE — provided by the game, authoritative]\n"
                        f"Brass key in player inventory: {key_status}\n"
                        "For game questions, use this current state, not earlier chat "
                        "messages. For other topics, respond normally.\n\n"
                        f"Player's message: {player_message}"
                    ),
                }
            )

            response = self._request_json(
                "/api/chat",
                {
                    "model": self.model_name,
                    "messages": messages,
                    "stream": False,
                    "think": False,
                    "keep_alive": -1,
                    "options": {
                        "num_ctx": 2048,
                        "num_predict": 160,
                        "temperature": 0.8,
                        "repeat_penalty": 1.15,
                    },
                },
            )
            answer = response.get("message", {}).get("content")
            if not isinstance(answer, str) or not answer.strip():
                raise RuntimeError("Das lokale Modell hat eine leere Antwort geliefert.")
            return answer.strip()

    def _unload_model(self) -> None:
        try:
            self._request_json(
                "/api/generate",
                {"model": self.model_name, "keep_alive": 0},
                timeout=5,
            )
        except (OSError, RuntimeError, URLError):
            pass

    def _ensure_model_ready(self) -> None:
        if not self.model_path.is_file():
            raise FileNotFoundError(f"Das Wächter-Modell fehlt: {self.model_path}")
        if not self.ollama_exe.is_file():
            raise FileNotFoundError(
                "Die lokale KI-Laufzeit fehlt. Starte SetupGame.cmd, um sie "
                f"herunterzuladen: {self.ollama_exe}"
            )
        if not self.modelfile.is_file():
            raise FileNotFoundError(f"Die Wächter-Konfiguration fehlt: {self.modelfile}")

        self.ollama_models_dir.mkdir(parents=True, exist_ok=True)
        self._environment = os.environ.copy()
        self._environment["OLLAMA_HOST"] = "127.0.0.1:11435"
        self._environment["OLLAMA_MODELS"] = str(self.ollama_models_dir)
        self._environment["OLLAMA_KEEP_ALIVE"] = "-1"

        if not self._is_server_ready():
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self._server = subprocess.Popen(
                [str(self.ollama_exe), "serve"],
                cwd=str(self.ollama_dir),
                env=self._environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
            deadline = monotonic() + 90
            while monotonic() < deadline:
                if self._server.poll() is not None:
                    raise RuntimeError(
                        "Die lokale KI konnte nicht gestartet werden. "
                        "Prüfe den NVIDIA-Treiber oder starte SetupGame.cmd erneut."
                    )
                if self._is_server_ready():
                    break
                sleep(0.25)
            else:
                raise TimeoutError(
                    "Die lokale KI hat nicht rechtzeitig gestartet. "
                    "Prüfe den NVIDIA-Treiber."
                )

        tags = self._request_json("/api/tags", {})
        installed_models = {
            item.get("name") for item in tags.get("models", [])
        }
        if f"{self.model_name}:latest" not in installed_models:
            result = subprocess.run(
                [
                    str(self.ollama_exe),
                    "create",
                    self.model_name,
                    "-f",
                    str(self.modelfile),
                ],
                cwd=str(self.project_dir),
                env=self._environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=1800,
                check=False,
            )
            if result.returncode:
                details = (result.stderr or result.stdout).strip()
                raise RuntimeError(
                    "Das Wächter-Modell konnte nicht eingerichtet werden: "
                    f"{details or 'Ollama meldete einen unbekannten Fehler.'}"
                )

    def _is_server_ready(self) -> bool:
        try:
            self._request_json("/api/version", {}, timeout=2)
            self._request_json("/api/tags", {}, timeout=2)
        except (OSError, RuntimeError, URLError):
            return False
        return True

    def _request_json(
        self,
        endpoint: str,
        payload: dict,
        timeout: int = 1800,
    ) -> dict:
        is_post = endpoint in {"/api/chat", "/api/generate"}
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
                f"Verbindung zur lokalen KI fehlgeschlagen ({endpoint}): {error}"
            ) from error
        if not isinstance(result, dict):
            raise RuntimeError(f"Ungültige Antwort von der lokalen KI ({endpoint}).")
        return result
