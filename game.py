from __future__ import annotations

from queue import Empty, Queue
from threading import Thread
import tkinter as tk
from dataclasses import dataclass
from math import gcd
from pathlib import Path

from emotion_tags import parse_emotion_tags
from guardian_ai import GuardianAI, GuardianResponse
from voice_chat import VoiceChat, VoiceEvent


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
EMOTION_IMAGE_DIR = Path(__file__).resolve().parent / "assets" / "emotions"
EMOTION_IMAGE_FILES = {
    "angry": "angry.png",
    "embarrassed": "embarrased.png",
    "happy": "happy.png",
    "scared": "scared.png",
    "surprised": "surprised.png",
}
EMOTION_IMAGE_MAX_SIZE = 520

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


def guardian_dialog_dimensions(
    screen_width: int,
    screen_height: int,
) -> tuple[int, int, int, int]:
    portrait_size = min(
        EMOTION_IMAGE_MAX_SIZE,
        max(160, (screen_width - 120) // 2),
        max(160, screen_height - 204),
    )
    chat_width = portrait_size
    window_width = portrait_size * 2 + 96
    window_height = min(screen_height - 24, portrait_size + 180)
    return portrait_size, chat_width, window_width, window_height


@dataclass
class Player:
    x: int = scale_coordinate(120)
    y: int = scale_coordinate(120)
    has_towel: bool = False
    towel_delivered: bool = False
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
    Place("Handtuch", 216, 120, "Ein sauberes Handtuch. Yumenko braucht es.", "towel"),
    Place(
        "Yumenko",
        600,
        312,
        "Yumenko haelt den Schluessel und moechte zuerst ihr Handtuch haben.",
        "guard",
    ),
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

    if place.kind == "towel":
        if place.used:
            return "Hier liegt kein Handtuch mehr.", False
        if player.has_towel:
            return "Du hast das Handtuch bereits.", False
        player.has_towel = True
        place.used = True
        return "Du hast Yumenkos Handtuch genommen. Bring es zu ihr.", False
    if place.kind == "guard":
        if not player.towel_delivered:
            if not player.has_towel:
                return (
                    "Yumenko sagt: Bring mir erst mein Handtuch, dann reden wir "
                    "ueber den Schluessel.",
                    False,
                )
            player.has_towel = False
            player.towel_delivered = True
            return (
                "Du gibst Yumenko ihr Handtuch. Jetzt musst du sie ueberzeugen, "
                "dir den Schluessel zu geben.",
                False,
            )
        return "Yumenko wartet darauf, dass du sie im Chat ueberzeugst.", False
    if place.kind == "exit":
        if player.has_key:
            return "Mit dem Schluessel oeffnest du den Ausgang. Geschafft!", True
        return (
            "Der Ausgang ist verschlossen. Ueberzeuge Yumenko, dir ihren "
            "Schluessel zu geben.",
            False,
        )
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
            / "Yumenko-Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
        )
        self.guardian_history: list[dict[str, str]] = []
        self.guardian_emotions: tuple[str, ...] = ()
        self.guardian_emotion: str | None = None
        self.guardian_busy = False
        self.guardian_greeting_started = False
        self.guardian_model_ready = False
        self.voice_ready = False
        self.voice_error: str | None = None
        self.guard_dialog: tk.Toplevel | None = None
        self.guard_was_nearby = False
        self.guardian_messages: tk.Text | None = None
        self.guardian_emotion_label: tk.Label | None = None
        self.guardian_emotion_title: tk.Label | None = None
        self.guardian_emotion_images: dict[str, tk.PhotoImage] = {}
        self.guardian_input: tk.Entry | None = None
        self.guardian_chat_button: tk.Button | None = None
        self.guardian_status: tk.Label | None = None
        self.guardian_send_button: tk.Button | None = None
        self.guardian_queue: Queue[
            tuple[bool, str | None, GuardianResponse | str]
        ] = Queue()
        self.guardian_warmup_queue: Queue[tuple[bool, str | None]] = Queue()
        self.guardian_warmup_started = False
        self.loading_dialog: tk.Toplevel | None = None
        self.loading_status: tk.Label | None = None
        self.loading_retry_button: tk.Button | None = None
        self.voice_events: Queue[VoiceEvent] = Queue()
        self.voice_chat: VoiceChat | None = None
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
            text=(
                "Finde Yumenkos Handtuch, bring es ihr und ueberzeuge sie, "
                "dir den Schluessel zu geben."
            ),
            font=("Segoe UI", 10),
            fg="#e2e8f0",
            bg="#1c2630",
            wraplength=WORLD_WIDTH,
            pady=4,
        )
        self.message_label.pack()

        self.guardian_chat_button = tk.Button(
            root,
            text="Mit Yumenko chatten",
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
            text="WASD bewegen    E interagieren    T Yumenko-Chat    Esc beenden",
            font=("Segoe UI", 10),
            fg="#94a3b8",
            bg="#1c2630",
            pady=10,
        )
        controls.pack()

        root.bind_all("<KeyPress>", self.on_key)
        self.draw()
        self.show_loading_dialog()
        root.after(200, self.start_guardian_warmup)
        root.after(100, self.poll_guardian_warmup)
        root.after(100, self.poll_voice_queue)

    def show_loading_dialog(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("ShowerEscape")
        dialog.geometry("420x150")
        dialog.resizable(False, False)
        dialog.configure(bg="#1c2630")
        dialog.protocol("WM_DELETE_WINDOW", self.close_game)

        self.loading_status = tk.Label(
            dialog,
            text=(
                "Yumenkos KI wird geladen. Danach werden die Sprachmodelle "
                "vorbereitet ..."
            ),
            font=("Segoe UI", 11),
            fg="#e2e8f0",
            bg="#1c2630",
            wraplength=380,
            pady=24,
        )
        self.loading_status.pack(fill="x")

        self.loading_retry_button = tk.Button(
            dialog,
            text="Erneut versuchen",
            command=self.start_guardian_warmup,
            font=("Segoe UI", 10, "bold"),
            fg="#f1f5f9",
            bg="#6d28d9",
            activebackground="#7c3aed",
            activeforeground="#ffffff",
        )
        dialog.update_idletasks()
        x = max(0, (dialog.winfo_screenwidth() - 420) // 2)
        y = max(0, (dialog.winfo_screenheight() - 150) // 2)
        dialog.geometry(f"420x150+{x}+{y}")
        self.loading_dialog = dialog

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
            if place.kind == "towel":
                self.canvas.create_rectangle(
                    x0,
                    y0,
                    x1,
                    y1,
                    fill="#f8fafc" if not place.used else "#64748b",
                    outline="#38bdf8",
                    width=outline_width,
                )
                self.canvas.create_line(
                    x0 + scale_coordinate(6),
                    place_y,
                    x1 - scale_coordinate(6),
                    place_y,
                    fill="#38bdf8",
                    width=outline_width,
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
            text=(
                f"Handtuch: {'Ja' if self.player.has_towel else 'Nein'}"
                f"    Schluessel: {'Ja' if self.player.has_key else 'Nein'}"
            )
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
            if (
                is_near_guard
                and self.player.towel_delivered
                and not self.guard_was_nearby
            ):
                self.open_guard_dialog()
            self.guard_was_nearby = is_near_guard
        elif key == "e":
            place = nearby_place(self.player)
            if place is not None and place.kind == "guard":
                if self.player.towel_delivered:
                    self.open_guard_dialog()
                else:
                    message, _ = interact(self.player)
                    self.message_label.config(text=message)
                    self.draw()
                return
            message, self.won = interact(self.player)
            self.message_label.config(text=message)
            self.draw()
            if self.won:
                self.message_label.config(fg="#86efac")

    def close_game(self) -> None:
        self.close_guard_dialog()
        if self.voice_chat is not None:
            self.voice_chat.stop()
            self.voice_chat = None
        self.guardian_ai.shutdown()
        self.root.destroy()

    def start_guardian_warmup(self) -> None:
        if self.guardian_warmup_started:
            return
        self.guardian_warmup_started = True
        if self.loading_status is not None:
            self.loading_status.config(
                text=(
                    "Yumenkos KI wird geladen. Danach werden die Sprachmodelle "
                    "vorbereitet ..."
                )
            )
        if self.loading_retry_button is not None:
            self.loading_retry_button.pack_forget()

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
            self.guardian_model_ready = True
            if self.loading_status is not None:
                self.loading_status.config(
                    text="Yumenkos KI ist bereit. Sprachmodelle werden geladen ..."
                )
            if self.voice_chat is None:
                self.voice_chat = VoiceChat(
                    Path(__file__).resolve().parent,
                    self.voice_events,
                )
                self.voice_chat.start()
            self._show_game_when_models_ready()
        else:
            self.guardian_warmup_started = False
            if self.loading_status is not None:
                self.loading_status.config(
                    text=f"Yumenkos KI konnte nicht geladen werden:\n{error}"
                )
            if self.loading_retry_button is not None:
                self.loading_retry_button.pack(pady=(0, 12))
            self.root.after(100, self.poll_guardian_warmup)

    def _show_game_when_models_ready(self) -> None:
        if not self.guardian_model_ready or not (self.voice_ready or self.voice_error):
            return
        if self.voice_error:
            self.message_label.config(
                text=(
                    "Yumenko ist bereit. Sprache nicht verfügbar; "
                    "Texteingabe bleibt möglich."
                )
            )
        else:
            self.message_label.config(
                text="Yumenko ist bereit. Gehe zu ihr und chatte mit ihr."
            )
        if self.loading_dialog is not None and self.loading_dialog.winfo_exists():
            self.loading_dialog.destroy()
        self.loading_dialog = None
        self.root.deiconify()

    def open_guard_dialog(self) -> None:
        if self.guard_dialog is not None and self.guard_dialog.winfo_exists():
            self.guard_dialog.lift()
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Yumenko")
        dialog.resizable(True, True)
        dialog.transient(self.root)
        dialog.configure(bg="#1c2630")
        dialog.update_idletasks()
        self.guard_dialog = dialog
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        if not self.guardian_emotion_images:
            target_image_size = guardian_dialog_dimensions(
                screen_width,
                screen_height,
            )[0]
            self.guardian_emotion_images = self.load_emotion_images(
                target_image_size
            )
        portrait_size = self.guardian_emotion_images["scared"].width()
        _, chat_width, window_width, window_height = guardian_dialog_dimensions(
            screen_width,
            screen_height,
        )
        x = max(0, (screen_width - window_width) // 2)
        y = max(0, (screen_height - window_height) // 2)
        dialog.geometry(f"{window_width}x{window_height}+{x}+{y}")

        if self.voice_chat is None:
            self.voice_chat = VoiceChat(
                Path(__file__).resolve().parent,
                self.voice_events,
            )
            self.voice_error = None
            self.voice_ready = False
            self.voice_chat.start()
        header = tk.Frame(dialog, bg="#1c2630")
        header.pack(side="top", fill="x", padx=18, pady=(14, 8))
        tk.Label(
            header,
            text="YUMENKO",
            font=("Segoe UI", 16, "bold"),
            fg="#f1f5f9",
            bg="#1c2630",
        ).pack(side="left")
        tk.Label(
            header,
            text="GESPRÄCH",
            font=("Segoe UI", 9, "bold"),
            fg="#a78bfa",
            bg="#1c2630",
        ).pack(side="left", padx=(12, 0), pady=(4, 0))

        panels = tk.Frame(dialog, bg="#1c2630")
        panels.pack(side="top", fill="both", expand=True, padx=18)
        chat_panel = tk.Frame(
            panels,
            bg="#1c2630",
            width=chat_width,
            height=portrait_size + 24,
        )
        chat_panel.pack(side="left", fill="both", expand=False)
        chat_panel.pack_propagate(False)
        portrait_panel = tk.Frame(
            panels,
            bg="#1c2630",
            width=portrait_size,
            height=portrait_size + 24,
        )
        portrait_panel.pack(side="right", fill="both", padx=(16, 0))
        portrait_panel.pack_propagate(False)
        tk.Label(
            chat_panel,
            text="CHAT",
            font=("Segoe UI", 9, "bold"),
            fg="#94a3b8",
            bg="#1c2630",
            anchor="w",
        ).pack(fill="x", pady=(0, 7))
        self.guardian_emotion_title = tk.Label(
            portrait_panel,
            text=(self.guardian_emotion or "scared").upper(),
            font=("Segoe UI", 9, "bold"),
            fg="#c4b5fd",
            bg="#1c2630",
            anchor="w",
        )
        self.guardian_emotion_title.pack(fill="x", pady=(0, 7))

        chat_body = tk.Frame(
            chat_panel,
            bg="#0f172a",
            width=chat_width,
            height=portrait_size,
            highlightthickness=1,
            highlightbackground="#334155",
        )
        chat_body.pack(fill="both", expand=True)
        chat_body.pack_propagate(False)
        scrollbar = tk.Scrollbar(
            chat_body,
            bg="#1e293b",
            troughcolor="#0f172a",
            activebackground="#475569",
            relief="flat",
            borderwidth=0,
        )
        scrollbar.pack(side="right", fill="y")
        self.guardian_messages = tk.Text(
            chat_body,
            state="disabled",
            wrap="word",
            font=("Segoe UI", 11),
            bg="#0f172a",
            fg="#e2e8f0",
            insertbackground="#f8fafc",
            padx=14,
            pady=14,
            relief="flat",
            borderwidth=0,
            yscrollcommand=scrollbar.set,
        )
        self.guardian_messages.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.guardian_messages.yview)
        portrait_frame = tk.Frame(
            portrait_panel,
            bg="#0f172a",
            width=portrait_size,
            height=portrait_size,
            highlightthickness=1,
            highlightbackground="#334155",
        )
        portrait_frame.pack()
        portrait_frame.pack_propagate(False)
        self.guardian_emotion_label = tk.Label(
            portrait_frame,
            image=self.guardian_emotion_images["scared"],
            bg="#0f172a",
            borderwidth=0,
        )
        self.guardian_emotion_label.pack(fill="both", expand=True)
        self.guardian_status = tk.Label(
            dialog,
            text="Yumenkos Sprachchat wird vorbereitet ...",
            font=("Segoe UI", 9),
            fg="#a5b4c7",
            bg="#1c2630",
            justify="left",
            wraplength=window_width - 36,
        )

        input_row = tk.Frame(
            dialog,
            bg="#0f172a",
            highlightthickness=1,
            highlightbackground="#334155",
        )
        input_row.pack(side="bottom", fill="x", padx=18, pady=(8, 14))
        self.guardian_input = tk.Entry(
            input_row,
            font=("Segoe UI", 11),
            fg="#f1f5f9",
            bg="#0f172a",
            insertbackground="#f8fafc",
            relief="flat",
            borderwidth=0,
        )
        self.guardian_input.pack(side="left", fill="x", expand=True, padx=12, ipady=10)
        self.guardian_send_button = tk.Button(
            input_row,
            text="Senden",
            command=self.send_guardian_message,
            font=("Segoe UI", 10, "bold"),
            fg="#ffffff",
            bg="#6d28d9",
            activebackground="#7c3aed",
            activeforeground="#ffffff",
            relief="flat",
            borderwidth=0,
            padx=18,
            pady=8,
        )
        self.guardian_send_button.pack(side="right", padx=6, pady=6)
        self.guardian_status.pack(side="bottom", anchor="w", padx=20, pady=(8, 0))
        self.update_guardian_emotion(self.guardian_emotion or "scared")
        self.guardian_input.bind("<Return>", self.send_guardian_message)
        dialog.bind("<Return>", self.send_guardian_message)
        dialog.protocol("WM_DELETE_WINDOW", self.close_guard_dialog)
        dialog.grab_set()
        dialog.deiconify()
        dialog.lift()
        dialog.attributes("-topmost", True)
        dialog.after(500, lambda: dialog.winfo_exists() and dialog.attributes("-topmost", False))
        dialog.after_idle(self.guardian_input.focus_force)

        for entry in self.guardian_history:
            speaker = "Du" if entry["role"] == "user" else "Yumenko"
            text = entry["content"]
            if entry["role"] == "assistant":
                text, _ = parse_emotion_tags(text)
            self.append_guardian_text(speaker, text)
        if not self.guardian_greeting_started:
            self.guardian_greeting_started = True
            self.request_guardian_reply(None)
        elif self.guardian_busy:
            self.guardian_status.config(text="Die lokale KI antwortet gerade ...")
            self.guardian_send_button.config(state="disabled")
        else:
            if self.voice_error is not None:
                self.guardian_status.config(
                    text=(
                        f"Sprachchat nicht verfügbar: {self.voice_error}. "
                        "Du kannst weiterhin schreiben."
                    )
                )
            else:
                self.guardian_status.config(text="Du kannst direkt mit Yumenko sprechen.")
            if self.voice_chat is not None:
                self.voice_chat.listen()
        self.poll_guardian_queue()

    def close_guard_dialog(self) -> None:
        if self.voice_chat is not None:
            self.voice_chat.pause()
            self.voice_chat.cancel_speech()
        if self.guard_dialog is not None:
            self.guard_dialog.grab_release()
            self.guard_dialog.destroy()
        self.guard_dialog = None
        self.guardian_messages = None
        self.guardian_emotion_label = None
        self.guardian_emotion_title = None
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

    @staticmethod
    def load_emotion_images(max_size: int = EMOTION_IMAGE_MAX_SIZE) -> dict[str, tk.PhotoImage]:
        images: dict[str, tk.PhotoImage] = {}
        for emotion, filename in EMOTION_IMAGE_FILES.items():
            image_path = EMOTION_IMAGE_DIR / filename
            if not image_path.is_file():
                raise FileNotFoundError(f"Emotionsbild nicht gefunden: {image_path}")
            image = tk.PhotoImage(file=str(image_path))
            factor = max(
                1,
                (max(image.width(), image.height()) + max_size - 1) // max_size,
            )
            images[emotion] = image.subsample(factor, factor)
        return images

    def update_guardian_emotion(self, emotion: str) -> None:
        if self.guardian_emotion_label is None:
            return
        image = self.guardian_emotion_images[emotion]
        self.guardian_emotion_label.config(image=image)
        if self.guardian_emotion_title is not None:
            self.guardian_emotion_title.config(text=emotion.upper())

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
        self.guardian_emotions = ()
        if self.voice_chat is not None:
            self.voice_chat.pause()
            self.voice_chat.cancel_speech()
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
        towel_delivered = self.player.towel_delivered

        def generate() -> None:
            try:
                reply = self.guardian_ai.reply(
                    message, has_key, history, towel_delivered=towel_delivered
                )
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
            if not isinstance(result, GuardianResponse):
                raise TypeError("Die lokale KI hat ein ungültiges Antwortformat geliefert.")
            if message is not None:
                self.guardian_history.append({"role": "user", "content": message})
            self.guardian_history.append(
                {"role": "assistant", "content": result.tagged_text}
            )
            self.guardian_emotions = result.emotions
            if result.emotions:
                self.guardian_emotion = result.emotions[-1]
                self.update_guardian_emotion(self.guardian_emotion)
            self.append_guardian_text("Yumenko", result.text)
            if result.key_given:
                self.player.has_key = True
                self.message_label.config(
                    text="Yumenko gibt dir den Schluessel. Geh zum Ausgang im Osten."
                )
                self.draw()
            if self.voice_chat is not None:
                self.voice_chat.speak(result.text)
                if self.guardian_status is not None:
                    self.guardian_status.config(text="Yumenko spricht ...")
        else:
            self.append_guardian_text("Fehler", result)
            if self.guardian_status is not None:
                self.guardian_status.config(text="Die lokale KI konnte nicht antworten.")
            if self.voice_chat is not None:
                self.voice_chat.listen()
        self.guardian_busy = False
        if self.guardian_send_button is not None:
            self.guardian_send_button.config(state="normal")
        if self.guardian_input is not None:
            self.guardian_input.config(state="normal")
            self.guardian_input.focus_set()
        self.root.after(100, self.poll_guardian_queue)

    def poll_voice_queue(self) -> None:
        try:
            event, message = self.voice_events.get_nowait()
        except Empty:
            if self.root.winfo_exists():
                self.root.after(100, self.poll_voice_queue)
            return

        if event == "ready":
            self.voice_ready = True
            self.voice_error = None
            self._show_game_when_models_ready()
            if not self.guardian_busy and self.guardian_status is not None:
                device_name = "GPU" if message == "cuda" else "CPU"
                self.guardian_status.config(
                    text=f"Der Sprachchat ist bereit ({device_name})."
                )
        elif event == "listening":
            if (
                self.guard_dialog is not None
                and self.guard_dialog.winfo_exists()
                and not self.guardian_busy
                and self.guardian_status is not None
            ):
                self.guardian_status.config(text="Yumenko hört zu ...")
        elif event == "transcript" and message:
            if self.guard_dialog is not None and self.guard_dialog.winfo_exists():
                self.append_guardian_text("Du", message)
                self.request_guardian_reply(message)
        elif event == "spoken":
            if self.voice_chat is not None and not self.guardian_busy:
                self.voice_chat.listen()
        elif event == "error":
            self.voice_error = message or "Unbekannter Sprachfehler"
            self.voice_ready = False
            if message:
                if self.guard_dialog is not None and self.guard_dialog.winfo_exists():
                    self.append_guardian_text("Sprachfehler", message)
            if self.voice_chat is not None:
                self.voice_chat.stop()
                self.voice_chat = None
            self._show_game_when_models_ready()
            if (
                self.guard_dialog is not None
                and self.guard_dialog.winfo_exists()
                and self.guardian_status is not None
            ):
                self.guardian_status.config(
                    text=(
                        f"Sprachchat nicht verfügbar: {self.voice_error}. "
                        "Du kannst weiterhin schreiben."
                    )
                )
        if self.root.winfo_exists():
            self.root.after(100, self.poll_voice_queue)


def main() -> None:
    try:
        root = tk.Tk()
    except tk.TclError:
        print("Das Spiel konnte keine grafische Oberfläche öffnen. Bitte in einer Desktop-Umgebung mit GUI ausführen.")
        return

    root.withdraw()
    GameWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
