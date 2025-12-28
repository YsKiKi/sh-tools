@echo off
echo 正在打包 A+1-Tool...

pyinstaller --windowed --onefile --icon=icon.ico --name="A+1-Tool" gui.py

echo.
if errorlevel 1 (
    echo 打包失败！
    pause
) else (
    echo 打包完成！
    pause
)