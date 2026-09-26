# 🛠️ sh-tools

Windows / Shell 快捷设置脚本集合，支持通过 `irm | iex` 与 `curl | sh` 远程一键执行。

---

## 使用须知

- PowerShell 脚本均需以 **管理员身份** 运行
- Shell 脚本（如 `sysinfo.sh`）为只读采集，普通用户即可执行
- 执行前建议阅读脚本说明，了解其操作内容
- PowerShell 脚本只修改系统配置，**不会自动移动已有文件**

---

## 📦 脚本列表

### 1. 移动 Windows 默认文件夹到 `D:\0.PC\`

> 脚本路径：[`Scripts/RelocateFolders.ps1`](Scripts/RelocateFolders.ps1)  
> 可用于解决 Windows 默认文件夹占用C盘空间的问题  
> 建议在新系统安装后或清理系统盘后执行，避免数据迁移问题

<details>
<summary>文件夹对照表</summary>

将以下用户默认文件夹重定向到 `D:\0.PC\` 下对应子目录：

| 文件夹 | 原路径 | 新路径 |
|--------|--------|--------|
| 桌面 | `C:\Users\<用户名>\Desktop` | `D:\0.PC\Desktop` |
| 文档 | `C:\Users\<用户名>\Documents` | `D:\0.PC\Documents` |
| 下载 | `C:\Users\<用户名>\Downloads` | `D:\0.PC\Downloads` |
| 音乐 | `C:\Users\<用户名>\Music` | `D:\0.PC\Music` |
| 图片 | `C:\Users\<用户名>\Pictures` | `D:\0.PC\Pictures` |
| 视频 | `C:\Users\<用户名>\Videos` | `D:\0.PC\Videos` |

</details>

**快速执行（交互模式）：**

```powershell
irm https://raw.githubusercontent.com/YsKiKi/sh-tools/main/Scripts/RelocateFolders.ps1 | iex
```

**静默执行（自动确认 + 重启资源管理器）：**

```powershell
$s = irm https://raw.githubusercontent.com/YsKiKi/sh-tools/main/Scripts/RelocateFolders.ps1
& ([scriptblock]::Create($s)) -NoConfirm -AutoRestartExplorer
```

<details>
<summary>可用参数</summary>

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `-BasePath` | `D:\0.PC` | 自定义目标根目录 |
| `-Folders` | 全部 6 个 | 指定要迁移的文件夹，如 `Desktop,Downloads` |
| `-NoConfirm` | 否 | 跳过确认提示 |
| `-AutoRestartExplorer` | 否 | 完成后自动重启资源管理器 |

</details>

> ⚠️ 脚本仅修改注册表路径，不会自动迁移原有文件。执行后请手动将原文件夹内容复制到 `D:\0.PC\` 对应目录。

---

### 2. 系统体检报告（只读）

> 脚本路径：[`Scripts/sysinfo.sh`](Scripts/sysinfo.sh)  
> 只读采集，不改动被检查的机器，适合例行巡检，或排查问题前先看一份全貌  
> 需要目标机器有 `sh` 与 `curl`（主流 Linux 发行版自带）

**快速执行（管道直接跑，不在本地留文件）：**

```bash
curl -fsSL https://raw.githubusercontent.com/YsKiKi/sh-tools/main/Scripts/sysinfo.sh | sh
```

**带参数执行（例如只看磁盘与内存）：**

```bash
curl -fsSL https://raw.githubusercontent.com/YsKiKi/sh-tools/main/Scripts/sysinfo.sh | sh -s -- --only disk,mem
```

**下载后先校验再执行：**

```bash
curl -fsSLO https://raw.githubusercontent.com/YsKiKi/sh-tools/main/Scripts/sysinfo.sh
curl -fsSLO https://raw.githubusercontent.com/YsKiKi/sh-tools/main/Scripts/sysinfo.sh.sha256
sha256sum -c sysinfo.sh.sha256 && sh sysinfo.sh
```

<details>
<summary>可用参数与段落名</summary>

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `-b`, `--brief` | 否 | 精简模式：跳过硬件/安全段，列表只留 5 行 |
| `-w`, `--warn-only` | 否 | 只输出结尾的告警汇总，**有告警时退出码为 1**，便于 cron 判断 |
| `--only LIST` | 全部段落 | 只跑指定段落，逗号分隔，如 `disk,mem` |
| `--skip LIST` | 无 | 跳过指定段落，逗号分隔 |
| `--top N` | `10` | 每个排行显示 N 行 |
| `-o`, `--output FILE` | 无 | 报告写入文件（同时关闭颜色） |
| `--no-color` | 否 | 关闭颜色（管道输出时本来就是关的） |
| `-V`, `--version` | — | 版本号 |
| `-h`, `--help` | — | 本帮助 |

段落名（供 `--only` / `--skip` 使用）：`overview` `cpu` `mem` `disk` `net` `proc` `systemd` `containers` `sessions` `hardware` `security`

</details>

> ⚠️ 脚本全程只读，不改动任何系统配置；唯一的写操作是 `-o`，把报告写到指定路径。

---

## 📁 仓库结构

```
sh-tools/
└── Scripts/
    ├── RelocateFolders.ps1     # 默认文件夹迁移
    ├── sysinfo.sh              # 系统体检报告（只读）
    └── sysinfo.sh.sha256       # sysinfo.sh 的 SHA-256 校验和
```

---

## License

[MIT](LICENSE)
