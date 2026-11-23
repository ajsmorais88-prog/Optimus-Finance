@echo off
rem BLOCO 1 - Resolve a raiz antes de localizar o ambiente virtual.
cd /d "%~dp0..\.."
rem BLOCO 2 - Interrompe a inicializacao quando o Python local nao foi instalado.
if not exist ".venv\Scripts\python.exe" (
    echo Instale as dependencias seguindo o README.md.
    pause
    exit /b 1
)
rem BLOCO 3 - Executa o modulo Python correspondente e preserva as mensagens do terminal.
".venv\Scripts\python.exe" Backend\Python\configurar_banco.py
pause
