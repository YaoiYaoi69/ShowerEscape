import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from guardian_ai import GuardianAI


class GuardianAITests(unittest.TestCase):
    def setUp(self):
        self.model_file = tempfile.NamedTemporaryFile(suffix=".gguf", delete=False)
        self.model_file.close()
        self.addCleanup(Path(self.model_file.name).unlink, missing_ok=True)
        self.project_dir = Path(self.model_file.name).parent

    def test_reports_missing_model(self):
        ai = GuardianAI(
            self.project_dir,
            Path(self.model_file.name + ".missing"),
        )
        with self.assertRaisesRegex(FileNotFoundError, "Modell fehlt"):
            ai._ensure_model_ready()

    def test_uses_local_api_with_game_context_and_history(self):
        ai = GuardianAI(self.project_dir, Path(self.model_file.name))
        with patch.object(ai, "_ensure_model_ready"), patch.object(
            ai,
            "_request_json",
            return_value={"message": {"content": "Der Ausgang ist im Osten."}},
        ) as request:
            result = ai.reply(
                "Kann ich passieren?",
                True,
                [{"role": "assistant", "content": "Willkommen."}],
            )

        self.assertEqual(result, "Der Ausgang ist im Osten.")
        endpoint, payload = request.call_args.args
        self.assertEqual(endpoint, "/api/chat")
        self.assertEqual(payload["model"], "shower-guardian")
        self.assertEqual(payload["stream"], False)
        self.assertEqual(payload["think"], False)
        self.assertEqual(payload["options"]["num_predict"], 160)
        self.assertEqual(payload["options"]["num_ctx"], 2048)
        self.assertEqual(payload["options"]["temperature"], 0.8)
        self.assertEqual(payload["options"]["repeat_penalty"], 1.15)
        self.assertIn("not limited to roleplay", payload["messages"][0]["content"])
        self.assertIn("language of the latest message", payload["messages"][0]["content"])
        self.assertIn("Do not repeat previous answers", payload["messages"][0]["content"])
        self.assertIn("Answer the specific latest message", payload["messages"][0]["content"])
        self.assertIn("For harmless off-topic requests", payload["messages"][0]["content"])
        self.assertIn("Never refuse or redirect", payload["messages"][0]["content"])
        self.assertEqual(payload["messages"][1]["content"], "Willkommen.")
        self.assertIn("Brass key in player inventory: YES", payload["messages"][2]["content"])
        self.assertIn("Player's message: Kann ich passieren?", payload["messages"][2]["content"])

    def test_starts_conversation_without_a_fake_user_message(self):
        ai = GuardianAI(self.project_dir, Path(self.model_file.name))
        with patch.object(ai, "_ensure_model_ready"), patch.object(
            ai,
            "_request_json",
            return_value={"message": {"content": "Willkommen."}},
        ) as request:
            ai.reply(None, False, [])

        messages = request.call_args.args[1]["messages"]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("invite them to chat about anything", messages[0]["content"])
        self.assertEqual(messages[1]["role"], "user")
        self.assertIn("Brass key in player inventory: NO", messages[1]["content"])

    def test_key_status_is_explicitly_sent_for_both_inventory_states(self):
        ai = GuardianAI(self.project_dir, Path(self.model_file.name))
        prompts = []

        def capture(_endpoint, payload):
            prompts.append(payload["messages"][-1]["content"])
            return {"message": {"content": "Der Ausgang liegt im Osten."}}

        with patch.object(ai, "_ensure_model_ready"), patch.object(
            ai, "_request_json", side_effect=capture
        ):
            ai.reply("Habe ich den Schlüssel?", False, [])
            ai.reply("Habe ich den Schlüssel?", True, [])

        self.assertIn("Brass key in player inventory: NO", prompts[0])
        self.assertIn("key is NOT in the player's inventory", prompts[0])
        self.assertIn("Brass key in player inventory: YES", prompts[1])
        self.assertIn("key is in the player's inventory", prompts[1])

    def test_warmup_and_prompt_use_english_instructions(self):
        ai = GuardianAI(self.project_dir, Path(self.model_file.name))
        with patch.object(ai, "_ensure_model_ready"), patch.object(
            ai,
            "_request_json",
            return_value={"message": {"content": "Ready."}},
        ) as request:
            ai.warm_up()

        warmup_prompt = request.call_args.args[1]["messages"][0]["content"]
        self.assertIn("Reply naturally in the language the player uses", warmup_prompt)

    def test_requires_portable_ollama_runtime(self):
        ai = GuardianAI(self.project_dir, Path(self.model_file.name))
        ai.modelfile.touch()
        with self.assertRaisesRegex(FileNotFoundError, "lokale KI-Laufzeit"):
            ai._ensure_model_ready()

    def test_get_requests_do_not_send_a_json_body(self):
        class RecordingOpener:
            request = None

            def open(self, request, timeout):
                self.request = request
                return io.BytesIO(b'{"version":"0.40.6"}')

        ai = GuardianAI(self.project_dir, Path(self.model_file.name))
        opener = RecordingOpener()
        ai._opener = opener

        self.assertEqual(ai._request_json("/api/version", {}, timeout=2)["version"], "0.40.6")
        self.assertEqual(opener.request.method, "GET")
        self.assertIsNone(opener.request.data)

    def test_warmup_loads_model_and_keeps_it_resident(self):
        ai = GuardianAI(self.project_dir, Path(self.model_file.name))
        with patch.object(ai, "_ensure_model_ready") as ensure_ready, patch.object(
            ai,
            "_request_json",
            return_value={"message": {"content": "Wächter."}},
        ) as request:
            ai.warm_up()

        ensure_ready.assert_called_once_with()
        endpoint, payload = request.call_args.args
        self.assertEqual(endpoint, "/api/chat")
        self.assertEqual(payload["model"], "shower-guardian")
        self.assertEqual(payload["keep_alive"], -1)
        self.assertEqual(payload["options"]["num_predict"], 1)

    def test_chat_keeps_model_loaded_indefinitely(self):
        ai = GuardianAI(self.project_dir, Path(self.model_file.name))
        with patch.object(ai, "_ensure_model_ready"), patch.object(
            ai,
            "_request_json",
            return_value={"message": {"content": "Der Ausgang liegt im Osten."}},
        ) as request:
            ai.reply("Wo ist der Ausgang?", False, [])

        self.assertEqual(request.call_args.args[1]["keep_alive"], -1)

    def test_unload_uses_post_request(self):
        class RecordingOpener:
            request = None

            def open(self, request, timeout):
                self.request = request
                return io.BytesIO(b'{"model":"shower-guardian"}')

        ai = GuardianAI(self.project_dir, Path(self.model_file.name))
        opener = RecordingOpener()
        ai._opener = opener

        ai._unload_model()

        self.assertEqual(opener.request.method, "POST")
        self.assertEqual(opener.request.data, b'{"model": "shower-guardian", "keep_alive": 0}')


if __name__ == "__main__":
    unittest.main()
