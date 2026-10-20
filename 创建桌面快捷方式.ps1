# 在桌面创建「桌宠Demo」启动快捷方式
# 优先级：打包好的 exe（不依赖 Python） > pythonw（开发模式）
# 说明：本文件保持纯 ASCII 编码，中文名用 Unicode 码点拼接，避免 PowerShell 5.1 读 UTF-8 产生乱码
$appName = -join ([char]0x684C, [char]0x5BA0, 'Demo')      # 桌宠Demo
$desc    = -join ([char]0x684C, [char]0x5BA0, 'Demo', ' - Desktop Pet')

$proj = Split-Path -Parent $MyInvocation.MyCommand.Definition
$desktop = [Environment]::GetFolderPath('Desktop')

# 清理旧的同名快捷方式（含之前编码异常产生的乱码名）
Get-ChildItem -Path $desktop -Filter '*.lnk' |
    Where-Object { $_.Name -like '*Demo*' } |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }

$exe = Join-Path $proj (Join-Path 'dist' "$appName.exe")
$icon = Join-Path $proj (Join-Path 'assets' 'app.ico')

if (Test-Path -LiteralPath $exe) {
    $target = $exe
    $args = ''
} else {
    $target = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
    if (-not $target) { $target = (Get-Command python).Source }
    $args = 'desktop_pet.py'
}

$ws = New-Object -ComObject WScript.Shell
$shortcut = $ws.CreateShortcut("$desktop\$appName.lnk")
$shortcut.TargetPath = $target
$shortcut.Arguments = $args
$shortcut.WorkingDirectory = Split-Path -Parent $target
$shortcut.IconLocation = $icon
$shortcut.Description = $desc
$shortcut.Save()

Write-Output "Shortcut: $desktop\$appName.lnk"
Write-Output "Target: $target $args"
