@echo off
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  set "PY=py -3"
) else (
  set "PY=python"
)
%PY% --version
if errorlevel 1 goto missing
%PY% -c "import PIL; import tkinter" >nul 2>nul
if errorlevel 1 (
  %PY% -m pip install "Pillow>=10"
  if errorlevel 1 goto failed
)
%PY% bootlogo_editor.py
if errorlevel 1 goto failed
exit /b 0
:missing
echo Instale Python 3 em https://www.python.org/downloads/ e tente novamente.
pause
exit /b 1
:failed
echo Nao foi possivel iniciar o editor. Confira a mensagem acima.
pause
exit /b 1
