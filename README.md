# ShowerEscape
Escape the shower.

## Starten

1. Führe einmal `SetupGame.cmd` aus. Das Setup lädt eine projektlokale Python-
   Laufzeit, Ollama für Windows mit NVIDIA-Unterstützung und das GGUF-Modell herunter.
   Der Download umfasst etwa 4 GB; durch Entpacken und lokalen Modellimport werden
   insgesamt etwa 8 GB freier Speicher benötigt. Ein NVIDIA-Treiber muss installiert
   sein (für eine GTX 1070 mindestens Version 570). CUDA-Toolkit, Visual Studio und
   globale Python-/KI-Installationen sind nicht erforderlich.
2. Danach reicht ein Doppelklick auf `PlayGame.cmd`. Ein Ladefenster erscheint,
   während Yumenkos KI im Hintergrund in den GPU-Speicher geladen wird. Das Spiel
   öffnet sich erst, wenn die KI bereit ist; beim ersten Start kann das etwas dauern.
   Danach bleibt sie bis zum Schließen des Spiels bereit. Spiel und Unterhaltungen
   bleiben lokal. Die
   Einstellung ist für eine GTX 1070 mit 8 GB geeignet und nutzt auch eine RTX 4060.
   Zum Chatten kannst du jederzeit auf **Mit Yumenko chatten** klicken oder **T**
   drücken. Yumenkos Charakter-Anweisungen sind auf Englisch formuliert; sie antwortet
   immer auf Englisch und kann sich auch über andere Themen unterhalten.

Die Laufzeiten und Modelldateien bleiben lokal und werden nicht mit Git committet.
Zum Aktualisieren des Quellcodes wird nur das Repository benötigt; nach dem Klonen
muss `SetupGame.cmd` einmal ausgeführt werden.

## Run

Zum direkten Start mit einer bereits installierten Python-Installation:

```powershell
python game.py
```

In Windows ohne portable Laufzeit:

```powershell
python game.py
```
