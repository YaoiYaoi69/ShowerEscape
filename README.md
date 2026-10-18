# ShowerEscape
Escape the shower.

Finde das Handtuch auf der Karte und bringe es zu Tina. Danach musst du sie
im Chat ueberzeugen, dir den Schluessel zu geben. Mit dem Schluessel kannst du
den Ausgang im Osten oeffnen.

## Starten

1. Stelle sicher, dass das trainierte Modell
   `models\Tina-Qwen3-4B-Instruct-2507-Q4_K_M.gguf` vorhanden ist, und führe einmal
   `SetupGame.cmd` aus. Das Setup lädt eine projektlokale Python-Laufzeit, llama.cpp
   mit Vulkan-Unterstützung und die lokalen Sprachmodelle herunter. Das trainierte
   Tina-Modell wird nicht aus dem Internet geladen und ist nicht im Git-Repository
   enthalten. Für Setup und Sprachpakete werden mehrere GB freier Speicher benötigt.
   Ein aktueller AMD- oder NVIDIA-Treiber mit Vulkan-Unterstützung wird empfohlen;
   CUDA-Toolkit, Visual Studio und globale Python-/KI-Installationen sind nicht nötig.
2. Danach reicht ein Doppelklick auf `PlayGame.cmd`. Ein Ladefenster erscheint,
   während das Spiel vorbereitet wird. Das Spiel öffnet sich, sobald es bereit
   ist. Die Modelle bleiben bis zum Schließen des Spiels geladen. Spiel und
   Unterhaltungen bleiben lokal. Das Setup lädt zusätzlich lokale
   Sprachmodelle und Sprachpakete herunter. NVIDIA-Systeme erhalten CUDA-PyTorch;
   AMD-Systeme erhalten CPU-PyTorch. Bei NVIDIA werden Whisper und Kokoro auf CUDA
   geladen; dafür müssen nach dem Start von Qwen noch mindestens 2 GB VRAM frei sein.
   Bei zu wenig VRAM meldet der Sprachchat einen Fehler, statt still auf die CPU
   zurückzufallen. Qwen läuft auf AMD und NVIDIA über Vulkan; bei AMD verwenden
   die Sprachmodelle die CPU.
3. Öffne den Tina-Chat mit **T** oder über die Chat-Schaltfläche. Während der Chat
   geöffnet ist, kannst du einfach sprechen: Deine Sprache wird lokal erkannt und
   Tina antwortet automatisch mit Kokoro-82M-Stimme. Sie versteht Englisch und
   Deutsch und antwortet auf Englisch. Beim Schließen des Chats wird das Mikrofon
   gestoppt. Texteingabe bleibt als Alternative verfügbar. Emotionstags wie
   `{surprised}` bleiben im Gesprächsverlauf, werden aber nicht angezeigt oder
   vorgelesen. Das passende Emotionsbild wird neben dem Chat angezeigt.
   `GameWindow.guardian_emotions` und `GameWindow.guardian_emotion` stellen die
   Tags als Python-Werte für das Spiel bereit.
4. Nach dem Öffnen des Ausgangs erscheint der Sieg-Bildschirm.

Die Laufzeiten und Modelldateien bleiben lokal und werden nicht mit Git committet.
Zum Aktualisieren des Quellcodes wird nur das Repository benötigt; nach dem Klonen
muss `SetupGame.cmd` einmal ausgeführt werden.

## Run

Zum direkten Start:

```powershell
.\.runtime\python312\python.exe game.py
```

## Portabler Windows-Export

Mit `ExportGame.ps1` wird eine vollständige Windows-x64-Ausgabe nach
`D:\ShowerEscapeGame` kopiert. Sie enthält Python, Spiel, Grafikdateien,
Sprachlaufzeit und die verwendeten KI-Modelle; ungenutzte Ollama-Caches bleiben
außen vor. Das fertige Paket benötigt beim Start keine Python- oder Modell-
Downloads. Wegen PyTorch und der lokalen Modelle ist es mehrere GB groß.

`PlayGame.cmd` startet das Spiel. `CheckDrivers.cmd` erkennt NVIDIA-/AMD-
Grafikkarten und öffnet die jeweilige offizielle Treiberseite. Mit aktuellem
Vulkan-Treiber nutzt Tina die GPU; andernfalls verwendet sie die CPU, was
langsamer sein kann. Die Treiberinstallation ist herstellerspezifisch und
erfordert Internet; Python muss nicht systemweit installiert werden.
