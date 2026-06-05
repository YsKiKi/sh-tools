## Windows快捷设置脚本
1. [移动Windows默认文件夹到 `D:\\0.PC\\`](Scripts/RelocateFolders.ps1)  
   
   使用方式：以管理员身份运行PowerShell，执行以下命令：
    ```powershell
    irm https://raw.githubusercontent.com/YsKiKi/sh-tools/main/Scripts/RelocateFolders.ps1 | iex
    ```
   该脚本会将用户的默认文件夹（如文档、图片、视频等）移动到 `D:\\0.PC\\` 目录下，并创建相应的快捷方式。
