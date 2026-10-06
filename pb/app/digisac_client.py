"""
Cliente Digisac API - VERSÃO REAL
"""
import time
import json

import requests


class DigisacError(Exception):
    """Erro ao falar com a API do Digisac."""


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def get_com_retry(url, params=None, headers=None, tentativas=5, espera_inicial=2):
    espera = espera_inicial
    ultima_resposta = None
    ultimo_erro = None
    for tentativa in range(tentativas):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=30)
        except requests.exceptions.RequestException as exc:
            # Falha de rede/timeout/DNS etc. Guarda o erro e tenta de novo.
            ultimo_erro = exc
            if tentativa < tentativas - 1:
                time.sleep(espera)
                espera *= 2
            continue

        if r.status_code not in (403, 429):
            return r
        ultima_resposta = r
        if tentativa < tentativas - 1:
            time.sleep(espera)
            espera *= 2

    if ultima_resposta is not None:
        return ultima_resposta
    # Todas as tentativas falharam por erro de rede (nunca chegou a ter resposta HTTP)
    raise DigisacError(f"Falha de conexão com o Digisac após {tentativas} tentativas: {ultimo_erro}")


def get_active_users(base_url: str, token: str) -> list[dict]:
    users, page = [], 1
    while True:
        r = get_com_retry(
            f"{base_url}/api/v1/users",
            params={"perPage": 50, "page": page},
            headers=auth_headers(token),
        )
        try:
            r.raise_for_status()
            payload = r.json()
        except requests.exceptions.HTTPError as exc:
            raise DigisacError(f"Erro HTTP {r.status_code} ao buscar usuários: {r.text[:300]}") from exc

        users.extend(payload["data"])
        if page >= payload["lastPage"]:
            break
        page += 1
    return [u for u in users if u.get("archivedAt") is None]


def get_user_ticket_metrics(base_url: str, token: str, user_id: str, start_iso: str, end_iso: str) -> dict:
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
            f"{base_url}/api/v1/tickets",
            params={"query": json.dumps(query)},
            headers=auth_headers(token),
        )
        try:
            r.raise_for_status()
            payload = r.json()
        except requests.exceptions.HTTPError as exc:
            raise DigisacError(f"Erro HTTP {r.status_code} ao buscar tickets: {r.text[:300]}") from exc

        for t in payload["data"]:
            m = t.get("metrics") or {}
            if m.get("ticketTime") is not None:
                ticket_times.append(m["ticketTime"])
            if m.get("waitingTime") is not None:
                waiting_times.append(m["waitingTime"])
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


def get_user_csat(base_url: str, token: str, user_id: str, from_iso: str, to_iso: str) -> dict:
    r = get_com_retry(
        f"{base_url}/api/v1/answers/overview",
        params={"userId": user_id, "from": from_iso, "to": to_iso, "type": "csat"},
        headers=auth_headers(token),
    )
    try:
        r.raise_for_status()
        payload = r.json()
    except requests.exceptions.HTTPError as exc:
        raise DigisacError(f"Erro HTTP {r.status_code} ao buscar CSAT: {r.text[:300]}") from exc

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
    """
Tela "Agora" do Digisac: departamentos e atendentes em tempo real.

COMO USAR: cole este conteúdo no FINAL do arquivo do cliente Digisac.
Ele reaproveita get_com_retry, auth_headers e DigisacError, que já existem lá.
"""


# Os três endpoints da tela Agora, conforme a coleção do Postman:
#   /api/v1/now/departments-resume  -> visão por departamento
#   /api/v1/now/attendance-resume   -> visão por atendente
#   /api/v1/now/resume              -> tudo junto
RECURSOS_AGORA = ("departments-resume", "attendance-resume", "resume")


def get_json(base_url: str, token: str, caminho: str, params=None):
    """Faz o GET com retry, valida o status e devolve o JSON já convertido."""
    r = get_com_retry(f"{base_url}{caminho}", params=params, headers=auth_headers(token))
    try:
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError as exc:
        raise DigisacError(f"Erro HTTP {r.status_code} em {caminho}: {r.text[:300]}") from exc
    except ValueError as exc:
        raise DigisacError(f"A resposta de {caminho} não veio em JSON") from exc


def buscar_agora(base_url: str, token: str, recurso: str):
    """recurso: 'departments-resume', 'attendance-resume' ou 'resume'."""
    if recurso not in RECURSOS_AGORA:
        raise ValueError(f"Recurso inválido: {recurso}. Use um de {RECURSOS_AGORA}")
    return get_json(base_url, token, f"/api/v1/now/{recurso}")


def explorar(obj, nivel=0, max_nivel=4):
    """Passo 1: imprime só a ESTRUTURA do JSON (chaves e tipos), sem dados."""
    recuo = "  " * nivel
    if isinstance(obj, dict):
        for chave, valor in obj.items():
            print(f"{recuo}{chave}: {type(valor).__name__}")
            if nivel < max_nivel:
                explorar(valor, nivel + 1, max_nivel)
    elif isinstance(obj, list) and obj:
        print(f"{recuo}[lista com {len(obj)} itens, estrutura do primeiro:]")
        if nivel < max_nivel:
            explorar(obj[0], nivel + 1, max_nivel)


def achar_itens(payload):
    """Acha a lista de itens dentro do JSON (aceita lista direta ou dict com uma lista dentro)."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for valor in payload.values():
            if isinstance(valor, list):
                return valor
            if isinstance(valor, dict):
                achado = achar_itens(valor)
                if achado:
                    return achado
    return []


def imprimir_campos(item: dict, prefixo: str = ""):
    """Passo 2: imprime todos os campos simples de um item (entra nos dicts, resume as listas)."""
    for chave, valor in item.items():
        if isinstance(valor, dict):
            imprimir_campos(valor, f"{prefixo}{chave}.")
        elif isinstance(valor, list):
            print(f"   {prefixo}{chave}: {len(valor)} itens")
        else:
            print(f"   {prefixo}{chave}: {valor}")


def mostrar_agora(base_url: str, token: str, recurso: str = "attendance-resume", so_estrutura: bool = False):
    """Mostra cada item (atendente ou departamento) com todas as suas informações."""
    payload = buscar_agora(base_url, token, recurso)
    print(f"=== {recurso} ===")
    if so_estrutura:
        explorar(payload)
        return payload
    itens = achar_itens(payload)
    if not itens:
        print("Nenhuma lista encontrada. Rode com so_estrutura=True para ver o formato do JSON.")
        return payload
    for i, item in enumerate(itens, start=1):
        print(f"\n[{i}]")
        imprimir_campos(item)
    return payload


# Exemplo de uso:
# mostrar_agora(BASE_URL, TOKEN, "attendance-resume", so_estrutura=True)   # 1º: ver o formato
# mostrar_agora(BASE_URL, TOKEN, "attendance-resume")                      # 2º: ver cada atendente
# mostrar_agora(BASE_URL, TOKEN, "departments-resume")                     # 3º: ver cada departamento