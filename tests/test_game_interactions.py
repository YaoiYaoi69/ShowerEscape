import unittest

from game import PLACES, Player, interact, nearby_place, scale_coordinate


class GameInteractionTests(unittest.TestCase):
    def setUp(self):
        for place in PLACES:
            place.used = False

    def test_finds_guard_nearby(self):
        player = Player(
            x=scale_coordinate(600),
            y=scale_coordinate(312),
        )

        self.assertEqual(nearby_place(player).kind, "guard")

    def test_chest_interaction_still_grants_key(self):
        player = Player(
            x=scale_coordinate(216),
            y=scale_coordinate(120),
        )

        message, won = interact(player)

        self.assertTrue(player.has_key)
        self.assertFalse(won)
        self.assertIn("gefunden", message)


if __name__ == "__main__":
    unittest.main()
