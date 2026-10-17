from __future__ import annotations

from queue import Empty, Queue
from threading import Thread
import tkinter as tk
from dataclasses import dataclass
from math import gcd
from pathlib import Path

from guardian_ai import GuardianAI


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


def nearby_place(player: Player) -> Place | None:
    nearby = [
        place
        for place in PLACES
        if abs(scale_coordinate(place.x) - player.x) <= scale_coordinate(48)
        and abs(scale_coordinate(place.y) - player.y) <= scale_coordinate(48)
    ]
    if not nearby:
        return None
    return min(
        nearby,
        key=lambda candidate: (
            scale_coordinate(candidate.x) - player.x
        ) ** 2
        + (scale_coordinate(candidate.y) - player.y) ** 2,
    )


def interact(player: Player) -> tuple[str, bool]:
    place = nearby_place(player)
    if place is None:
        return "Hier ist nichts zum Interagieren. Geh naeher an ein Objekt heran.", False

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
        try:
            root.attributes("-fullscreen", True)
        except tk.TclError:
            root.attributes("-fullscreen", False)
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
        self.guardian_ai = GuardianAI(
            Path(__file__).resolve().parent,
            Path(__file__).resolve().parent
            / "models"
            / "qwen3.5-0.8b-Q4_K_M.gguf",
        )
        self.guardian_history: list[dict[str, str]] = []
        self.guardian_busy = False
        self.guardian_greeting_started = False
        self.guard_dialog: tk.Toplevel | None = None
        self.guard_was_nearby = False
        self.guardian_messages: tk.Text | None = None
        self.guardian_input: tk.Entry | None = None
        self.guardian_chat_button: tk.Button | None = None
        self.guardian_status: tk.Label | None = None
        self.guardian_send_button: tk.Button | None = None
        self.guardian_queue: Queue[tuple[bool, str | None, str]] = Queue()
        self.guardian_warmup_queue: Queue[tuple[bool, str | None]] = Queue()
        self.guardian_warmup_started = False
        self.background_images = self.load_background_images()
        root.protocol("WM_DELETE_WINDOW", self.close_game)

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

        self.guardian_chat_button = tk.Button(
            root,
            text="Mit dem Wächter chatten",
            command=self.open_guard_dialog,
            font=("Segoe UI", 11, "bold"),
            fg="#f1f5f9",
            bg="#6d28d9",
            activebackground="#7c3aed",
            activeforeground="#ffffff",
            padx=18,
            pady=6,
        )
        self.guardian_chat_button.pack(pady=(8, 2))

        controls = tk.Label(
            root,
            text="WASD bewegen    E interagieren    T Wächter-Chat    Esc beenden",
            font=("Segoe UI", 10),
            fg="#94a3b8",
            bg="#1c2630",
            pady=10,
        )
        controls.pack()

        root.bind_all("<KeyPress>", self.on_key)
        self.draw()
        root.after(200, self.start_guardian_warmup)
        root.after(100, self.poll_guardian_warmup)

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
            if self.guard_dialog is not None and self.guard_dialog.winfo_exists():
                self.close_guard_dialog()
                return
            self.close_game()
            return
        if event.keysym.lower() == "t":
            self.open_guard_dialog()
            return
        if self.guard_dialog is not None and self.guard_dialog.winfo_exists():
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
            place = nearby_place(self.player)
            is_near_guard = place is not None and place.kind == "guard"
            if is_near_guard and not self.guard_was_nearby:
                self.open_guard_dialog()
            self.guard_was_nearby = is_near_guard
        elif key == "e":
            place = nearby_place(self.player)
            if place is not None and place.kind == "guard":
                self.open_guard_dialog()
                return
            message, self.won = interact(self.player)
            self.message_label.config(text=message)
            self.draw()
            if self.won:
                self.message_label.config(fg="#86efac")

    def close_game(self) -> None:
        self.close_guard_dialog()
        self.guardian_ai.shutdown()
        self.root.destroy()

    def start_guardian_warmup(self) -> None:
        if self.guardian_warmup_started:
            return
        self.guardian_warmup_started = True
        self.message_label.config(
            text="Der Wächter lädt seine lokale KI im Hintergrund ..."
        )

        def warm_up() -> None:
            try:
                self.guardian_ai.warm_up()
            except Exception as error:
                self.guardian_warmup_queue.put((False, str(error)))
            else:
                self.guardian_warmup_queue.put((True, None))

        Thread(target=warm_up, daemon=True).start()

    def poll_guardian_warmup(self) -> None:
        try:
            succeeded, error = self.guardian_warmup_queue.get_nowait()
        except Empty:
            if self.root.winfo_exists():
                self.root.after(200, self.poll_guardian_warmup)
            return

        if succeeded:
            self.message_label.config(
                text="Die Wächter-KI ist geladen. Gehe zum Wächter und chatte mit ihm."
            )
        else:
            self.message_label.config(
                text=f"Wächter-KI konnte nicht geladen werden: {error}"
            )

    def open_guard_dialog(self) -> None:
        if self.guard_dialog is not None and self.guard_dialog.winfo_exists():
            self.guard_dialog.lift()
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Der Wächter")
        dialog.geometry("520x440")
        dialog.resizable(True, True)
        dialog.transient(self.root)
        dialog.configure(bg="#1c2630")
        dialog.update_idletasks()
        x = max(0, (dialog.winfo_screenwidth() - 520) // 2)
        y = max(0, (dialog.winfo_screenheight() - 440) // 2)
        dialog.geometry(f"520x440+{x}+{y}")
        self.guard_dialog = dialog

        self.guardian_messages = tk.Text(
            dialog,
            state="disabled",
            wrap="word",
            font=("Segoe UI", 10),
            bg="#0f172a",
            fg="#e2e8f0",
            padx=10,
            pady=10,
        )
        self.guardian_status = tk.Label(
            dialog,
            text="Der Wächter denkt nach ...",
            fg="#94a3b8",
            bg="#1c2630",
        )

        input_row = tk.Frame(dialog, bg="#1c2630")
        input_row.pack(side="bottom", fill="x", padx=12, pady=12)
        self.guardian_input = tk.Entry(input_row, font=("Segoe UI", 11))
        self.guardian_input.pack(side="left", fill="x", expand=True, ipady=6)
        self.guardian_send_button = tk.Button(
            input_row, text="Senden", command=self.send_guardian_message
        )
        self.guardian_send_button.pack(side="left", padx=(8, 0))
        self.guardian_status.pack(side="bottom", anchor="w", padx=14)
        self.guardian_messages.pack(
            side="top", fill="both", expand=True, padx=12, pady=(12, 6)
        )
        self.guardian_input.bind("<Return>", self.send_guardian_message)
        dialog.bind("<Return>", self.send_guardian_message)
        dialog.bind("<Escape>", lambda _event: self.close_guard_dialog())
        dialog.protocol("WM_DELETE_WINDOW", self.close_guard_dialog)
        dialog.grab_set()
        dialog.deiconify()
        dialog.lift()
        dialog.attributes("-topmost", True)
        dialog.after(500, lambda: dialog.winfo_exists() and dialog.attributes("-topmost", False))
        dialog.after_idle(self.guardian_input.focus_force)

        for entry in self.guardian_history:
            speaker = "Du" if entry["role"] == "user" else "Wächter"
            self.append_guardian_text(speaker, entry["content"])
        if not self.guardian_greeting_started:
            self.guardian_greeting_started = True
            self.request_guardian_reply(None)
        elif self.guardian_busy:
            self.guardian_status.config(text="Die lokale KI antwortet gerade ...")
            self.guardian_send_button.config(state="disabled")
        else:
            self.guardian_status.config(text="Stelle deine Frage an den Wächter.")
        self.poll_guardian_queue()

    def close_guard_dialog(self) -> None:
        if self.guard_dialog is not None:
            self.guard_dialog.grab_release()
            self.guard_dialog.destroy()
        self.guard_dialog = None
        self.guardian_messages = None
        self.guardian_input = None
        self.guardian_status = None
        self.guardian_send_button = None

    def append_guardian_text(self, speaker: str, text: str) -> None:
        if self.guardian_messages is None:
            return
        self.guardian_messages.config(state="normal")
        self.guardian_messages.insert("end", f"{speaker}: {text}\n\n")
        self.guardian_messages.config(state="disabled")
        self.guardian_messages.see("end")

    def send_guardian_message(self, _event: tk.Event | None = None) -> None:
        if (
            self.guardian_input is None
            or self.guardian_send_button is None
            or self.guardian_busy
        ):
            return
        message = self.guardian_input.get().strip()
        if not message:
            return
        self.guardian_input.delete(0, "end")
        self.append_guardian_text("Du", message)
        self.request_guardian_reply(message)

    def request_guardian_reply(self, message: str | None) -> None:
        self.guardian_busy = True
        if self.guardian_send_button is not None:
            self.guardian_send_button.config(state="disabled")
        if self.guardian_input is not None:
            self.guardian_input.config(state="disabled")
        if self.guardian_status is not None:
            self.guardian_status.config(
                text="Die lokale KI antwortet ... Bitte kurz warten."
            )
        history = list(self.guardian_history)
        has_key = self.player.has_key

        def generate() -> None:
            try:
                reply = self.guardian_ai.reply(message, has_key, history)
            except Exception as error:
                self.guardian_queue.put((False, message, str(error)))
            else:
                self.guardian_queue.put((True, message, reply))

        Thread(target=generate, daemon=True).start()

    def poll_guardian_queue(self) -> None:
        if self.guard_dialog is None or not self.guard_dialog.winfo_exists():
            return
        try:
            succeeded, message, result = self.guardian_queue.get_nowait()
        except Empty:
            self.root.after(100, self.poll_guardian_queue)
            return

        if succeeded:
            if message is not None:
                self.guardian_history.append({"role": "user", "content": message})
            self.guardian_history.append({"role": "assistant", "content": result})
            self.append_guardian_text("Wächter", result)
            if self.guardian_status is not None:
                self.guardian_status.config(text="")
        else:
            self.append_guardian_text("Fehler", result)
            if self.guardian_status is not None:
                self.guardian_status.config(text="Die lokale KI konnte nicht antworten.")
        self.guardian_busy = False
        if self.guardian_send_button is not None:
            self.guardian_send_button.config(state="normal")
        if self.guardian_input is not None:
            self.guardian_input.config(state="normal")
            self.guardian_input.focus_set()
        self.root.after(100, self.poll_guardian_queue)


def main() -> None:
    try:
        root = tk.Tk()
    except tk.TclError:
        print("Das Spiel konnte keine grafische Oberfläche öffnen. Bitte in einer Desktop-Umgebung mit GUI ausführen.")
        return

    GameWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
