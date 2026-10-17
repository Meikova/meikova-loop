# Creates a Desktop shortcut for MashLoop.exe
$target = Join-Path (Get-Location) "dist\MashLoop\MashLoop.exe"
if (-not (Test-Path $target)) {
    Write-Error "Khong tim thay $target. Vui long chay build truoc."
    exit 1
}

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "MashLoop.lnk"

$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = Split-Path $target
$shortcut.IconLocation = "$target,0"
$shortcut.Description = "MashLoop - Nhac nhay nhip vo tan"
$shortcut.Save()

Write-Host "Da tao shortcut MashLoop tren man hinh Desktop: $shortcutPath"
