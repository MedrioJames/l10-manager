# L10 Manager - Setup
#
# Builds a new, self-contained L10 Manager folder for one Level 10 Meeting.
# Runs from the copy-paste one-liner (irm .../install.ps1 | iex), from
# L10-Manager-Setup.bat, or directly from a local clone of this repo for
# development/testing - all three are handled below.
#
# -InstallParent / -MeetingName are optional and only exist so this script
# can be tested non-interactively; leave them out for the normal guided
# experience (folder-picker dialog + prompt).

param(
    [string]$InstallParent,
    [string]$MeetingName
)

$ErrorActionPreference = 'Stop'

# --- Repo / mode detection -------------------------------------------------

$RepoOwner = 'MedrioJames'
$RepoName = 'l10-manager'
$Branch = 'main'
$RawBase = "https://raw.githubusercontent.com/$RepoOwner/$RepoName/$Branch"

$LocalRoot = $null
if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'manifest.json'))) {
    $LocalRoot = $PSScriptRoot
}

function Get-RepoBytes {
    param([string]$RelativePath)
    if ($LocalRoot) {
        return [System.IO.File]::ReadAllBytes((Join-Path $LocalRoot $RelativePath))
    }
    $tmp = [System.IO.Path]::Combine($env:TEMP, [System.IO.Path]::GetRandomFileName())
    Invoke-WebRequest -Uri "$RawBase/$RelativePath" -OutFile $tmp -TimeoutSec 30
    $bytes = [System.IO.File]::ReadAllBytes($tmp)
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    return $bytes
}

function Get-Manifest {
    if ($LocalRoot) {
        return Get-Content (Join-Path $LocalRoot 'manifest.json') -Raw | ConvertFrom-Json
    }
    return Invoke-RestMethod -Uri "$RawBase/manifest.json" -TimeoutSec 15
}

# --- Banner ------------------------------------------------------------

Clear-Host
Write-Host ""
Write-Host "  L10 Manager - Setup" -ForegroundColor Cyan
Write-Host "  ----------------------------------------------------" -ForegroundColor DarkCyan
Write-Host ""

$manifest = Get-Manifest
Write-Host "  Version $($manifest.version)" -ForegroundColor DarkGray
Write-Host ""

# --- Step 1: Python -------------------------------------------------------

Write-Host "  Step 1 of 4 - Checking Python" -ForegroundColor Cyan
Write-Host ""

if ($LocalRoot) {
    . (Join-Path $LocalRoot 'app-template\lib\PythonCheck.ps1')
} else {
    # Dot-source from an in-memory script block rather than a downloaded .ps1
    # file - loading a script *file* is subject to the execution policy, but
    # a script block built from text in memory is not (same reason the outer
    # `irm | iex` one-liner itself isn't blocked by the policy).
    $libText = [System.Text.Encoding]::UTF8.GetString((Get-RepoBytes 'app-template/lib/PythonCheck.ps1'))
    . ([ScriptBlock]::Create($libText))
}

$showMessage = {
    param($m)
    Write-Host ""
    Write-Host "  $m" -ForegroundColor Yellow
    Write-Host ""
}
$confirm = {
    param($m)
    (Read-Host "  $m [press Enter to continue, or type 'cancel' to stop]") -ne 'cancel'
}

$python = Resolve-Python -ShowMessage $showMessage -Confirm $confirm
if (-not $python) {
    Write-Host ""
    Write-Host "  Setup cancelled - Python is required to continue." -ForegroundColor Red
    exit 1
}
Write-Host "  Python looks good ($($python.PythonExe))" -ForegroundColor Green
Write-Host ""

# --- Step 2: choose a folder ------------------------------------------

Write-Host "  Step 2 of 4 - Choose where this L10 lives" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Tip: pick a folder inside Google Drive, OneDrive, or Dropbox if you" -ForegroundColor DarkGray
Write-Host "  want to be able to share this L10 with a teammate later." -ForegroundColor DarkGray
Write-Host ""

if ($InstallParent -and $MeetingName) {
    # Non-interactive (used for testing) - skip the dialog/prompt below.
    $parentFolder = $InstallParent
    $meetingName = $MeetingName.Trim()
} else {
    Add-Type -AssemblyName System.Windows.Forms

    $folderDialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $folderDialog.Description = "Choose a location for this L10 (e.g. a folder inside Google Drive, OneDrive, or Dropbox)"
    $folderDialog.ShowNewFolderButton = $true
    try { $folderDialog.SelectedPath = [Environment]::GetFolderPath('MyDocuments') } catch {}

    $dialogResult = $folderDialog.ShowDialog()
    if ($dialogResult -ne [System.Windows.Forms.DialogResult]::OK) {
        Write-Host ""
        Write-Host "  Setup cancelled - no folder was chosen." -ForegroundColor Red
        exit 1
    }
    $parentFolder = $folderDialog.SelectedPath

    $meetingName = Read-Host "  What's this L10 for? (e.g. 'Leadership Team')"
    while ([string]::IsNullOrWhiteSpace($meetingName)) {
        $meetingName = Read-Host "  Please enter a name for this L10"
    }
    $meetingName = $meetingName.Trim()
}

$folderName = if ($meetingName.ToLower().EndsWith('l10')) { $meetingName } else { "$meetingName L10" }
$installDir = Join-Path $parentFolder $folderName

if (Test-Path $installDir) {
    $existingItems = Get-ChildItem -Path $installDir -Force -ErrorAction SilentlyContinue
    if ($existingItems) {
        Write-Host ""
        Write-Host "  '$folderName' already exists and isn't empty." -ForegroundColor Yellow
        $overwrite = Read-Host "  Continue anyway? Files may be overwritten [y/N]"
        if ($overwrite.ToLower() -ne 'y') {
            Write-Host ""
            Write-Host "  Setup cancelled." -ForegroundColor Red
            exit 1
        }
    }
}

Write-Host ""
Write-Host "  This L10 will live at:" -ForegroundColor Cyan
Write-Host "    $installDir" -ForegroundColor White
Write-Host ""

# --- Step 3: build the folder ------------------------------------------

Write-Host "  Step 3 of 4 - Building your L10 folder" -ForegroundColor Cyan
Write-Host ""

$appDir = Join-Path $installDir 'App'
$dataDir = Join-Path $installDir 'Data'
New-Item -ItemType Directory -Path $installDir -Force | Out-Null
New-Item -ItemType Directory -Path $appDir -Force | Out-Null
New-Item -ItemType Directory -Path $dataDir -Force | Out-Null

foreach ($file in $manifest.app_files) {
    Write-Host "    - $($file.dest)" -ForegroundColor DarkGray
    $destPath = Join-Path $appDir $file.dest
    $destDir = Split-Path $destPath -Parent
    if ($destDir -and -not (Test-Path $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }
    $bytes = Get-RepoBytes $file.src
    [System.IO.File]::WriteAllBytes($destPath, $bytes)
}

Set-Content -Path (Join-Path $appDir 'version.txt') -Value $manifest.version -NoNewline

# Render the read-me
$readmeBytes = Get-RepoBytes $manifest.readme_template
$readmeText = [System.Text.Encoding]::UTF8.GetString($readmeBytes)
$readmeText = $readmeText.Replace('{{MEETING_NAME}}', $folderName)
$readmeText = $readmeText.Replace('{{INSTALL_DATE}}', (Get-Date).ToString('MMMM d, yyyy'))
$readmeText = $readmeText.Replace('{{VERSION}}', [string]$manifest.version)
[System.IO.File]::WriteAllText((Join-Path $installDir 'README.html'), $readmeText, [System.Text.Encoding]::UTF8)

# Shortcut with custom icon
$iconPath = Join-Path $appDir 'icon\l10-manager-icon.ico'
$shortcutPath = Join-Path $installDir 'Start L10 Manager.lnk'
$launcherPath = Join-Path $appDir 'launcher.ps1'
$systemPowerShell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'

$wshell = New-Object -ComObject WScript.Shell
$shortcut = $wshell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $systemPowerShell
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$launcherPath`""
$shortcut.WorkingDirectory = $installDir
$shortcut.IconLocation = "$iconPath,0"
$shortcut.Description = "Start L10 Manager for $folderName"
$shortcut.Save()

Write-Host ""
Write-Host "  Folder built." -ForegroundColor Green
Write-Host ""

# --- Step 4: open it up and explain what's next -------------------------

Write-Host "  Step 4 of 4 - All done!" -ForegroundColor Cyan
Write-Host ""

Start-Process explorer.exe $installDir
Start-Process (Join-Path $installDir 'README.html')

Write-Host "  '$folderName' is ready at:" -ForegroundColor White
Write-Host "    $installDir" -ForegroundColor White
Write-Host ""
Write-Host "  What to do next:" -ForegroundColor Cyan
Write-Host "    1. The folder and its read-me just opened for you." -ForegroundColor White
Write-Host "    2. From now on, double-click 'Start L10 Manager' in that folder to open it." -ForegroundColor White
Write-Host "    3. Share the whole folder (e.g. via Google Drive/OneDrive/Dropbox) with" -ForegroundColor White
Write-Host "       anyone who needs to run or cover this L10." -ForegroundColor White
Write-Host ""
Write-Host "  You can close this window now." -ForegroundColor DarkGray
Write-Host ""
