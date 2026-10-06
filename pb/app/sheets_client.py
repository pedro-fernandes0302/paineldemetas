"""
Cliente para ler a aba "P&P" (Produtividade & Projeção) de um ARQUIVO EXCEL (.xlsx)
no Google Drive. Usa Drive API para baixar + pandas/openpyxl para parsear.

Índices CONFIRMADOS no .xlsx real (0-based, pandas):
  - índice 1  -> Nome do agente / subequipe (coluna B)
  - índice 10 -> % META, em escala DECIMAL (0.899216 = 89,92%)   (coluna K)
  - índice 20 -> META absoluta, em R$ ou unidades                (coluna U)

Testado contra o .xlsx de AGO-26 (produção atual):
  COLABORADOR_A: idx10=1.025881 (102.59%), idx20=2000.0
  COLABORADOR_B:   idx10=1.01329912 (101.33%), idx20=25000.0

Subequipes detectadas pelo padrão: começa com "SB" e contém "-"
  Ex: "SB1 - YANE", "SB2 - VICTOR", "SB3 - GRAZIELA"

IMPORTANTE: a service account do Cloud Run precisa ter acesso de LEITURA ao
arquivo no Google Drive (compartilhamento normal do Drive, botão "Compartilhar"
com o e-mail da service account) — isso é separado de qualquer IAM role do GCP.
Sem esse compartilhamento, o download aqui embaixo estoura 403.
"""

import io
import re
import logging
import pandas as pd
import google.auth
from typing import Optional
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError
from app.config import get_settings

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
]

# Índices confirmados na aba P&P (0-based) — MESMOS de antes
IDX_NOME = 1          # Coluna B
IDX_META_PCT = 10     # Coluna K -> % META (escala decimal: 1.0 = 100%)
IDX_META_ABS = 20     # Coluna U -> META absoluta

# Tabela da direita (mesma linha, colunas AC-AN): breakdown semanal.
# Cada semana tem 3 colunas: (META DA SEMANA, ALCANÇADO, % META).
# Testado: COLABORADOR_A 2 semanas batidas, COLABORADOR_B 2 semanas batidas.
SEMANAS_COLS = [
    (28, 29, 30),  # semana1: AC, AD, AE
    (31, 32, 33),  # semana2: AF, AG, AH
    (34, 35, 36),  # semana3: AI, AJ, AK
    (37, 38, 39),  # semana4: AL, AM, AN
]
LIMIAR_SEMANA_BATIDA = 1.0  # % META em escala decimal (1.0 = 100%)


NOME_ABA = "P&P"


def _get_drive_service():
    credentials, _ = google.auth.default(scopes=SCOPES)
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def _baixar_excel_do_drive(spreadsheet_id: str) -> pd.DataFrame:
    """
    Baixa o arquivo .xlsx do Google Drive via Drive API e retorna
    um DataFrame só da aba 'P&P' (não carrega as outras abas do arquivo).
    """
    service = _get_drive_service()

    try:
        request = service.files().get_media(fileId=spreadsheet_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            logger.debug("[sheets_client] Download %d%%.", int(status.progress() * 100))
    except HttpError as e:
        logger.error(
            "[sheets_client] Falha ao baixar arquivo id=%s do Drive: %s",
            spreadsheet_id, e,
        )
        raise RuntimeError(f"Erro ao baixar arquivo do Drive: {e}") from e

    fh.seek(0)

    # Lê só a aba "P&P" direto -- evita processar as outras 15 abas do arquivo
    # (arquivo tem ~7MB e algumas abas passam de milhares de linhas).
    try:
        aba_pp = pd.read_excel(fh, sheet_name=NOME_ABA, engine="openpyxl")
    except ValueError as e:
        # Nome da aba pode ter variação de espaço/maiúscula/minúscula.
        # Nesse caso (só nesse caso) caímos pro fallback de carregar tudo
        # e procurar pelo nome normalizado.
        logger.warning(
            "[sheets_client] Aba '%s' não encontrada direto (%s). "
            "Tentando fallback lendo todas as abas.", NOME_ABA, e,
        )
        fh.seek(0)
        try:
            excel_file = pd.read_excel(fh, sheet_name=None, engine="openpyxl")
        except Exception as e2:
            logger.error("[sheets_client] Falha ao ler Excel com pandas: %s", e2)
            raise RuntimeError(f"Erro ao parsear Excel: {e2}") from e2

        aba_pp = next(
            (v for k, v in excel_file.items()
             if k.strip().upper().replace(" ", "") == "P&P"),
            None,
        )
        if aba_pp is None:
            abas_disponiveis = list(excel_file.keys())
            raise RuntimeError(
                f"Aba 'P&P' não encontrada no Excel. Abas disponíveis: {abas_disponiveis}"
            ) from e
    except Exception as e:
        logger.error("[sheets_client] Falha ao ler Excel com pandas: %s", e)
        raise RuntimeError(f"Erro ao parsear Excel: {e}") from e

    logger.info(
        "[sheets_client] Aba 'P&P' carregada: %d linhas x %d colunas",
        len(aba_pp), len(aba_pp.columns),
    )
    return aba_pp


def _parse_percent(val) -> Optional[float]:
    """Converte valor da célula em float. Aceita número puro ou string com % / vírgula."""
    if val is None or pd.isna(val):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace("%", "").replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    try:
        return float(s) if s else None
    except ValueError:
        return None


def _normalize_name(name: str) -> str:
    """Normaliza nome para comparação: maiúsculo, sem acento, só primeiro nome."""
    name = str(name).upper().strip()
    for a, b in [
        ("Á", "A"), ("É", "E"), ("Í", "I"), ("Ó", "O"), ("Ú", "U"),
        ("Â", "A"), ("Ê", "E"), ("Î", "I"), ("Ô", "O"), ("Û", "U"),
        ("Ã", "A"), ("Õ", "O"), ("Ç", "C"), ("À", "A"),
    ]:
        name = name.replace(a, b)
    return name.split()[0] if name else ""


def _find_meta_por_faixa(porcentagem_0_100: float) -> str:
    """
    Recebe porcentagem já convertida pra escala 0-100 (95 = 95%),
    pra ficar consistente com o rv_calculator.py que compara com
    `pct < 95`, `pct < 100` etc.
    """
    if porcentagem_0_100 < 95:
        return "abaixo_95"
    elif porcentagem_0_100 < 100:
        return "95_99"
    elif porcentagem_0_100 < 120:
        return "100_119"
    elif porcentagem_0_100 < 150:
        return "120_149"
    elif porcentagem_0_100 < 200:
        return "150_199"
    else:
        return "200_ou_mais"


        


def ler_aba_produtividade() -> dict:
    """
    Lê a aba "P&P" do Excel (.xlsx) no Drive e retorna dicionário com:
    - por_agente: {nome_normalizado: {"meta_individual": float (0-100), ...}}
    - por_subequipe: {subequipe: {"meta_subequipe": float (0-100), ...}}

    Levanta RuntimeError se a leitura falhar OU vier vazia — nunca retorna
    um dict "vazio mas válido" silenciosamente.
    """
    settings = get_settings()
    spreadsheet_id = settings.google_sheets_spreadsheet_id

    df = _baixar_excel_do_drive(spreadsheet_id)

    if df.empty:
        raise RuntimeError(
            f"Planilha 'P&P' (id={spreadsheet_id}) retornou DataFrame vazio. "
            f"Provável causa: arquivo corrompido, sem permissão de leitura, "
            f"ou aba vazia."
        )

    logger.info("[sheets_client] Linhas lidas da aba 'P&P': %d", len(df))

    por_agente = {}
    por_subequipe = {}
    meta_geral_empresa = None
    subequipe_atual = None

    for idx, row in df.iterrows():
        if len(row) <= IDX_NOME:
            continue

        identificador = str(row.iloc[IDX_NOME]).strip().upper() if pd.notna(row.iloc[IDX_NOME]) else ""

        # --- Filtros de skip ---
        if not identificador or identificador in ["-", "AGENTE"]:
            continue

        if identificador in ["NOVATO(A)", "NOVATO", "NOVATA"]:
            continue

        skip_keywords = [
            "TOTAL", "META DA SEMANA", "SEMANA", "PERÍODO",
            "CÁLCULO", "CONFERÊNCIA", "VICE LÍDERES",
            "QTD. DIAS ÚTEIS", "TIME", "ACORDOS GERADOS",
        ]
        if any(kw in identificador for kw in skip_keywords):
            continue

        if len(identificador) < 2:
            continue

        meta_pct_raw = _parse_percent(row.iloc[IDX_META_PCT]) if len(row) > IDX_META_PCT else None
        meta_abs = _parse_percent(row.iloc[IDX_META_ABS]) if len(row) > IDX_META_ABS else None

        # Converte de escala decimal (0.8992) pra escala 0-100 (89.92)
        meta_pct = meta_pct_raw * 100 if meta_pct_raw is not None else None

        # --- Detectar SUBEQUIPE (ex: "SB1 - YANE", "SB2 - VICTOR") ---
        if identificador.startswith("SB") and "-" in identificador:
            subequipe_atual = identificador
            if meta_pct is not None and meta_pct > 0:
                por_subequipe[subequipe_atual] = {
                    "meta_subequipe": meta_pct,
                    "meta_subequipe_abs": meta_abs,
                    "meta_geral": None,
                }
                logger.debug(
                    "[sheets_client] Sub-equipe: %s | %%META=%.2f | META=%s",
                    subequipe_atual, meta_pct, meta_abs,
                )
            continue

        # --- Detectar JURÍD (subequipe especial, mesmo padrão de "-") ---
        if "JURÍD" in identificador and "-" in identificador:
            subequipe_atual = identificador
            if meta_pct is not None and meta_pct > 0:
                por_subequipe[subequipe_atual] = {
                    "meta_subequipe": meta_pct,
                    "meta_subequipe_abs": meta_abs,
                    "meta_geral": None,
                }
            continue

        # --- Agente individual ---
        nome_normalizado = _normalize_name(identificador)
        if not nome_normalizado:
            continue

        if meta_pct is not None and meta_pct > 0:
            # Breakdown semanal (tabela da direita, mesma linha: colunas AC-AN)
            semanas = []
            semanas_batidas = 0
            for meta_i, alc_i, pct_i in SEMANAS_COLS:
                if len(row) <= pct_i:
                    semanas.append({"meta": None, "alcancado": None, "pct": None, "bateu": False})
                    continue
                sem_meta = _parse_percent(row.iloc[meta_i])
                sem_alc = _parse_percent(row.iloc[alc_i])
                sem_pct_raw = _parse_percent(row.iloc[pct_i])
                bateu = sem_pct_raw is not None and sem_pct_raw >= LIMIAR_SEMANA_BATIDA
                if bateu:
                    semanas_batidas += 1
                semanas.append({
                    "meta": sem_meta,
                    "alcancado": sem_alc,
                    "pct": sem_pct_raw * 100 if sem_pct_raw is not None else None,
                    "bateu": bateu,
                })

            por_agente[nome_normalizado] = {
                "meta_individual": meta_pct,
                "meta_individual_abs": meta_abs,
                "meta_subequipe": (
                    por_subequipe.get(subequipe_atual, {}).get("meta_subequipe")
                    if subequipe_atual else None
                ),
                "subequipe": subequipe_atual,
                "semanas": semanas,
                "semanas_batidas": semanas_batidas,
            }
            logger.debug(
                "[sheets_client] Agente: %s (%s) | %%META=%.2f | META=%s | Sub=%s | semanas_batidas=%d",
                nome_normalizado, identificador, meta_pct, meta_abs, subequipe_atual, semanas_batidas,
            )

    logger.info(
        "[sheets_client] Resumo: %d agentes | %d sub-equipes",
        len(por_agente), len(por_subequipe),
    )

    if not por_agente:
        raise RuntimeError(
            f"Planilha 'P&P' tem {len(df)} linhas mas 0 agentes "
            f"reconhecidos. Provável mudança de layout — colunas B/K/U não "
            f"batem mais com IDX_NOME/IDX_META_PCT/IDX_META_ABS."
        )

    return {
        "por_agente": por_agente,
        "por_subequipe": por_subequipe,
        "meta_geral_empresa": meta_geral_empresa,
    }


def buscar_metas_por_nome(nome: str, dados_sheets: dict) -> dict:
    """Busca as metas de um colaborador pelo nome (primeiro nome). Retorna % em escala 0-100."""
    nome_norm = _normalize_name(nome)
    agente = dados_sheets["por_agente"].get(nome_norm, {})

    if not agente:
        logger.warning(
            "[sheets_client] Agente '%s' (normalizado: '%s') não encontrado "
            "em por_agente. Nomes disponíveis: %s",
            nome, nome_norm, list(dados_sheets["por_agente"].keys()),
        )

    subequipe = agente.get("subequipe")
    subequipe_data = dados_sheets["por_subequipe"].get(subequipe, {}) if subequipe else {}

    meta_individual = agente.get("meta_individual")
    meta_subequipe = agente.get("meta_subequipe") or subequipe_data.get("meta_subequipe")
    meta_geral_time = subequipe_data.get("meta_geral")

    return {
        "meta_individual": meta_individual,
        "meta_individual_abs": agente.get("meta_individual_abs"),
        "meta_subequipe": meta_subequipe,
        "meta_subequipe_abs": subequipe_data.get("meta_subequipe_abs"),
        "meta_geral_time": meta_geral_time,
        "meta_geral_empresa": dados_sheets["meta_geral_empresa"],
        "faixa_individual": _find_meta_por_faixa(meta_individual) if meta_individual is not None else None,
        "faixa_subequipe": _find_meta_por_faixa(meta_subequipe) if meta_subequipe is not None else None,
        "faixa_geral_time": _find_meta_por_faixa(meta_geral_time) if meta_geral_time is not None else None,
        "semanas": agente.get("semanas", []),
        "semanas_batidas": agente.get("semanas_batidas", 0),
    }