"""
Cliente Supabase para ler flags administrativas (erros graves, advertências, ativações).
"""
from typing import Optional
from supabase import create_client, Client

from app.config import get_settings


def _get_supabase_client() -> Client:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_key:
        raise RuntimeError("SUPABASE_URL e SUPABASE_SERVICE_KEY devem estar configurados")
    return create_client(settings.supabase_url, settings.supabase_service_key)


def buscar_flags_admin(email: str) -> dict:
    try:
        sb = _get_supabase_client()
    except RuntimeError:
        return {
            "tem_erro_grave": False,
            "tem_advertencia": False,
            "ativado_ciclo1": False,
            "ativado_ciclo2": False,
        }

    try:
        resp_erro = sb.table("erros_graves").select("*").eq("email", email).execute()
        tem_erro_grave = len(resp_erro.data) > 0
    except Exception:
        tem_erro_grave = False

    try:
        resp_adv = sb.table("advertencias").select("*").eq("email", email).execute()
        tem_advertencia = len(resp_adv.data) > 0
    except Exception:
        tem_advertencia = False

    try:
        resp_atv = sb.table("ativacoes").select("*").eq("email", email).execute()
        ativado_ciclo1 = any(r.get("ciclo") == 1 and r.get("ativo") for r in resp_atv.data)
        ativado_ciclo2 = any(r.get("ciclo") == 2 and r.get("ativo") for r in resp_atv.data)
    except Exception:
        ativado_ciclo1 = False
        ativado_ciclo2 = False

    return {
        "tem_erro_grave": tem_erro_grave,
        "tem_advertencia": tem_advertencia,
        "ativado_ciclo1": ativado_ciclo1,
        "ativado_ciclo2": ativado_ciclo2,
    }