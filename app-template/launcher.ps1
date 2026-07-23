# Entry point for the "Start L10 Manager" shortcut.
# Shows a small status window, makes sure Python still works (the folder may
# have been shared to a machine that's never had it), then launches the app.
# Update checking/applying is owned by the running app itself (see
# updater.py) - not duplicated here, to avoid prompting the user twice.

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

# --- Launch the app ---
Set-Status "Launching L10 Manager..."
$appScript = Join-Path $appDir 'l10_manager.py'
$exe = if ($python.PythonwExe) { $python.PythonwExe } else { $python.PythonExe }
# -B (don't write __pycache__/*.pyc) - this app's install folder is designed
# to live on a Google Drive/OneDrive/Dropbox sync mount, and a bytecode
# cache write racing that sync process is a real, reproducible source of
# stale-module bugs after an update (see l10_manager.py::relaunch()'s
# matching comment for the incident that surfaced this).
Start-Process -FilePath $exe -ArgumentList "-B", "`"$appScript`"" -WorkingDirectory $appDir

Start-Sleep -Milliseconds 400
$splash.Close()
