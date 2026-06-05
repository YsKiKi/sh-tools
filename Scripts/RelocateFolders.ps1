#Requires -RunAsAdministrator
<#
.SYNOPSIS
    将 Windows 默认用户文件夹重定向到 D:\0.PC\<子文件夹>

.DESCRIPTION
    支持本地运行，也支持通过以下方式远程执行：
    irm https://your-server/RelocateFolders.ps1 | iex

    或带参数：
    $s = irm https://your-server/RelocateFolders.ps1
    & ([scriptblock]::Create($s)) -BasePath "D:\0.PC" -AutoRestartExplorer -NoConfirm

.PARAMETER BasePath
    目标根目录，默认 D:\0.PC

.PARAMETER NoConfirm
    跳过确认提示，静默执行

.PARAMETER AutoRestartExplorer
    执行完毕后自动重启资源管理器

.PARAMETER Folders
    要迁移的文件夹列表，默认全部（Desktop/Documents/Downloads/Music/Pictures/Videos）

.EXAMPLE
    # 本地运行（全部默认）
    .\RelocateFolders.ps1

    # 静默 + 自动重启资源管理器
    .\RelocateFolders.ps1 -NoConfirm -AutoRestartExplorer

    # 远程一键执行（静默）
    irm https://your-server/RelocateFolders.ps1 | iex

    # 远程执行并传参
    $s = irm https://your-server/RelocateFolders.ps1
    & ([scriptblock]::Create($s)) -BasePath "E:\MyFiles" -NoConfirm -AutoRestartExplorer
#>

[CmdletBinding()]
param(
    [string]   $BasePath             = "D:\0.PC",
    [switch]   $NoConfirm,
    [switch]   $AutoRestartExplorer,
    [string[]] $Folders              = @("Desktop","Documents","Downloads","Music","Pictures","Videos")
)

# ----------------------------------------------------------------
# 颜色输出辅助
# ----------------------------------------------------------------
function Write-Step   { param($msg) Write-Host "  $msg" -ForegroundColor Cyan }
function Write-Ok     { param($msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn   { param($msg) Write-Host "  [警告] $msg" -ForegroundColor Yellow }
function Write-Fail   { param($msg) Write-Host "  [错误] $msg" -ForegroundColor Red }
function Write-Header { param($msg) Write-Host "`n$("="*60)`n  $msg`n$("="*60)" -ForegroundColor White }

# ----------------------------------------------------------------
# 文件夹元数据：Shell 名称、注册表值名、已知文件夹 GUID
# ----------------------------------------------------------------
$FolderMeta = [ordered]@{
    Desktop   = @{
        Label    = "桌面 (Desktop)"
        RegName  = "Desktop"
        OldName  = "Desktop"
        KnownId  = [guid]"B4BFCC3A-DB2C-424C-B029-7FE99A87C641"
    }
    Documents = @{
        Label    = "文档 (Documents)"
        RegName  = "Personal"
        OldName  = "Documents"
        KnownId  = [guid]"FDD39AD0-238F-46AF-ADB4-6C85480369C7"
    }
    Downloads = @{
        Label    = "下载 (Downloads)"
        RegName  = "{374DE290-123F-4565-9164-39C4925E467B}"
        OldName  = "Downloads"
        KnownId  = [guid]"374DE290-123F-4565-9164-39C4925E467B"
    }
    Music     = @{
        Label    = "音乐 (Music)"
        RegName  = "My Music"
        OldName  = "Music"
        KnownId  = [guid]"4BD8D571-6D19-48D3-BE97-422220080E43"
    }
    Pictures  = @{
        Label    = "图片 (Pictures)"
        RegName  = "My Pictures"
        OldName  = "Pictures"
        KnownId  = [guid]"33E28130-4E1E-4676-835A-98395C3BC3BB"
    }
    Videos    = @{
        Label    = "视频 (Videos)"
        RegName  = "My Video"
        OldName  = "Videos"
        KnownId  = [guid]"18989B1D-99B5-455B-841C-AB7C74E4DDFC"
    }
}

# ----------------------------------------------------------------
# 加载 Shell32 SHSetKnownFolderPath
# ----------------------------------------------------------------
$shell32Src = @"
using System;
using System.Runtime.InteropServices;
public class Shell32Helper {
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    public static extern int SHSetKnownFolderPath(
        ref Guid folderId, uint flags, IntPtr token, string path);
}
"@
try {
    if (-not ([System.Management.Automation.PSTypeName]"Shell32Helper").Type) {
        Add-Type -TypeDefinition $shell32Src -ErrorAction Stop
    }
    $shell32Loaded = $true
} catch {
    $shell32Loaded = $false
    Write-Warn "Shell32Helper 加载失败，将仅通过注册表更新路径（需重启生效）"
}

# ----------------------------------------------------------------
# 权限检查
# ----------------------------------------------------------------
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Fail "请以管理员身份运行此脚本！"
    Write-Host "  提示：右键 PowerShell -> 以管理员身份运行" -ForegroundColor Yellow
    exit 1
}

# ----------------------------------------------------------------
# 欢迎信息
# ----------------------------------------------------------------
Write-Header "Windows 默认文件夹迁移工具"
Write-Host "  目标根目录 : $BasePath" -ForegroundColor White
Write-Host "  迁移文件夹 : $($Folders -join ', ')" -ForegroundColor White
Write-Host ""
Write-Host "  [注意] 此脚本只修改路径，不移动已有文件。" -ForegroundColor Yellow
Write-Host "         建议执行后手动将旧文件夹内容复制到新位置。" -ForegroundColor Yellow

# ----------------------------------------------------------------
# 确认
# ----------------------------------------------------------------
if (-not $NoConfirm) {
    Write-Host ""
    $ans = Read-Host "  确认继续？(Y/N)"
    if ($ans -notmatch "^[Yy]$") {
        Write-Host "  已取消。" -ForegroundColor Gray
        exit 0
    }
}

# ----------------------------------------------------------------
# 1. 创建目录
# ----------------------------------------------------------------
Write-Header "第 1 步：创建目录结构"
$regPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"

foreach ($name in $Folders) {
    if (-not $FolderMeta.Contains($name)) {
        Write-Warn "未知文件夹名称: $name，已跳过"
        continue
    }
    $target = Join-Path $BasePath $name
    if (-not (Test-Path $target)) {
        New-Item -ItemType Directory -Path $target -Force | Out-Null
        Write-Ok "已创建: $target"
    } else {
        Write-Step "已存在（跳过）: $target"
    }
}

# ----------------------------------------------------------------
# 2. 更新注册表
# ----------------------------------------------------------------
Write-Header "第 2 步：更新注册表"

foreach ($name in $Folders) {
    if (-not $FolderMeta.Contains($name)) { continue }
    $meta   = $FolderMeta[$name]
    $target = Join-Path $BasePath $name

    try {
        # 写入注册表（名称键）
        Set-ItemProperty -Path $regPath -Name $meta.RegName -Value $target -Type ExpandString -ErrorAction Stop

        # 如果 RegName 不是 GUID 格式，同时写入 GUID 键（兼容旧版）
        $guidKey = "{$($meta.KnownId.ToString().ToUpper())}"
        if ($meta.RegName -ne $guidKey) {
            Set-ItemProperty -Path $regPath -Name $guidKey -Value $target -Type ExpandString -ErrorAction SilentlyContinue
        }
        Write-Ok "$($meta.Label) -> $target"
    } catch {
        Write-Fail "$($meta.Label) 注册表写入失败: $_"
    }
}

# ----------------------------------------------------------------
# 3. 调用 SHSetKnownFolderPath 立即生效
# ----------------------------------------------------------------
Write-Header "第 3 步：通知 Shell 刷新路径"

foreach ($name in $Folders) {
    if (-not $FolderMeta.Contains($name)) { continue }
    $meta   = $FolderMeta[$name]
    $target = Join-Path $BasePath $name
    $guid   = $meta.KnownId

    if ($shell32Loaded) {
        try {
            $hr = [Shell32Helper]::SHSetKnownFolderPath([ref]$guid, 0, [IntPtr]::Zero, $target)
            if ($hr -eq 0) {
                Write-Ok "$($meta.Label) Shell 路径已刷新"
            } else {
                Write-Warn "$($meta.Label) SHSetKnownFolderPath 返回 HRESULT: 0x$('{0:X8}' -f $hr)（注册表已写入，重启后生效）"
            }
        } catch {
            Write-Warn "$($meta.Label) Shell 刷新异常: $_"
        }
    } else {
        Write-Warn "$($meta.Label) Shell32 未加载，跳过实时刷新（重启后生效）"
    }
}

# ----------------------------------------------------------------
# 4. 汇总
# ----------------------------------------------------------------
Write-Header "迁移完成"
Write-Host "  目录结构：" -ForegroundColor White
foreach ($name in $Folders) {
    if ($FolderMeta.Contains($name)) {
        Write-Host "    $BasePath\$name" -ForegroundColor Green
    }
}
Write-Host ""
Write-Host "  后续建议：" -ForegroundColor White
Write-Host "    1. 将 C:\Users\$env:USERNAME\<各文件夹> 中的文件复制到对应新位置" -ForegroundColor Gray
Write-Host "    2. 注销/重新登录使所有应用完全识别新路径" -ForegroundColor Gray
Write-Host ""

# ----------------------------------------------------------------
# 5. 重启资源管理器
# ----------------------------------------------------------------
if ($AutoRestartExplorer) {
    Write-Step "正在重启资源管理器..."
    Stop-Process -Name explorer -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 800
    Start-Process explorer
    Write-Ok "资源管理器已重启"
} else {
    if (-not $NoConfirm) {
        $ans = Read-Host "  是否立即重启资源管理器以使更改生效？(Y/N)"
        if ($ans -match "^[Yy]$") {
            Stop-Process -Name explorer -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 800
            Start-Process explorer
            Write-Ok "资源管理器已重启"
        }
    }
}