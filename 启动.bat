@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "main.py" (
    echo.
    echo [错误] 当前目录未找到 main.py
    echo.
    echo 请进入完整的项目根目录后再运行（应与 requirements.txt 同级）。
    echo 若尚未获取源码，请克隆或解压仓库：
    echo   https://github.com/charoumiaoth2759-alt/zhigui
    echo.
    pause
    exit /b 1
)

python main.py
if errorlevel 1 pause
