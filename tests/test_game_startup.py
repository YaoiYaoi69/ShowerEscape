import unittest
from queue import Queue
from unittest.mock import MagicMock, patch

from game import GameWindow


class GameStartupTests(unittest.TestCase):
    def make_game(self):
        game = GameWindow.__new__(GameWindow)
        game.root = MagicMock()
        game.root.winfo_exists.return_value = True
        game.guardian_warmup_queue = Queue()
        game.voice_events = Queue()
        game.guardian_model_ready = False
        game.voice_ready = False
        game.voice_error = None
        game.voice_chat = None
        game.guardian_busy = False
        game.guardian_status = None
        game.guard_dialog = None
        game.loading_dialog = None
        game.loading_status = MagicMock()
        game.loading_retry_button = MagicMock()
        game.message_label = MagicMock()
        return game

    def test_voice_models_load_before_game_window_is_shown(self):
        game = self.make_game()
        game.guardian_warmup_queue.put((True, None))
        voice_chat = MagicMock()

        with patch("game.VoiceChat", return_value=voice_chat):
            game.poll_guardian_warmup()

        voice_chat.start.assert_called_once_with()
        game.root.deiconify.assert_not_called()
        self.assertTrue(game.guardian_model_ready)

        game.voice_events.put(("ready", "cuda"))
        game.poll_voice_queue()

        game.root.deiconify.assert_called_once_with()
        self.assertTrue(game.voice_ready)
        game.message_label.config.assert_called_once_with(
            text="Yumenko ist bereit. Gehe zu ihr und chatte mit ihr."
        )

    def test_game_opens_with_text_chat_if_voice_model_fails(self):
        game = self.make_game()
        game.guardian_model_ready = True
        game.voice_events.put(("error", "CUDA unavailable"))

        game.poll_voice_queue()

        game.root.deiconify.assert_called_once_with()
        game.message_label.config.assert_called_once_with(
            text=(
                "Yumenko ist bereit. Sprache nicht verfügbar; "
                "Texteingabe bleibt möglich."
            )
        )
        self.assertEqual(game.voice_error, "CUDA unavailable")


if __name__ == "__main__":
    unittest.main()
