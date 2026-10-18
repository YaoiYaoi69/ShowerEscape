$ErrorActionPreference = "Stop"
$source = $PSScriptRoot
$destination = "D:\ShowerEscapeGame"
$requiredModel = Join-Path $source "models\Tina-Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
$requiredPaths = @(
    ".runtime\python312",
    ".runtime\voice",
    "tools\llama.cpp",
    "assets",
    "game.py",
    "guardian_ai.py",
    "voice_chat.py",
    "emotion_tags.py"
)

if (-not (Test-Path -LiteralPath $requiredModel -PathType Leaf)) {
    throw "Das lokale Tina-Modell fehlt: $requiredModel"
}
$modelHash = (Get-FileHash -LiteralPath $requiredModel -Algorithm SHA256).Hash
if ($modelHash -ne "80647F2EE030B7336036ACF21C19D0E5139F9AD36A71BD5E6E7E50EDDFA648A6") {
    throw "Die SHA-256-Pruefung des Tina-Modells ist fehlgeschlagen."
}
foreach ($relativePath in $requiredPaths) {
    if (-not (Test-Path -LiteralPath (Join-Path $source $relativePath))) {
        throw "Eine benoetigte Spieldatei fehlt: $relativePath"
    }
}

if (Test-Path -LiteralPath $destination) {
    $existingItems = @(Get-ChildItem -LiteralPath $destination -Force)
    if ($existingItems.Count -gt 0) {
        throw "Der Exportordner ist nicht leer. Vorhandene Dateien bleiben unveraendert: $destination"
    }
} else {
    New-Item -ItemType Directory -Path $destination | Out-Null
}

$copyPaths = @(
    ".runtime\python312",
    ".runtime\voice",
    "tools\llama.cpp",
    "assets"
)
$totalBytes = [long](Get-Item -LiteralPath $requiredModel).Length
foreach ($relativePath in $copyPaths) {
    $totalBytes += [long](
        Get-ChildItem -LiteralPath (Join-Path $source $relativePath) -Recurse -File |
            Measure-Object -Property Length -Sum
    ).Sum
}
$destinationDrive = (Get-Item -LiteralPath $destination).PSDrive
if ($destinationDrive.Free -lt $totalBytes) {
    throw (
        "Fuer den vollstaendigen Offline-Export werden mindestens " +
        "$([math]::Ceiling($totalBytes / 1GB)) GB freier Speicher benoetigt."
    )
}

New-Item -ItemType Directory -Force (Join-Path $destination ".runtime") | Out-Null
New-Item -ItemType Directory -Force (Join-Path $destination "tools") | Out-Null
New-Item -ItemType Directory -Force (Join-Path $destination "models") | Out-Null
foreach ($relativePath in $copyPaths) {
    $targetParent = if ($relativePath.StartsWith(".runtime\")) {
        Join-Path $destination ".runtime"
    } elseif ($relativePath.StartsWith("tools\")) {
        Join-Path $destination "tools"
    } else {
        $destination
    }
    Copy-Item `
        -LiteralPath (Join-Path $source $relativePath) `
        -Destination $targetParent `
        -Recurse
}
Copy-Item -LiteralPath $requiredModel -Destination (Join-Path $destination "models")
foreach ($relativePath in @("game.py", "guardian_ai.py", "voice_chat.py", "emotion_tags.py")) {
    Copy-Item -LiteralPath (Join-Path $source $relativePath) -Destination $destination
}

$launcher = @'
@echo off
setlocal
cd /d "%~dp0"
if not exist ".runtime\python312\pythonw.exe" (
    echo Die mitgelieferte Python-Laufzeit fehlt. Bitte das Spiel erneut entpacken.
    pause
    exit /b 1
)
start "" ".runtime\python312\pythonw.exe" "%~dp0game.py"
'@
[System.IO.File]::WriteAllText(
    (Join-Path $destination "PlayGame.cmd"),
    $launcher,
    [System.Text.UTF8Encoding]::new($false)
)

$driverCheck = @'
$ErrorActionPreference = "Stop"
$videoAdapters = @(Get-CimInstance -ClassName Win32_VideoController)
$adapterNames = @($videoAdapters | ForEach-Object { $_.Name })
$hasNvidia = @($adapterNames | Where-Object { $_ -match "NVIDIA" }).Count -gt 0
$hasAmd = @($adapterNames | Where-Object { $_ -match "AMD|Radeon|ATI" }).Count -gt 0

Write-Host "Erkannte Grafikadapter:"
if ($adapterNames.Count -eq 0) {
    Write-Host "  Keine erkannt; Tina kann auf der CPU laufen."
}
$adapterNames | ForEach-Object { Write-Host "  $_" }

if ($hasNvidia) {
    Write-Host "Oeffne die offizielle NVIDIA-Treibersuche."
    Start-Process "https://www.nvidia.com/Download/index.aspx?lang=en-us"
}
if ($hasAmd) {
    Write-Host "Oeffne die offizielle AMD-Treiberseite."
    Start-Process "https://www.amd.com/en/support/download/drivers.html"
}
if (-not $hasNvidia -and -not $hasAmd) {
    Write-Host "Kein NVIDIA-/AMD-Adapter erkannt. Das Spiel verwendet die CPU."
}
Write-Host "Waehle dort den passenden Treiber und installiere ihn mit Herstellerrechten."
'@
[System.IO.File]::WriteAllText(
    (Join-Path $destination "CheckDrivers.ps1"),
    $driverCheck,
    [System.Text.UTF8Encoding]::new($true)
)

$driverLauncher = @'
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0CheckDrivers.ps1"
pause
'@
[System.IO.File]::WriteAllText(
    (Join-Path $destination "CheckDrivers.cmd"),
    $driverLauncher,
    [System.Text.UTF8Encoding]::new($false)
)

$readme = @'
ShowerEscape - portable Ausgabe (Windows x64)

Start:
  Doppelklick auf PlayGame.cmd

Python 3.12, die lokalen Sprachmodelle, Tina-KI, llama.cpp und alle
Spielgrafiken sind in diesem Ordner enthalten. Eine globale Python-
Installation oder ein Download beim Spielen ist nicht erforderlich.

Die Tina-KI nutzt automatisch die erste verfuegbare Vulkan-GPU (NVIDIA
oder AMD). Ohne Vulkan-GPU startet sie auf der CPU; Antworten koennen dann
deutlich langsamer sein. Fuer Grafiktreiber CheckDrivers.cmd oeffnen. Das
Skript erkennt NVIDIA-/AMD-Karten und oeffnet die offizielle Treiberseite.
Treiberwahl und Installation fuehrt der Hersteller-Installer aus; dafuer
sind Internet und je nach Treiber Administratorrechte erforderlich.

Sprachchat und lokale KI funktionieren nach dem Entpacken offline.
Benoetigt Windows x64 und mehrere GB freien Arbeitsspeicher; fuer gute
CPU-Leistung wird eine Vulkan-faehige GPU mit aktuellem Herstellertreiber
empfohlen. Beim ersten Start dauert das Laden der lokalen Modelle.

Das vollstaendige Paket ist wegen Python/PyTorch und der lokalen Modelle
mehrere GB gross. Nicht verwendete Ollama-Modell-Caches sind nicht enthalten.
'@
[System.IO.File]::WriteAllText(
    (Join-Path $destination "README.txt"),
    $readme,
    [System.Text.UTF8Encoding]::new($true)
)

Write-Host (
    "Portabler Export erstellt: $destination " +
    "({0:N2} GB Quelldaten)" -f ($totalBytes / 1GB)
)
