"""Inicia o painel e abre o navegador apenas depois de receber resposta HTTP."""

import os
import threading
import time
import urllib.request
import webbrowser

from app import app

# BLOCO 1 — Usa a mesma configuração de porta do backend.
port = int(os.getenv("PORT", "5050"))
url = f"http://127.0.0.1:{port}/"


# BLOCO 2 — Aguarda o servidor, sem encaminhar localhost para um proxy.
def open_when_ready():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(40):
        try:
            with opener.open(url, timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except OSError:
            time.sleep(0.25)
    print(f"Nao foi possivel abrir automaticamente. Acesse {url}")


# BLOCO 3 — O terminal mantém o servidor ativo até Ctrl+C.
if __name__ == "__main__":
    print(f"Painel: {url}")
    print("Mantenha esta janela aberta. Para encerrar, pressione Ctrl+C.")
    threading.Thread(target=open_when_ready, daemon=True).start()
    app.run(host="127.0.0.1", port=port, debug=False)
