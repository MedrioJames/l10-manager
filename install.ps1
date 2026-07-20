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
    # ",$bytes" (comma-prefixed) forces PowerShell to return the byte array
    # as-is rather than unrolling it - without this, a zero-length array
    # (an empty file) comes back as $null to the caller, which then crashes
    # WriteAllBytes. A quirk, but a real one - app-template/ui/__init__.py
    # hit it during testing.
    param([string]$RelativePath)
    if ($LocalRoot) {
        $bytes = [System.IO.File]::ReadAllBytes((Join-Path $LocalRoot $RelativePath))
        return , $bytes
    }
    $tmp = [System.IO.Path]::Combine($env:TEMP, [System.IO.Path]::GetRandomFileName())
    Invoke-WebRequest -Uri "$RawBase/$RelativePath" -OutFile $tmp -TimeoutSec 30
    $bytes = [System.IO.File]::ReadAllBytes($tmp)
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    return , $bytes
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
    # install.ps1 is always launched via `-File` under -ExecutionPolicy Bypass
    # (see L10-Manager-Setup.bat / the README one-liner) rather than piped
    # into iex, so the whole process already runs under Bypass - dot-sourcing
    # a downloaded file here works fine and doesn't need an in-memory eval
    # trick. Deliberately avoiding fileless script evaluation (ScriptBlock::
    # Create/iex on downloaded text): it's a heavily-signatured pattern for
    # security tooling, even when the content itself is benign.
    $tmpLib = [System.IO.Path]::Combine($env:TEMP, [System.IO.Path]::GetRandomFileName() + '.ps1')
    Invoke-WebRequest -Uri "$RawBase/app-template/lib/PythonCheck.ps1" -OutFile $tmpLib -TimeoutSec 30
    . $tmpLib
    Remove-Item $tmpLib -Force -ErrorAction SilentlyContinue
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
Write-Host "  Tip: pick a location inside Google Drive, OneDrive, or Dropbox if you" -ForegroundColor DarkGray
Write-Host "  want to be able to share this L10 with a teammate later." -ForegroundColor DarkGray
Write-Host ""

if ($InstallParent -and $MeetingName) {
    # Non-interactive (used for testing) - skip the dialog/prompt below.
    $parentFolder = $InstallParent
    $meetingName = $MeetingName.Trim()
} else {
    # A real folder-only picker via IFileOpenDialog + FOS_PICKFOLDERS - the
    # same modern Explorer-style common dialog Office/VS Code use for "Open
    # Folder", showing Quick Access/OneDrive/Google Drive properly (unlike
    # the legacy FolderBrowserDialog tree view). Unlike a repurposed file
    # dialog, this only shows folders and the button genuinely says "Select
    # Folder" - no confusing file-picking affordances.
    Add-Type -Language CSharp -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

namespace L10Manager {
    [ComImport, Guid("DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7")]
    internal class FileOpenDialogRCW { }

    [ComImport, Guid("d57c7288-d4ad-4768-be02-9d969532d960"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface IFileOpenDialog {
        [PreserveSig] int Show(IntPtr parent);
        void SetFileTypes(uint cFileTypes, IntPtr rgFilterSpec);
        void SetFileTypeIndex(uint iFileType);
        void GetFileTypeIndex(out uint piFileType);
        void Advise(IntPtr pfde, out uint pdwCookie);
        void Unadvise(uint dwCookie);
        void SetOptions(uint fos);
        void GetOptions(out uint pfos);
        void SetDefaultFolder(IShellItem psi);
        void SetFolder(IShellItem psi);
        void GetFolder(out IShellItem ppsi);
        void GetCurrentSelection(out IShellItem ppsi);
        void SetFileName(string pszName);
        void GetFileName(out string pszName);
        void SetTitle(string pszTitle);
        void SetOkButtonLabel(string pszText);
        void SetFileNameLabel(string pszLabel);
        void GetResult(out IShellItem ppsi);
        void AddPlace(IShellItem psi, uint fdap);
        void SetDefaultExtension(string pszDefaultExtension);
        void Close(int hr);
        void SetClientGuid(ref Guid guid);
        void ClearClientData();
        void SetFilter([MarshalAs(UnmanagedType.IUnknown)] object pFilter);
        void GetResults(out IntPtr ppenum);
        void GetSelectedItems(out IntPtr ppsai);
    }

    [ComImport, Guid("43826d1e-e718-42ee-bc55-a1e261c37bfe"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface IShellItem {
        void BindToHandler(IntPtr pbc, ref Guid bhid, ref Guid riid, out IntPtr ppv);
        void GetParent(out IShellItem ppsi);
        void GetDisplayName(int sigdnName, out IntPtr ppszName);
        void GetAttributes(uint sfgaoMask, out uint psfgaoAttribs);
        void Compare(IShellItem psi, uint hint, out int piOrder);
    }

    public static class Win32FolderPicker {
        [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
        private static extern int SHCreateItemFromParsingName(string pszPath, IntPtr pbc, ref Guid riid, out IShellItem ppv);

        private static readonly Guid IID_IShellItem = new Guid("43826d1e-e718-42ee-bc55-a1e261c37bfe");
        private const uint FOS_PICKFOLDERS = 0x20;
        private const uint FOS_FORCEFILESYSTEM = 0x40;
        private const uint FOS_PATHMUSTEXIST = 0x800;
        private const int SIGDN_FILESYSPATH = unchecked((int)0x80058000);

        public static string PickFolder(string title, string initialDirectory) {
            var dialog = (IFileOpenDialog)new FileOpenDialogRCW();
            try {
                dialog.SetOptions(FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST);
                if (!string.IsNullOrEmpty(title)) dialog.SetTitle(title);

                if (!string.IsNullOrEmpty(initialDirectory) && System.IO.Directory.Exists(initialDirectory)) {
                    IShellItem folderItem;
                    Guid iid = IID_IShellItem;
                    if (SHCreateItemFromParsingName(initialDirectory, IntPtr.Zero, ref iid, out folderItem) == 0) {
                        dialog.SetFolder(folderItem);
                    }
                }

                int hr = dialog.Show(IntPtr.Zero);
                if (hr != 0) return null;

                IShellItem result;
                dialog.GetResult(out result);
                IntPtr pathPtr;
                result.GetDisplayName(SIGDN_FILESYSPATH, out pathPtr);
                try {
                    return Marshal.PtrToStringUni(pathPtr);
                } finally {
                    Marshal.FreeCoTaskMem(pathPtr);
                }
            } finally {
                Marshal.ReleaseComObject(dialog);
            }
        }
    }
}
"@

    $initialDir = $null
    try { $initialDir = [Environment]::GetFolderPath('MyDocuments') } catch {}

    Write-Host "  Press Enter to open the folder picker..." -ForegroundColor DarkGray
    Read-Host | Out-Null

    $parentFolder = [L10Manager.Win32FolderPicker]::PickFolder("Choose a location for this L10", $initialDir)
    if (-not $parentFolder) {
        Write-Host ""
        Write-Host "  Setup cancelled - no folder was chosen." -ForegroundColor Red
        exit 1
    }

    $meetingName = Read-Host "  What would you like to name this L10 folder? (e.g. 'Leadership Team')"
    while ([string]::IsNullOrWhiteSpace($meetingName)) {
        $meetingName = Read-Host "  Please enter a name"
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
Write-Host "  This window will close on its own in a moment - the folder that just" -ForegroundColor DarkGray
Write-Host "  opened is all you need." -ForegroundColor DarkGray
Start-Sleep -Seconds 3
