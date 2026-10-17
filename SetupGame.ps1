$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonDirectory = Join-Path $project ".runtime\python"
$ollamaDirectory = Join-Path $project "tools\ollama"
$ollamaArchive = Join-Path $project ".runtime\ollama-windows-amd64.zip"
$modelPath = Join-Path $project "models\Qwen3-VL-4B-Instruct-Uncensored.Q4_K_M.gguf"
$pythonInstaller = Join-Path $project ".runtime\python-3.13.16-amd64.exe"

New-Item -ItemType Directory -Force (Join-Path $project ".runtime") | Out-Null
New-Item -ItemType Directory -Force (Join-Path $project "models") | Out-Null

if (-not (Test-Path $pythonDirectory)) {
    if (-not (Test-Path $pythonInstaller)) {
        Write-Host "Lade Python 3.13 herunter..."
        Invoke-WebRequest `
            -Uri "https://www.python.org/ftp/python/3.13.16/python-3.13.16-amd64.exe" `
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

if (-not (Test-Path (Join-Path $ollamaDirectory "ollama.exe"))) {
    if (-not (Test-Path $ollamaArchive)) {
        Write-Host "Lade portable Ollama-Laufzeit mit NVIDIA-Bibliotheken herunter (ca. 1,4 GB)..."
        Invoke-WebRequest `
            -Uri "https://github.com/ollama/ollama/releases/download/v0.40.6/ollama-windows-amd64.zip" `
            -OutFile $ollamaArchive
    }
    $ollamaHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ollamaArchive).Hash
    if ($ollamaHash -ne "E359637575302F288D76C0007C408A4BE9C7376D59C4F28684D63B232A44B427") {
        throw "Die SHA-256-Prüfung der Ollama-Laufzeit ist fehlgeschlagen."
    }
    Write-Host "Entpacke Ollama in den Projektordner..."
    New-Item -ItemType Directory -Force $ollamaDirectory | Out-Null
    Expand-Archive -Path $ollamaArchive -DestinationPath $ollamaDirectory -Force
    Remove-Item -LiteralPath $ollamaArchive -Force
}

if (-not (Test-Path (Join-Path $ollamaDirectory "ollama.exe"))) {
    throw "ollama.exe wurde im heruntergeladenen Archiv nicht gefunden."
}

if (-not (Test-Path $modelPath)) {
    Write-Host "Lade Yumenkos Modell herunter (ca. 2,5 GB)..."
    $temporaryModel = "$modelPath.download"
    Invoke-WebRequest `
        -Uri "https://huggingface.co/mradermacher/Qwen3-VL-4B-Instruct-Uncensored-GGUF/resolve/6d93457e019e051d38a6268f9884ece33efdb258/Qwen3-VL-4B-Instruct-Uncensored.Q4_K_M.gguf" `
        -OutFile $temporaryModel
    $model = Get-Item -LiteralPath $temporaryModel
    if ($model.Length -ne 2497282496) {
        Remove-Item -LiteralPath $temporaryModel -Force
        throw "Modell-Download unvollständig: $($model.Length) Bytes statt 2497282496."
    }
    Move-Item -LiteralPath $temporaryModel -Destination $modelPath
}

$expectedHash = "16146EB3978364E89593C2D9F5A0B905F528733B5FA5AFA0BD5E25F4D8AD6848"
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $modelPath).Hash
if ($actualHash -ne $expectedHash) {
    throw "Die SHA-256-Prüfung des Modells ist fehlgeschlagen."
}

$ollamaVersion = & (Join-Path $ollamaDirectory "ollama.exe") --version
if ($LASTEXITCODE -ne 0) {
    throw "Die portable Ollama-Laufzeit konnte nicht ausgeführt werden."
}

Write-Host "Setup vollständig. $ollamaVersion"
