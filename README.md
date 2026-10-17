# ShowerEscape
Escape the shower.

## Starten

1. Führe einmal `SetupGame.cmd` aus. Das Setup lädt eine projektlokale Python-
   Laufzeit, Ollama für Windows mit NVIDIA-Unterstützung und das GGUF-Modell herunter.
   Der Download umfasst etwa 4,7 GB; durch Entpacken, Sprachpakete und lokalen
   Modellimport werden insgesamt etwa 13 GB freier Speicher benötigt. Ein NVIDIA-Treiber
   muss installiert sein (für eine GTX 1070 mindestens Version 570). CUDA-Toolkit,
   Visual Studio und globale Python-/KI-Installationen sind nicht erforderlich.
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
   gestoppt. Texteingabe bleibt als Alternative verfügbar. Die Einstellung ist für
   eine GTX 1070 mit 8 GB geeignet und nutzt auch eine RTX 4060.

Die Laufzeiten und Modelldateien bleiben lokal und werden nicht mit Git committet.
Zum Aktualisieren des Quellcodes wird nur das Repository benötigt; nach dem Klonen
muss `SetupGame.cmd` einmal ausgeführt werden.

## Run

Zum direkten Start:

```powershell
.\.runtime\python312\python.exe game.py
```
