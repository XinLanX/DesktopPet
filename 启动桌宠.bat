@echo off
title 桌宠Demo
rem 精灵少女桌宠启动器（双击运行，使用 pythonw 不显示控制台）
cd /d "%~dp0"
rem 优先用 pythonw（无控制台窗口），找不到时退回 py -3w，都没有才用 python
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw desktop_pet.py
    exit /b
)
where py >nul 2>nul
if %errorlevel%==0 (
    start "" py -3w desktop_pet.py
    exit /b
)
start "" python desktop_pet.py
