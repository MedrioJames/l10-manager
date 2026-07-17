# Entry point for the "Start L10 Manager" shortcut.
# Shows a small status window, makes sure Python still works (the folder may
# have been shared to a machine that's never had it), offers an update if one
# is available, then launches the app.

$ErrorActionPreference = 'Stop'
$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $appDir 'lib\PythonCheck.ps1')

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$splash = New-Object System.Windows.Forms.Form
$splash.Text = "L10 Manager"
$splash.Size = New-Object System.Drawing.Size(360, 110)
$splash.StartPosition = "CenterScreen"
$splash.FormBorderStyle = "FixedDialog"
$splash.ControlBox = $false
$splash.TopMost = $true

$label = New-Object System.Windows.Forms.Label
$label.Text = "Starting L10 Manager..."
$label.AutoSize = $false
$label.TextAlign = [System.Drawing.ContentAlignment]::MiddleCenter
$label.Dock = "Fill"
$label.Font = New-Object System.Drawing.Font("Segoe UI", 11)
$splash.Controls.Add($label)

$splash.Show()
$splash.Refresh()

function Set-Status {
    param([string]$Text)
    $label.Text = $Text
    $splash.Refresh()
    [System.Windows.Forms.Application]::DoEvents()
}

function Show-Message {
    param([string]$Message)
    [System.Windows.Forms.MessageBox]::Show(
        $splash, $Message, "L10 Manager",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information) | Out-Null
}

function Confirm-Prompt {
    param([string]$Message)
    $result = [System.Windows.Forms.MessageBox]::Show(
        $splash, $Message, "L10 Manager",
        [System.Windows.Forms.MessageBoxButtons]::OKCancel,
        [System.Windows.Forms.MessageBoxIcon]::Question)
    return $result -eq [System.Windows.Forms.DialogResult]::OK
}

# --- Python check (still needed even on a re-shared copy) ---
Set-Status "Checking Python..."
$python = Resolve-Python -ShowMessage ${function:Show-Message} -Confirm ${function:Confirm-Prompt}

if (-not $python) {
    Set-Status "Cancelled."
    Show-Message "L10 Manager can't run without Python. Closing for now."
    $splash.Close()
    exit 1
}

# --- Update check: best-effort, never blocks launch ---
Set-Status "Checking for updates..."
try {
    $manifestUrl = "https://raw.githubusercontent.com/MedrioJames/l10-manager/main/manifest.json"
    $manifest = Invoke-RestMethod -Uri $manifestUrl -TimeoutSec 5

    $versionFile = Join-Path $appDir 'version.txt'
    $localVersion = if (Test-Path $versionFile) { (Get-Content $versionFile -Raw).Trim() } else { "0.0.0" }

    if ($manifest.version -and ($manifest.version -ne $localVersion)) {
        $wantsUpdate = Confirm-Prompt "A newer version of L10 Manager is available (v$($manifest.version) - you have v$localVersion).`r`n`r`nUpdate now?"
        if ($wantsUpdate) {
            Set-Status "Updating..."
            foreach ($file in $manifest.app_files) {
                $rawUrl = "https://raw.githubusercontent.com/$($manifest.repo)/$($manifest.branch)/$($file.src)"
                $destPath = Join-Path $appDir $file.dest
                $destDir = Split-Path $destPath -Parent
                if ($destDir -and -not (Test-Path $destDir)) {
                    New-Item -ItemType Directory -Path $destDir -Force | Out-Null
                }
                Invoke-WebRequest -Uri $rawUrl -OutFile $destPath -TimeoutSec 15
            }
            Set-Content -Path $versionFile -Value $manifest.version -NoNewline
            Set-Status "Updated to v$($manifest.version)."
        }
    }
} catch {
    # Offline or GitHub unreachable - not fatal, just skip the update check.
}

# --- Launch the app ---
Set-Status "Launching L10 Manager..."
$appScript = Join-Path $appDir 'l10_manager.py'
$exe = if ($python.PythonwExe) { $python.PythonwExe } else { $python.PythonExe }
Start-Process -FilePath $exe -ArgumentList "`"$appScript`"" -WorkingDirectory $appDir

Start-Sleep -Milliseconds 400
$splash.Close()
