# ShowerEscape
Escape the shower.

## Starten

1. Führe einmal `SetupGame.cmd` aus. Das Setup lädt eine projektlokale Python-
   Laufzeit, Ollama für Windows mit NVIDIA-Unterstützung und das GGUF-Modell herunter.
   Der Download umfasst etwa 2 GB; durch Entpacken und lokalen Modellimport werden
   insgesamt etwa 4 GB freier Speicher benötigt. Ein NVIDIA-Treiber muss installiert
   sein (für eine GTX 1070 mindestens Version 570). CUDA-Toolkit, Visual Studio und
   globale Python-/KI-Installationen sind nicht erforderlich.
2. Danach reicht ein Doppelklick auf `PlayGame.cmd`. Das Spiel lädt die Wächter-KI
   gleich beim Start im Hintergrund in den GPU-Speicher. Bis die Meldung erscheint,
   dass sie geladen ist, dauert es beim ersten Start etwas länger. Danach bleibt sie
   bis zum Schließen des Spiels bereit. Spiel und Unterhaltungen bleiben lokal. Die
   Einstellung ist für eine GTX 1070 mit 8 GB geeignet und nutzt auch eine RTX 4060.
   Zum Chatten kannst du jederzeit auf **Mit dem Wächter chatten** klicken oder **T**
   drücken. Die Wächter-Anweisungen sind auf Englisch formuliert; er antwortet in der
   Sprache deiner Nachricht und kann sich auch über andere Themen unterhalten.

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
