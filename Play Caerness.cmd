@echo off
setlocal
cd /d "%~dp0"
echo.
echo  CAERNESS - A life in a living world
echo.
if exist ".venv\Scripts\python.exe" goto dependencies
py -3 -c "import sys; assert sys.version_info >= (3,12)" >nul 2>nul
if errorlevel 1 goto no_python
echo Creating the local game environment...
py -3 -m venv .venv
if errorlevel 1 goto setup_failed
:dependencies
".venv\Scripts\python.exe" -c "import numpy" >nul 2>nul
if not errorlevel 1 goto launch
".venv\Scripts\python.exe" -m pip install -r requirements-play.txt
if errorlevel 1 goto setup_failed
:launch
if not defined CAERNESS_SETUP_OPTION set "CAERNESS_SETUP_OPTION=--choose-ai"
echo Keep this window open while you play. Close it to stop the game.
echo Your campaign is saved separately from the starting world.
echo.
".venv\Scripts\python.exe" tools\narrative_play.py %CAERNESS_SETUP_OPTION% --open-browser %*
if errorlevel 1 goto setup_failed
exit /b 0
:no_python
echo Install Python 3.12 or later from https://www.python.org/downloads/windows/
echo Include the Python launcher when installing, then double-click this file again.
pause
exit /b 1
:setup_failed
echo.
echo The game could not start. Read the message above for the missing requirement.
echo Your campaign remains in game\narrative-session.db. Local AI needs no key; optional free cloud AI needs a free developer key.
pause
exit /b 1
