# MetaClean Windows bootstrapper
# Usage:
# irm https://raw.githubusercontent.com/0xb0rn3/MetaClean/main/install.ps1 | iex

$ErrorActionPreference = "Stop"
$RepoZip = "https://github.com/0xb0rn3/MetaClean/archive/refs/heads/main.zip"
$InstallDir = Join-Path $env:LOCALAPPDATA "MetaClean"
$BinDir = Join-Path $HOME "bin"
$TempDir = Join-Path $env:TEMP ("MetaClean-Setup-" + [guid]::NewGuid().ToString("N"))
$Packages = @(
    "Python.Python.3.12",
    "Gyan.FFmpeg",
    "OliverBetz.ExifTool",
    "QPDF.QPDF"
)

function Write-Step([string]$Message) {
    Write-Host ([Environment]::NewLine + "[MetaClean] " + $Message) -ForegroundColor Cyan
}
function Refresh-Path {
    $MachinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$MachinePath;$UserPath"
}

try {
    Write-Step "Checking Windows Package Manager"
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "winget is required. Install Microsoft's App Installer from the Microsoft Store, then rerun this command."
    }

    Write-Step "Installing Python, FFmpeg, ExifTool and qpdf"
    foreach ($Package in $Packages) {
        Write-Host "Installing $Package ..."
        & winget install --exact --id $Package --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "winget returned exit code $LASTEXITCODE for $Package. The tool may already be installed; it will be checked below."
        }
    }
    Refresh-Path

    $Py = Get-Command py -ErrorAction SilentlyContinue
    if ($Py) {
        & py -3.12 --version
        if ($LASTEXITCODE -ne 0) { throw "Python 3.12 was not found after installation." }
    } else {
        $Python = Get-Command python -ErrorAction SilentlyContinue
        if (-not $Python) { throw "Python was not found. Rerun the installer after Python setup completes." }
    }

    Write-Step "Downloading MetaClean"
    New-Item -ItemType Directory -Force -Path $TempDir | Out-Null
    $ZipPath = Join-Path $TempDir "MetaClean-main.zip"
    Invoke-WebRequest -Uri $RepoZip -OutFile $ZipPath -UseBasicParsing
    Expand-Archive -Path $ZipPath -DestinationPath $TempDir -Force
    $SourceDir = Join-Path $TempDir "MetaClean-main\metaclean"
    if (-not (Test-Path (Join-Path $SourceDir "app.py"))) {
        throw "The downloaded repository did not contain metaclean/app.py."
    }

    Write-Step "Installing the application and Python environment"
    if (Test-Path $InstallDir) { Remove-Item -Recurse -Force $InstallDir }
    New-Item -ItemType Directory -Force -Path $InstallDir, (Join-Path $HOME "MetaClean\Files"), $BinDir | Out-Null
    Copy-Item -Path (Join-Path $SourceDir "*") -Destination $InstallDir -Recurse -Force

    $VenvPython = Join-Path $InstallDir ".venv\Scripts\python.exe"
    if ($Py) {
        & py -3.12 -m venv (Join-Path $InstallDir ".venv")
    } else {
        & python -m venv (Join-Path $InstallDir ".venv")
    }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPython)) {
        throw "Could not create MetaClean's Python virtual environment."
    }
    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Could not upgrade pip." }
    & $VenvPython -m pip install -r (Join-Path $InstallDir "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "Could not install MetaClean's Python dependencies." }

    Write-Step "Creating the metaclean command"
    $Launcher = Join-Path $BinDir "metaclean.cmd"
    $NewLine = [Environment]::NewLine
    $Quote = [char]34
    $AppFile = Join-Path $InstallDir "app.py"
    $LauncherText = "@echo off" + $NewLine + "cd /d " + $Quote + $InstallDir + $Quote + $NewLine + $Quote + $VenvPython + $Quote + " " + $Quote + $AppFile + $Quote + " %*" + $NewLine
    Set-Content -Path $Launcher -Value $LauncherText -Encoding ASCII

    $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $PathParts = @()
    if ($UserPath) { $PathParts = $UserPath -split ";" }
    if ($PathParts -notcontains $BinDir) {
        $NewUserPath = (@($PathParts | Where-Object { $_ }) + $BinDir) -join ";"
        [Environment]::SetEnvironmentVariable("Path", $NewUserPath, "User")
    }
    if (($env:Path -split ";") -notcontains $BinDir) { $env:Path = "$env:Path;$BinDir" }

    Write-Step "Checking installed native tools"
    foreach ($Tool in @("exiftool", "ffmpeg", "qpdf")) {
        if (Get-Command $Tool -ErrorAction SilentlyContinue) {
            Write-Host "  $Tool : available" -ForegroundColor Green
        } else {
            Write-Warning "  $Tool is not currently in PATH. Restart PowerShell after winget finishes, or add its install folder to PATH."
        }
    }

    Write-Host ([Environment]::NewLine + "MetaClean is installed.") -ForegroundColor Green
    Write-Host "Open a NEW PowerShell window, then run: metaclean" -ForegroundColor Green
    Write-Host "Dashboard: http://127.0.0.1:5000"
    Write-Host "Default file root: $HOME\MetaClean\Files"
    Write-Host "For shared-network processing, open Cleaning options > Host for devices on your local network."
}
finally {
    if (Test-Path $TempDir) { Remove-Item -Recurse -Force $TempDir -ErrorAction SilentlyContinue }
}
