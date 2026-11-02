@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set EMBED_YT=1
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 goto nopython
echo EXPERIMENT MODE: YouTube streams are attached to each episode.
python server.py
pause
exit /b
:nopython
echo Python is not installed. Get it from python.org (tick "Add Python to PATH").
pause
