$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonDirectory = Join-Path $project ".runtime\python312"
$llamaDirectory = Join-Path $project "tools\llama.cpp"
$llamaServer = Join-Path $llamaDirectory "llama-server.exe"
$llamaVulkanLibrary = Join-Path $llamaDirectory "ggml-vulkan.dll"
$llamaArchive = Join-Path $project ".runtime\llama-b11718-bin-win-vulkan-x64.zip"
$modelPath = Join-Path $project "models\Tina-Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
$pythonInstaller = Join-Path $project ".runtime\python-3.12.10-amd64.exe"
$pythonExecutable = Join-Path $pythonDirectory "python.exe"
$voiceDirectory = Join-Path $project ".runtime\voice"
$speechModelDirectory = Join-Path $voiceDirectory "whisper-base"
$kokoroDirectory = Join-Path $voiceDirectory "kokoro"

New-Item -ItemType Directory -Force (Join-Path $project ".runtime") | Out-Null
New-Item -ItemType Directory -Force (Join-Path $project "models") | Out-Null

if (-not (Test-Path $modelPath)) {
    throw (
        "Das trainierte Tina-Modell fehlt: $modelPath`n" +
        "Kopiere Tina-Qwen3-4B-Instruct-2507-Q4_K_M.gguf in diesen Ordner."
    )
}
$expectedModelHash = "80647F2EE030B7336036ACF21C19D0E5139F9AD36A71BD5E6E7E50EDDFA648A6"
$actualModelHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $modelPath).Hash
if ($actualModelHash -ne $expectedModelHash) {
    throw "Die SHA-256-Prüfung des trainierten Tina-Modells ist fehlgeschlagen."
}

if (-not (Test-Path $pythonDirectory)) {
    if (-not (Test-Path $pythonInstaller)) {
        Write-Host "Lade Python 3.12 für Kokoro herunter..."
        Invoke-WebRequest `
            -Uri "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe" `
            -OutFile $pythonInstaller
    }
    Write-Host "Richte Python samt Tkinter lokal im Projekt ein..."
    $installArguments = @(
        "/quiet",
        "InstallAllUsers=0",
        "TargetDir=$pythonDirectory",
        "Include_tcltk=1",
        "Include_pip=0",
        "Include_launcher=0",
        "Include_test=0",
        "Shortcuts=0",
        "PrependPath=0"
    )
    $installer = Start-Process -FilePath $pythonInstaller `
        -ArgumentList $installArguments -Wait -PassThru
    if ($installer.ExitCode -ne 0) {
        throw "Python konnte nicht installiert werden (Exitcode $($installer.ExitCode))."
    }
    Remove-Item -LiteralPath $pythonInstaller -Force
}

if (-not (Test-Path (Join-Path $pythonDirectory "pythonw.exe"))) {
    throw "Die lokale Python-Installation ist unvollständig: $pythonDirectory"
}

if (-not (Test-Path $llamaServer) -or -not (Test-Path $llamaVulkanLibrary)) {
    if (-not (Test-Path $llamaArchive)) {
        Write-Host "Lade llama.cpp mit Vulkan-GPU-Unterstützung herunter..."
        Invoke-WebRequest `
            -Uri "https://github.com/ggml-org/llama.cpp/releases/download/b11718/llama-b11718-bin-win-vulkan-x64.zip" `
            -OutFile $llamaArchive
    }
    $llamaHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $llamaArchive).Hash
    if ($llamaHash -ne "237E5736031A9CDCF9EFF54E1F4E9BD871945DE1D56EC542ECB9EBAF8D45BDB6") {
        throw "Die SHA-256-Prüfung der llama.cpp-Laufzeit ist fehlgeschlagen."
    }
    Write-Host "Entpacke llama.cpp mit Vulkan-Unterstützung..."
    New-Item -ItemType Directory -Force $llamaDirectory | Out-Null
    Expand-Archive -Path $llamaArchive -DestinationPath $llamaDirectory -Force
    Remove-Item -LiteralPath $llamaArchive -Force
}

if (-not (Test-Path $llamaServer) -or -not (Test-Path $llamaVulkanLibrary)) {
    throw "llama.cpp oder die Vulkan-GPU-Bibliothek fehlt: $llamaDirectory"
}

Write-Host "Richte lokale Spracherkennung und Kokoro-Sprachwiedergabe ein..."
New-Item -ItemType Directory -Force $voiceDirectory | Out-Null
& $pythonExecutable -c "import importlib.util, sys; names = ['en_core_web_sm', 'faster_whisper', 'kokoro', 'numpy', 'sounddevice', 'torch']; sys.exit(1) if any(importlib.util.find_spec(name) is None for name in names) else None; import torch; sys.exit(0 if torch.__version__ == '2.6.0+cu124' and torch.cuda.is_available() and (torch.ones(1, device='cuda') + 1).item() == 2 else 1)"
if ($LASTEXITCODE -ne 0) {
    & $pythonExecutable -m ensurepip --upgrade
    if ($LASTEXITCODE -ne 0) {
        throw "Pip konnte für die lokale Sprachfunktion nicht eingerichtet werden."
    }
    & $pythonExecutable -m pip install --disable-pip-version-check -r (Join-Path $project "requirements-voice.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "Die lokalen Sprachpakete konnten nicht installiert werden."
    }
}
& $pythonExecutable -c "import sys, torch; sys.exit(0 if torch.__version__ == '2.6.0+cu124' and torch.cuda.is_available() and (torch.ones(1, device='cuda') + 1).item() == 2 else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "CUDA-PyTorch kann die NVIDIA-GPU nicht verwenden. Prüfe den NVIDIA-Treiber und die GPU-Kompatibilität."
}

$speechModelRevision = "ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66"
& $pythonExecutable -c "import sys; from huggingface_hub import snapshot_download; snapshot_download(repo_id='Systran/faster-whisper-base', revision='$speechModelRevision', local_dir=sys.argv[1], allow_patterns=['config.json', 'model.bin', 'tokenizer.json', 'vocabulary.txt'])" $speechModelDirectory
if ($LASTEXITCODE -ne 0) {
    throw "Das lokale Spracherkennungsmodell konnte nicht heruntergeladen werden."
}
$speechModelPath = Join-Path $speechModelDirectory "model.bin"
$speechModel = Get-Item -LiteralPath $speechModelPath
if ($speechModel.Length -ne 145217532) {
    throw "Das Spracherkennungsmodell ist unvollständig: $($speechModel.Length) Bytes statt 145217532."
}
$speechModelHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $speechModelPath).Hash
if ($speechModelHash -ne "D01C3014881C9C6F3133C182F3D2887EB6CA1C789A7538C5C007196857A0A6A9") {
    throw "Die SHA-256-Prüfung des Spracherkennungsmodells ist fehlgeschlagen."
}

$kokoroRevision = "f3ff3571791e39611d31c381e3a41a3af07b4987"
& $pythonExecutable -c "import sys; from huggingface_hub import snapshot_download; snapshot_download(repo_id='hexgrad/Kokoro-82M', revision='$kokoroRevision', local_dir=sys.argv[1], allow_patterns=['config.json', 'kokoro-v1_0.pth', 'voices/af_heart.pt'])" $kokoroDirectory
if ($LASTEXITCODE -ne 0) {
    throw "Kokoro-82M konnte nicht heruntergeladen werden."
}
$kokoroWeightsPath = Join-Path $kokoroDirectory "kokoro-v1_0.pth"
$kokoroWeights = Get-Item -LiteralPath $kokoroWeightsPath
if ($kokoroWeights.Length -ne 327212226) {
    throw "Das Kokoro-Modell ist unvollständig: $($kokoroWeights.Length) Bytes statt 327212226."
}
$kokoroWeightsHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $kokoroWeightsPath).Hash
if ($kokoroWeightsHash -ne "496DBA118D1A58F5F3DB2EFC88DBDC216E0483FC89FE6E47EE1F2C53F18AD1E4") {
    throw "Die SHA-256-Prüfung des Kokoro-Modells ist fehlgeschlagen."
}
$kokoroVoicePath = Join-Path $kokoroDirectory "voices\af_heart.pt"
$kokoroVoice = Get-Item -LiteralPath $kokoroVoicePath
if ($kokoroVoice.Length -ne 523425) {
    throw "Die Kokoro-Stimme ist unvollständig: $($kokoroVoice.Length) Bytes statt 523425."
}
$kokoroVoiceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $kokoroVoicePath).Hash
if ($kokoroVoiceHash -ne "0AB5709B8FFAB19BFD849CD11D98F75B60AF7733253AD0D67B12382A102CB4FF") {
    throw "Die SHA-256-Prüfung der Kokoro-Stimme ist fehlgeschlagen."
}

$llamaVersion = & $llamaServer --version
if ($LASTEXITCODE -ne 0) {
    throw "llama.cpp konnte nicht ausgeführt werden."
}

Write-Host "Setup vollständig. $llamaVersion"
