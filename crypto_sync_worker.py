"""Consumidor isolado para que as consultas das exchanges não aguardem extratos bancários."""

# Os grupos conservam os nomes anteriores à reorganização das pastas.
from typing import Any
from vercel.queue import Message, subscribe


# BLOCO — Processa as exchanges em fila separada das consultas bancárias.
@subscribe(
    topic="finance-sync-crypto",
    consumer_group="crypto_sync_worker.sync_exchange",
    max_attempts=3,
    max_concurrency=1,
    retry_after=60,
)
def sync_exchange(message: Message[Any]):
    from auto_sync import run_job

    print("auto-sync: private exchange job received", flush=True)
    run_job(message.payload)
