@echo off
setlocal
set "CAERNESS_SETUP_OPTION=--choose-ai"
rem One selector and one campaign: choose a free cloud provider in the launch window.
call "%~dp0Play Caerness.cmd" %*
