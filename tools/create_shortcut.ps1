# Creates a Desktop shortcut for Meikova Loop.exe
$target = Join-Path (Get-Location) "dist\MeikovaLoop\MeikovaLoop.exe"
if (-not (Test-Path $target)) {
    Write-Error "Khong tim thay $target. Vui long chay build truoc."
    exit 1
}

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "MeikovaLoop.lnk"

$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = Split-Path $target
$shortcut.IconLocation = "$target,0"
$shortcut.Description = "Meikova Loop - Continuous soundscape engine"
$shortcut.Save()

Write-Host "Da tao shortcut Meikova Loop tren man hinh Desktop: $shortcutPath"
