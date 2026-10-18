# ShowerEscape
Escape the shower.

Finde das Handtuch auf der Karte und bringe es zu Yumenko. Danach musst du sie
im Chat ueberzeugen, dir den Schluessel zu geben. Mit dem Schluessel kannst du
den Ausgang im Osten oeffnen.

## Starten

1. Stelle sicher, dass das trainierte Modell
   `models\Yumenko-Qwen3-4B-Instruct-2507-Q4_K_M.gguf` vorhanden ist, und führe einmal
   `SetupGame.cmd` aus. Das Setup lädt eine projektlokale Python-Laufzeit, llama.cpp
   mit Vulkan-Unterstützung und die lokalen Sprachmodelle herunter. Das trainierte
   Yumenko-Modell wird nicht aus dem Internet geladen und ist nicht im Git-Repository
   enthalten. Für Setup und Sprachpakete werden mehrere GB freier Speicher benötigt.
   Ein aktueller NVIDIA-Treiber mit Vulkan-Unterstützung ist erforderlich; CUDA-Toolkit,
   Visual Studio und globale Python-/KI-Installationen sind nicht nötig.
2. Danach reicht ein Doppelklick auf `PlayGame.cmd`. Ein Ladefenster erscheint,
   während zuerst Yumenkos KI und danach die Sprachmodelle geladen werden. Das Spiel
   öffnet sich erst, wenn beide bereit sind. Whisper bleibt im RAM und Kokoro im VRAM
   geladen, damit der Chat nicht erst auf den Sprachmodellstart warten muss. Die Modelle
   bleiben bis zum Schließen des Spiels geladen. Spiel und Unterhaltungen bleiben lokal.
   Das Setup lädt zusätzlich lokale Sprachmodelle, Sprachpakete und
   CUDA-PyTorch für Kokoros GPU-Beschleunigung herunter; dafür werden einige GB
   zusätzlich heruntergeladen. Kokoro nutzt die GPU, wenn mindestens 2 GB VRAM frei
   sind, andernfalls automatisch die CPU.
3. Öffne den Yumenko-Chat mit **T** oder über die Chat-Schaltfläche. Während der Chat
   geöffnet ist, kannst du einfach sprechen: Deine Sprache wird lokal erkannt und
   Yumenko antwortet automatisch mit Kokoro-82M-Stimme. Sie versteht Englisch und
   Deutsch und antwortet auf Englisch. Beim Schließen des Chats wird das Mikrofon
   gestoppt. Texteingabe bleibt als Alternative verfügbar. Das Sprachmodell wird
   lokal mit Vulkan auf der GPU ausgeführt. Kokoro nutzt CUDA, wenn mindestens
   2 GB VRAM frei sind, andernfalls automatisch die CPU. Emotionstags wie
   `{surprised}` bleiben im Gesprächsverlauf, werden aber nicht angezeigt oder
   vorgelesen. Das passende Emotionsbild wird neben dem Chat angezeigt.
   `GameWindow.guardian_emotions` und `GameWindow.guardian_emotion` stellen die
   Tags als Python-Werte für das Spiel bereit.

Die Laufzeiten und Modelldateien bleiben lokal und werden nicht mit Git committet.
Zum Aktualisieren des Quellcodes wird nur das Repository benötigt; nach dem Klonen
muss `SetupGame.cmd` einmal ausgeführt werden.

## Run

Zum direkten Start:

```powershell
.\.runtime\python312\python.exe game.py
```
