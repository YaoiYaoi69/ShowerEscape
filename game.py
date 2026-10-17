from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from math import gcd
from pathlib import Path


BASE_TILE_SIZE = 32
TILE_SIZE = 72
SCALE_FACTOR = TILE_SIZE / BASE_TILE_SIZE
GRID_COLUMNS = 26
GRID_ROWS = 15
WORLD_WIDTH = GRID_COLUMNS * TILE_SIZE
WORLD_HEIGHT = GRID_ROWS * TILE_SIZE
PLAYER_SIZE = round(28 * SCALE_FACTOR)
MOVE_DISTANCE = round(12 * SCALE_FACTOR)
TILE_IMAGE_DIR = Path(__file__).resolve().parent / "assets" / "tiles"

# Use (column, row): "filename.png" entries to assign individual backgrounds.
BACKGROUND_TILES: dict[tuple[int, int], str] = {
    (column, row): "stone.png"
    for row in range(GRID_ROWS)
    for column in range(GRID_COLUMNS)
}

# Each row must contain GRID_COLUMNS characters: . is walkable, # is blocked.
COLLISION_MAP = (
    "##########################",
    "..........................",
    "..........................",
    "..........................",
    ".........#################",
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    "....................####..",
    "....................####..",
    "..........................",
    "..........................",
    "..........................",
)


def scale_coordinate(value: int) -> int:
    return round(value * SCALE_FACTOR)


@dataclass
class Player:
    x: int = scale_coordinate(120)
    y: int = scale_coordinate(120)
    has_key: bool = False


@dataclass
class Place:
    name: str
    x: int
    y: int
    description: str
    kind: str
    used: bool = False


PLACES = [
    Place("Truhe", 216, 120, "Eine alte Truhe. Darin liegt ein kleiner Messingschluessel.", "chest"),
    Place("Schild", 408, 168, "Auf dem Schild steht: Finde den Schluessel und suche den Ausgang im Osten.", "sign"),
    Place("Waechter", 600, 312, "Der Waechter sagt: Der Ausgang liegt ganz im Osten. Ohne Schluessel bleibt er zu.", "guard"),
    Place("Ausgang", 696, 72, "Der Ausgang ist verschlossen.", "exit"),
]


def validate_grid() -> None:
    if len(COLLISION_MAP) != GRID_ROWS:
        raise ValueError(f"Die Kollisionskarte muss genau {GRID_ROWS} Zeilen haben.")
    for row_index, row in enumerate(COLLISION_MAP):
        if len(row) != GRID_COLUMNS:
            raise ValueError(
                f"Zeile {row_index + 1} der Kollisionskarte muss "
                f"{GRID_COLUMNS} Zeichen haben."
            )
        if set(row) - {".", "#"}:
            raise ValueError("Die Kollisionskarte darf nur . und # enthalten.")

    for column, row in BACKGROUND_TILES:
        if not (0 <= column < GRID_COLUMNS and 0 <= row < GRID_ROWS):
            raise ValueError(f"Hintergrund-Kachel ausserhalb des Rasters: {(column, row)}")


def move(player: Player, direction: str) -> None:
    offsets = {
        "w": (0, -MOVE_DISTANCE),
        "a": (-MOVE_DISTANCE, 0),
        "s": (0, MOVE_DISTANCE),
        "d": (MOVE_DISTANCE, 0),
    }
    dx, dy = offsets[direction]
    half_size = PLAYER_SIZE / 2
    next_x = max(half_size, min(WORLD_WIDTH - half_size, player.x + dx))
    next_y = max(half_size, min(WORLD_HEIGHT - half_size, player.y + dy))
    if not is_position_blocked(next_x, next_y):
        player.x = next_x
        player.y = next_y


def is_position_blocked(x: float, y: float) -> bool:
    half_size = PLAYER_SIZE / 2
    left = int((x - half_size) // TILE_SIZE)
    right = int((x + half_size - 1) // TILE_SIZE)
    top = int((y - half_size) // TILE_SIZE)
    bottom = int((y + half_size - 1) // TILE_SIZE)
    return any(
        COLLISION_MAP[row][column] == "#"
        for row in range(top, bottom + 1)
        for column in range(left, right + 1)
    )


def interact(player: Player) -> tuple[str, bool]:
    nearby = [
        place
        for place in PLACES
        if abs(scale_coordinate(place.x) - player.x) <= scale_coordinate(48)
        and abs(scale_coordinate(place.y) - player.y) <= scale_coordinate(48)
    ]
    if not nearby:
        return "Hier ist nichts zum Interagieren. Geh naeher an ein Objekt heran.", False

    place = nearby[0]
    if place.kind == "chest":
        if place.used:
            return "Die Truhe ist leer.", False
        player.has_key = True
        place.used = True
        return "Du hast den Messingschluessel gefunden!", False
    if place.kind == "exit":
        if player.has_key:
            return "Mit dem Schluessel oeffnest du den Ausgang. Geschafft!", True
        return "Der Ausgang ist verschlossen. Vielleicht liegt der Schluessel in der Truhe.", False
    return place.description, False


class GameWindow:
    def __init__(self, root: tk.Tk) -> None:
        global TILE_SIZE, SCALE_FACTOR, WORLD_WIDTH, WORLD_HEIGHT, PLAYER_SIZE, MOVE_DISTANCE

        validate_grid()
        self.root = root
        root.title("Das kleine Abenteuer")
        root.attributes("-fullscreen", True)
        root.configure(bg="#1c2630")

        available_width = root.winfo_screenwidth()
        available_height = root.winfo_screenheight() - 144
        fitted_tile_size = min(
            TILE_SIZE,
            available_width // GRID_COLUMNS,
            available_height // GRID_ROWS,
        )
        TILE_SIZE = max(4, fitted_tile_size // 4 * 4)
        SCALE_FACTOR = TILE_SIZE / BASE_TILE_SIZE
        WORLD_WIDTH = GRID_COLUMNS * TILE_SIZE
        WORLD_HEIGHT = GRID_ROWS * TILE_SIZE
        PLAYER_SIZE = round(28 * SCALE_FACTOR)
        MOVE_DISTANCE = max(1, round(12 * SCALE_FACTOR))
        self.player = Player(x=scale_coordinate(120), y=scale_coordinate(120))
        self.won = False
        self.background_images = self.load_background_images()

        title = tk.Label(
            root,
            text="ShowerEscape",
            font=("Segoe UI", 18, "bold"),
            fg="#f1f5f9",
            bg="#1c2630",
            pady=12,
        )
        title.pack()

        self.canvas = tk.Canvas(
            root,
            width=WORLD_WIDTH,
            height=WORLD_HEIGHT,
            bg="#78a75b",
            highlightthickness=0,
        )
        self.canvas.pack(padx=18)

        self.key_label = tk.Label(
            root, font=("Segoe UI", 11, "bold"), fg="#facc15", bg="#1c2630", pady=8
        )
        self.key_label.pack()

        self.message_label = tk.Label(
            root,
            text="Finde den Schluessel und erreiche den Ausgang.",
            font=("Segoe UI", 10),
            fg="#e2e8f0",
            bg="#1c2630",
            wraplength=WORLD_WIDTH,
            pady=4,
        )
        self.message_label.pack()

        controls = tk.Label(
            root,
            text="WASD bewegen    E interagieren    Esc beenden",
            font=("Segoe UI", 10),
            fg="#94a3b8",
            bg="#1c2630",
            pady=10,
        )
        controls.pack()

        root.bind("<KeyPress>", self.on_key)
        self.draw()

    def load_background_images(self) -> dict[str, tk.PhotoImage]:
        images: dict[str, tk.PhotoImage] = {}
        for filename in set(BACKGROUND_TILES.values()):
            image_path = TILE_IMAGE_DIR / filename
            if not image_path.is_file():
                raise FileNotFoundError(f"Hintergrund-Kachel nicht gefunden: {image_path}")
            image = tk.PhotoImage(file=str(image_path))
            if image.width() != image.height():
                raise ValueError(
                    f"{image_path} muss quadratisch sein, damit sie in Tiles passt."
                )
            divisor = gcd(image.width(), TILE_SIZE)
            image = image.subsample(
                image.width() // divisor, image.height() // divisor
            ).zoom(
                TILE_SIZE // divisor, TILE_SIZE // divisor
            )
            images[filename] = image
        return images

    def draw(self) -> None:
        self.canvas.delete("all")
        for (column, row), filename in BACKGROUND_TILES.items():
            x = column * TILE_SIZE
            y = row * TILE_SIZE
            self.canvas.create_image(
                x, y, image=self.background_images[filename], anchor="nw"
            )
            self.canvas.create_rectangle(
                x,
                y,
                x + TILE_SIZE,
                y + TILE_SIZE,
                outline="#475569",
                width=round(SCALE_FACTOR),
            )
            if COLLISION_MAP[row][column] == "#":
                self.canvas.create_rectangle(
                    x,
                    y,
                    x + TILE_SIZE,
                    y + TILE_SIZE,
                    fill="#404040",
                    outline="",
                )

        for place in PLACES:
            place_half_size = PLAYER_SIZE / 2
            place_x = scale_coordinate(place.x)
            place_y = scale_coordinate(place.y)
            x0, y0 = place_x - place_half_size, place_y - place_half_size
            x1, y1 = place_x + place_half_size, place_y + place_half_size
            outline_width = round(2 * SCALE_FACTOR)
            if place.kind == "chest":
                color = "#64748b" if place.used else "#a16207"
                self.canvas.create_rectangle(
                    x0, y0, x1, y1, fill=color, outline="#fbbf24", width=outline_width
                )
            elif place.kind == "exit":
                self.canvas.create_rectangle(
                    x0,
                    y0 - scale_coordinate(8),
                    x1,
                    y1 + scale_coordinate(8),
                    fill="#1e293b",
                    outline="#cbd5e1",
                    width=outline_width,
                )
            elif place.kind == "sign":
                self.canvas.create_rectangle(
                    place_x - scale_coordinate(3),
                    place_y,
                    place_x + scale_coordinate(3),
                    place_y + scale_coordinate(18),
                    fill="#78350f",
                    outline="",
                )
                self.canvas.create_rectangle(
                    x0 - scale_coordinate(4),
                    y0 - scale_coordinate(4),
                    x1 + scale_coordinate(4),
                    y0 + scale_coordinate(12),
                    fill="#a16207",
                    outline="#fbbf24",
                    width=outline_width,
                )
            else:
                self.canvas.create_rectangle(
                    x0, y0, x1, y1, fill="#7c3aed", outline="#ddd6fe", width=outline_width
                )

        half_size = PLAYER_SIZE / 2
        self.canvas.create_rectangle(
            self.player.x - half_size,
            self.player.y - half_size,
            self.player.x + half_size,
            self.player.y + half_size,
            fill="#38bdf8",
            outline="#e0f2fe",
            width=round(2 * SCALE_FACTOR),
        )

        self.key_label.config(
            text=f"Schluessel: {'Ja' if self.player.has_key else 'Nein'}"
        )

    def on_key(self, event: tk.Event) -> None:
        if event.keysym == "Escape":
            self.root.destroy()
            return
        if self.won:
            return

        key = event.keysym.lower()
        directions = {
            "w": "w",
            "a": "a",
            "s": "s",
            "d": "d",
            "up": "w",
            "left": "a",
            "down": "s",
            "right": "d",
        }
        if key in directions:
            move(self.player, directions[key])
            self.draw()
        elif key == "e":
            message, self.won = interact(self.player)
            self.message_label.config(text=message)
            self.draw()
            if self.won:
                self.message_label.config(fg="#86efac")


def main() -> None:
    root = tk.Tk()
    GameWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
