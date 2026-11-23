"""Consumidores privados: eventos bancários e consultas periódicas, sem credenciais nas mensagens."""

# Os grupos conservam os nomes anteriores à reorganização das pastas.
from typing import Any
from vercel.queue import Message, subscribe


# BLOCO — Recebe o agendamento e distribui as conexões pelos trabalhos individuais.
@subscribe(
    topic="finance-sync-tick",
    consumer_group="sync_worker.sync_tick",
    max_attempts=3,
    max_concurrency=1,
    retry_after=60,
)
def sync_tick(message: Message[Any]):
    from auto_sync import dispatch_all

    print("auto-sync: private tick received", flush=True)
    dispatch_all()


# BLOCO — Processa apenas o identificador de um trabalho bancário privado.
@subscribe(
    topic="finance-sync",
    consumer_group="sync_worker.sync_provider",
    max_attempts=3,
    max_concurrency=2,
    retry_after=60,
)
def sync_provider(message: Message[Any]):
    from auto_sync import run_job

    print("auto-sync: private bank job received", flush=True)
    run_job(message.payload)
