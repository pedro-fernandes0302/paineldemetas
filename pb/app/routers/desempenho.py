import asyncio
import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from app.schemas import Csat, DesempenhoResponse, MetricasAtendimento, RVResumo, RVFlags, RVFaixas, MetricasBrutas
from app.rv_calculator import calcular_rv_completo
from app import bigquery_client, digisac_client
from app.auth import UsuarioLogado, get_current_user
from app.config import Settings, get_settings
from app.sheets_client import ler_aba_produtividade, buscar_metas_por_nome
from app.supabase_client import buscar_flags_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/desempenho", tags=["desempenho"])


def _periodo_mes_atual() -> tuple[datetime, datetime]:
    agora = datetime.now(timezone.utc)
    inicio = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if inicio.month == 12:
        proximo_mes = inicio.replace(year=inicio.year + 1, month=1)
    else:
        proximo_mes = inicio.replace(month=inicio.month + 1)
    fim = proximo_mes - timedelta(seconds=1)
    return inicio, fim


async def _buscar_metricas_digisac(settings, digisac_user_id, inicio_iso, fim_iso):
    try:
        metricas = await run_in_threadpool(
            digisac_client.get_user_ticket_metrics,
            settings.digisac_base_url,
            settings.digisac_token,
            digisac_user_id,
            inicio_iso,
            fim_iso,
        )
        csat = await run_in_threadpool(
            digisac_client.get_user_csat,
            settings.digisac_base_url,
            settings.digisac_token,
            digisac_user_id,
            inicio_iso,
            fim_iso,
        )
    except digisac_client.DigisacError as exc:
        raise HTTPException(status_code=502, detail=f"Erro ao consultar o Digisac: {exc}") from exc
    return metricas, csat


async def _buscar_metas_sheets(nome_colaborador: str) -> dict:
    try:
        dados_sheets = await run_in_threadpool(ler_aba_produtividade)
    except Exception as e:
        logger.exception(
            "Falha ao ler planilha P&P — abortando cálculo de RV em vez de "
            "usar valores padrão silenciosos"
        )
        raise HTTPException(
            status_code=503,
            detail="Não foi possível calcular a RV agora: falha ao ler a planilha de produtividade. Tenta de novo em alguns minutos.",
        ) from e

    metas = buscar_metas_por_nome(nome_colaborador, dados_sheets)
    return {
        "meta_individual": metas.get("meta_individual"),
        "meta_subequipe": metas.get("meta_subequipe"),
        "meta_geral_time": metas.get("meta_geral_time"),
        "semanas_batidas": metas.get("semanas_batidas", 0),  # ver nota abaixo
    }


async def _buscar_flags_admin_seguro(email: str) -> dict:
    """Não deixa um erro do Supabase derrubar a rota inteira sem CORS headers."""
    try:
        return await run_in_threadpool(buscar_flags_admin, email)
    except Exception:
        logger.exception("Falha ao buscar flags admin no Supabase, usando valores padrão")
        return {
            "tem_erro_grave": False,
            "tem_advertencia": False,
            "ativado_ciclo1": False,
            "ativado_ciclo2": False,
        }


@router.get("/me", response_model=DesempenhoResponse)
async def get_meu_desempenho(
    settings: Settings = Depends(get_settings),
    usuario: UsuarioLogado = Depends(get_current_user),
):
    # 1. Busca colaborador no BigQuery (as outras chamadas dependem do digisac_user_id dele)
    try:
        colaborador = await run_in_threadpool(
            bigquery_client.get_colaborador_por_email,
            usuario["email"],
            settings.bq_project_id,
            settings.bq_dataset,
            settings.bq_table_colaboradores,
        )
    except bigquery_client.ColaboradorNaoEncontrado as exc:
        raise HTTPException(
            status_code=404,
            detail="Seu usuário não está cadastrado na base de colaboradores. Fale com o admin.",
        ) from exc
    except bigquery_client.BigQueryError as exc:
        logger.exception("Erro ao consultar BigQuery em /me")
        raise HTTPException(status_code=502, detail=f"Erro ao consultar o BigQuery: {exc}") from exc

    inicio, fim = _periodo_mes_atual()
    inicio_iso, fim_iso = inicio.isoformat(), fim.isoformat()

    # 2. Digisac, Sheets e Supabase não dependem uns dos outros -> roda tudo em paralelo
    (metricas, csat), metas_sheets, flags_admin = await asyncio.gather(
        _buscar_metricas_digisac(settings, colaborador["digisac_user_id"], inicio_iso, fim_iso),
        _buscar_metas_sheets(colaborador["nome"]),
        _buscar_flags_admin_seguro(usuario["email"]),
    )

    metricas_digisac = {
        "tempo_medio_atendimento_min": metricas.get("tempo_medio_atendimento_seg", 0) / 60 if metricas.get("tempo_medio_atendimento_seg") else None,
        "primeira_resposta_min": metricas.get("primeira_resposta_seg", 0) / 60 if metricas.get("primeira_resposta_seg") else None,
        "nps_pct": csat.get("csat_percentual"),
        "novos_cpcs": None,
        "registro_sistema_pct": None,
        "avaliacoes_google": None,
    }

    # 3. Calcula o RV
    rv_resultado = calcular_rv_completo(
        nome=colaborador["nome"],
        email=usuario["email"],
        cargo=colaborador["cargo"],
        equipe=colaborador["equipe"],
        digisac_user_id=colaborador["digisac_user_id"],
        metas_sheets=metas_sheets,
        metricas_digisac=metricas_digisac,
        flags_admin=flags_admin,
    )

    return DesempenhoResponse(
        nome=colaborador["nome"],
        cargo=colaborador["cargo"],
        equipe=colaborador["equipe"],
        periodo_inicio=inicio_iso,
        periodo_fim=fim_iso,
        metricas_atendimento=MetricasAtendimento(**metricas),
        csat=Csat(**csat),
        rv=RVResumo(**rv_resultado["rv"]),
        breakdown=rv_resultado["breakdown"],
        flags=RVFlags(**rv_resultado["flags"]),
        faixas=RVFaixas(**rv_resultado["faixas"]),
        metricas_brutas=MetricasBrutas(**rv_resultado["metricas_brutas"]),
    )