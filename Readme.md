# 🛠️ sh-tools

Windows / Shell 快捷设置脚本集合，支持通过 `irm | iex` 远程一键执行。

---

## 使用须知

- 所有脚本均需以 **管理员身份** 运行 PowerShell
- 执行前建议阅读脚本说明，了解其操作内容
- 脚本只修改系统配置，**不会自动移动已有文件**

---

## 📦 脚本列表

### 1. 移动 Windows 默认文件夹到 `D:\0.PC\`

> 脚本路径：[`Scripts/RelocateFolders.ps1`](Scripts/RelocateFolders.ps1)  
> 可用于解决 Windows 默认文件夹占用C盘空间的问题  
> 建议在新系统安装后或清理系统盘后执行，避免数据迁移问题

将以下用户默认文件夹重定向到 `D:\0.PC\` 下对应子目录：

| 文件夹 | 原路径 | 新路径 |
|--------|--------|--------|
| 桌面 | `C:\Users\<用户名>\Desktop` | `D:\0.PC\Desktop` |
| 文档 | `C:\Users\<用户名>\Documents` | `D:\0.PC\Documents` |
| 下载 | `C:\Users\<用户名>\Downloads` | `D:\0.PC\Downloads` |
| 音乐 | `C:\Users\<用户名>\Music` | `D:\0.PC\Music` |
| 图片 | `C:\Users\<用户名>\Pictures` | `D:\0.PC\Pictures` |
| 视频 | `C:\Users\<用户名>\Videos` | `D:\0.PC\Videos` |

**快速执行（交互模式）：**

```powershell
irm https://raw.githubusercontent.com/YsKiKi/sh-tools/main/Scripts/RelocateFolders.ps1 | iex
```

**静默执行（自动确认 + 重启资源管理器）：**

```powershell
$s = irm https://raw.githubusercontent.com/YsKiKi/sh-tools/main/Scripts/RelocateFolders.ps1
& ([scriptblock]::Create($s)) -NoConfirm -AutoRestartExplorer
```

**可用参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `-BasePath` | `D:\0.PC` | 自定义目标根目录 |
| `-Folders` | 全部 6 个 | 指定要迁移的文件夹，如 `Desktop,Downloads` |
| `-NoConfirm` | 否 | 跳过确认提示 |
| `-AutoRestartExplorer` | 否 | 完成后自动重启资源管理器 |

> ⚠️ 脚本仅修改注册表路径，不会自动迁移原有文件。执行后请手动将原文件夹内容复制到 `D:\0.PC\` 对应目录。

---

## 📁 仓库结构

```
sh-tools/
└── Scripts/
    └── RelocateFolders.ps1   # 默认文件夹迁移
```

---

## License

[MIT](LICENSE)