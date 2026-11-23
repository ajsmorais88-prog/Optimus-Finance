@echo off
rem Executa a aplicacao a partir da pasta correta, mesmo com duplo clique.
rem BLOCO 1 - Resolve a raiz antes de localizar o ambiente virtual.
cd /d "%~dp0..\.."
rem BLOCO 2 - Interrompe a inicializacao quando o Python local nao foi instalado.
if not exist ".venv\Scripts\python.exe" (
    echo Crie o ambiente virtual seguindo o README.md antes de iniciar.
    pause
    exit /b 1
)
echo O navegador sera aberto quando o painel estiver pronto.
echo Mantenha esta janela aberta enquanto estiver usando o painel.
rem BLOCO 3 - Executa o modulo Python correspondente e preserva as mensagens do terminal.
".venv\Scripts\python.exe" Backend\Python\iniciar.py
pause
