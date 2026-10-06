"""
Ranking de atendentes - Digisac API
------------------------------------
Métricas: Tempo Médio de Atendimento, Primeira Resposta ao Cliente,

Rodar:
    pip install streamlit requests pandas
    streamlit run ranking_atendentes.py

Modo debug (valida os campos crus da API antes de confiar nas médias):
    Marca a caixinha "🔍 Modo debug" na sidebar antes de gerar o ranking.
    Isso imprime o JSON bruto da 1ª chamada de /tickets e /answers/overview
    pra você conferir se os campos metrics.ticketTime, metrics.waitingTime
    e os buckets de realmente vêm com esses nomes.
"""
import os
import time

import json
from datetime import datetime, timedelta

import pandas as pd
import requests
import streamlit as st

BASE_URL = os.getenv("DIGISAC_BASE_URL", "https://SEU-SUBDOMINIO.digisac.biz")
TOKEN = os.getenv("DIGISAC_TOKEN", "")


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def get_com_retry(url, params=None, headers=None, tentativas=5, espera_inicial=2):
    """
    GET com retry pra 403/429 (rate limit da API do Digisac). Espera
    dobrando a cada tentativa (2s, 4s, 8s, 16s, 32s) antes de desistir.
    """
    espera = espera_inicial
    ultima_resposta = None
    for tentativa in range(tentativas):
        r = requests.get(url, params=params, headers=headers, timeout=30)
        if r.status_code not in (403, 429):
            return r
        ultima_resposta = r
        if tentativa < tentativas - 1:
            time.sleep(espera)
            espera *= 2
    return ultima_resposta


# ---------------------------------------------------------------------------
# USUÁRIOS (paginado)
# ---------------------------------------------------------------------------
def get_active_users(token: str) -> list[dict]:
    users, page = [], 1
    while True:
        r = get_com_retry(
            f"{BASE_URL}/api/v1/users",
            params={"perPage": 50, "page": page},
            headers=auth_headers(token),
        )
        r.raise_for_status()
        payload = r.json()
        users.extend(payload["data"])
        if page >= payload["lastPage"]:
            break
        page += 1
    return [u for u in users if u.get("archivedAt") is None]


# ---------------------------------------------------------------------------
# TICKETS FECHADOS DE UM USUÁRIO NO PERÍODO -> métricas médias
# (aba "Histórico de chamados" do Postman: /api/v1/tickets)
# ---------------------------------------------------------------------------
CAMPO_TEMPO_ATENDIMENTO = "ticketTime"
CAMPO_PRIMEIRA_RESPOSTA = "waitingTime"


def get_user_ticket_metrics(token: str, user_id: str, start_iso: str, end_iso: str) -> dict:
    ticket_times, waiting_times = [], []
    page = 1
    while True:
        query = {
            "where": {
                "userId": user_id,
                "isOpen": False,
                "endedAt": {"$gte": start_iso, "$lte": end_iso},
            },
            "attributes": ["id", "metrics"],
            "perPage": 100,
            "page": page,
        }
        r = get_com_retry(
            f"{BASE_URL}/api/v1/tickets",
            params={"query": json.dumps(query)},
            headers=auth_headers(token),
        )
        r.raise_for_status()
        payload = r.json()
        for t in payload["data"]:
            m = t.get("metrics") or {}
            if m.get(CAMPO_TEMPO_ATENDIMENTO) is not None:
                ticket_times.append(m[CAMPO_TEMPO_ATENDIMENTO])
            if m.get(CAMPO_PRIMEIRA_RESPOSTA) is not None:
                waiting_times.append(m[CAMPO_PRIMEIRA_RESPOSTA])
        if page >= payload.get("lastPage", 1):
            break
        page += 1

    avg_ticket_time = sum(ticket_times) / len(ticket_times) if ticket_times else None
    avg_waiting_time = sum(waiting_times) / len(waiting_times) if waiting_times else None
    return {
        "tempo_medio_atendimento_seg": avg_ticket_time,
        "primeira_resposta_seg": avg_waiting_time,
        "qtd_chamados_fechados": len(ticket_times),
        "qtd_com_primeira_resposta": len(waiting_times),
    }



# ---------------------------------------------------------------------------
# CSAT DO COLABORADOR (campos já vêm nomeados pela API)
# ---------------------------------------------------------------------------
def get_user_csat(token: str, user_id: str, from_iso: str, to_iso: str) -> dict:
    r = get_com_retry(
        f"{BASE_URL}/api/v1/answers/overview",
        params={"userId": user_id, "from": from_iso, "to": to_iso, "type": "csat"},
        headers=auth_headers(token),
    )
    r.raise_for_status()
    payload = r.json()
    total = payload.get("total", {}).get("csat", 0)
    c = payload.get("data", {}).get("csat", {})

    fully_sat = c.get("fullySatisfied", 0)
    sat = c.get("satisfied", 0)
    neutral = c.get("neutral", 0)
    unsat = c.get("unsatisfied", 0)
    fully_unsat = c.get("fullyUnsatisfied", 0)
    invalid = c.get("invalid", 0)

    csat_pct = ((fully_sat + sat) / total * 100) if total else None

    ai_total = payload.get("total", {}).get("aiCsat", 0)
    ai = payload.get("data", {}).get("aiCsat", {})
    ai_fully_sat = ai.get("fullySatisfied", 0)
    ai_sat = ai.get("satisfied", 0)
    ai_neutral = ai.get("neutral", 0)
    ai_unsat = ai.get("unsatisfied", 0)
    ai_fully_unsat = ai.get("fullyUnsatisfied", 0)
    ai_invalid = ai.get("invalid", 0)
    ai_csat_pct = ((ai_fully_sat + ai_sat) / ai_total * 100) if ai_total else None

    return {
        "csat_total_respostas": total,
        "csat_percentual": csat_pct,
        "csat_totalmente_satisfeitos": fully_sat,
        "csat_satisfeitos": sat,
        "csat_neutros": neutral,
        "csat_insatisfeitos": unsat,
        "csat_totalmente_insatisfeitos": fully_unsat,
        "csat_invalidos": invalid,
        "ai_csat_total_respostas": ai_total,
        "ai_csat_percentual": ai_csat_pct,
        "ai_csat_totalmente_satisfeitos": ai_fully_sat,
        "ai_csat_satisfeitos": ai_sat,
        "ai_csat_neutros": ai_neutral,
        "ai_csat_insatisfeitos": ai_unsat,
        "ai_csat_totalmente_insatisfeitos": ai_fully_unsat,
        "ai_csat_invalidos": ai_invalid,
    }


