# Shared Python detection + guided-install flow.
# Dot-sourced by both install.ps1 (console UI) and launcher.ps1 (WinForms UI) -
# keep this file UI-agnostic; callers supply their own presentation via
# scriptblocks passed to Resolve-Python.

function Test-RealPython {
    param(
        [Parameter(Mandatory)][string]$Command,
        [Parameter(Mandatory)][string[]]$Arguments
    )
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $Command
        $psi.Arguments = ($Arguments -join ' ')
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $proc = [System.Diagnostics.Process]::Start($psi)
        $out = $proc.StandardOutput.ReadToEnd()
        $err = $proc.StandardError.ReadToEnd()
        $proc.WaitForExit(5000) | Out-Null
        return "$out$err" -match 'Python 3\.\d+'
    } catch {
        return $false
    }
}

function Find-Python {
    <#
      Detects a real, working Python 3 install - deliberately avoiding the
      Microsoft Store "python.exe" stub, which exists on PATH by default on
      many Windows installs but just opens the Store when run.

      Returns @{ Launcher; PythonExe; PythonwExe } or $null if none found.
    #>

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py -and (Test-RealPython -Command $py.Source -Arguments @('-3', '--version'))) {
        $pythonExe = (& py -3 -c "import sys; print(sys.executable)" 2>$null)
        $pythonExe = if ($pythonExe) { $pythonExe.Trim() } else { $null }
        $pythonwExe = $null
        if ($pythonExe) {
            $candidate = Join-Path (Split-Path $pythonExe) 'pythonw.exe'
            if (Test-Path $candidate) { $pythonwExe = $candidate }
        }
        return @{ Launcher = 'py'; PythonExe = $pythonExe; PythonwExe = $pythonwExe }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python -and $python.Source -notmatch 'WindowsApps' -and (Test-RealPython -Command $python.Source -Arguments @('--version'))) {
        $pythonwExe = $null
        $candidate = Join-Path (Split-Path $python.Source) 'pythonw.exe'
        if (Test-Path $candidate) { $pythonwExe = $candidate }
        return @{ Launcher = 'python'; PythonExe = $python.Source; PythonwExe = $pythonwExe }
    }

    return $null
}

function Resolve-Python {
    <#
      Ensures a real Python 3 install exists, guiding the user through
      installing it if not. Never installs anything silently - always opens
      the official download page and waits for explicit confirmation.

      -ShowMessage: scriptblock(string) - display an informational message
      -Confirm:     scriptblock(string) -> bool - ask a yes/continue question;
                    return $false to cancel the whole flow

      Returns the Find-Python hashtable, or $null if the user cancels.
    #>
    param(
        [Parameter(Mandatory)][scriptblock]$ShowMessage,
        [Parameter(Mandatory)][scriptblock]$Confirm
    )

    $found = Find-Python
    if ($found) { return $found }

    while ($true) {
        & $ShowMessage "Python 3 wasn't found on this computer. L10 Manager needs it to run.`r`n`r`nOpening the official download page - when installing, check the box that says 'Add python.exe to PATH'."
        Start-Process "https://www.python.org/downloads/"

        $keepGoing = & $Confirm "Once Python is installed, continue?"
        if (-not $keepGoing) { return $null }

        $found = Find-Python
        if ($found) {
            & $ShowMessage "Found it - Python is ready to go."
            return $found
        }
        & $ShowMessage "Still couldn't find a working Python install. Let's try again."
    }
}
