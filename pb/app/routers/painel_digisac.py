import json
import os
import threading
import time
from io import BytesIO
from typing import Literal, Optional

import pandas as pd
from fastapi import APIRouter, Query
from google.auth import default
from google.cloud import bigquery
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ---------- CONFIG ----------

PROJETO = os.getenv("GCP_PROJECT_ID", "seu-projeto-gcp")
DATASET = os.getenv("DATASET", "painel_digisac")
TABELA = os.getenv("TABELA", "campanhas_digisac")
CUSTO_POR_MENSAGEM = float(os.getenv("CUSTO_POR_MENSAGEM", "0.03"))

DRIVE_FILE_ID = os.getenv("DRIVE_FILE_ID", "")
ABAS_CREDORES = ["CARTEIRA_B", "CARTEIRA_E", "CARTEIRA_D", "CARTEIRA_A", "CARTEIRA_C", "CARTEIRA_M", "OUTRAS"]
CARTEIRAS_CONHECIDAS = [
    "CARTEIRA_B", "CARTEIRA_A", "CARTEIRA_C", "CARTEIRA_D", "CARTEIRA_E", "CARTEIRA_F", "CARTEIRA_G",
    "CARTEIRA_H", "CARTEIRA_I", "CARTEIRA_J", "CARTEIRA_K", "CARTEIRA_L", "CARTEIRA_M",
]

CACHE_TTL = 600  # segundos

router = APIRouter(prefix="/painel-digisac", tags=["painel-digisac"])

# ---------- CACHE (substitui o st.cache_data) ----------

_cache: dict = {}
_lock = threading.Lock()


def cached(chave, ttl, fn):
    """Cache em memória com TTL. Se fn levantar exceção, nada é cacheado."""
    with _lock:
        item = _cache.get(chave)
        if item and time.time() - item[0] < ttl:
            return item[1]
    valor = fn()
    with _lock:
        _cache[chave] = (time.time(), valor)
    return valor


# ---------- HELPERS ----------

def extrair_carteira(titulo):
    if pd.isna(titulo):
        return "NÃO IDENTIFICADO"
    titulo_upper = str(titulo).upper()
    for carteira in CARTEIRAS_CONHECIDAS:
        if carteira in titulo_upper:
            return carteira
    return "OUTROS"


def hoje_brasil():
    """Data de 'hoje' no fuso de Brasília, independente do fuso do servidor."""
    return pd.Timestamp.now(tz="America/Sao_Paulo").date()


def limpar_moeda(serie):
    """
    Converte pra número lidando com formatos misturados entre abas:
    - Já numérico -> usa direto.
    - Texto BR "R$ 1.234,56" (tem vírgula) -> remove ponto de milhar, vírgula vira ponto.
    - Texto sem vírgula "166.66" -> usa direto.
    """
    if pd.api.types.is_numeric_dtype(serie):
        return pd.to_numeric(serie, errors="coerce")

    texto = serie.astype(str).str.strip().str.replace("R$", "", regex=False).str.strip()
    tem_virgula = texto.str.contains(",", na=False)

    texto_br = (
        texto[tem_virgula]
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    texto_final = texto.copy()
    texto_final[tem_virgula] = texto_br

    return pd.to_numeric(texto_final, errors="coerce")


def para_json(df):
    """DataFrame -> lista de dicts JSON-safe (NaN vira null, numpy vira python)."""
    return json.loads(df.to_json(orient="records", date_format="iso"))


def variacao_pct(atual, anterior):
    if not anterior:
        return None
    return round((atual - anterior) / anterior * 100, 1)


def pct_abertura(visualizadas, enviadas):
    return (
        (visualizadas / enviadas * 100)
        .replace([float("inf"), float("-inf")], 0)
        .round(1)
        .fillna(0)
    )


# ---------- CARGA DE DADOS ----------

def _carregar_dados():
    client = bigquery.Client(project=PROJETO)

    query = f"""
        SELECT *
        FROM `{PROJETO}.{DATASET}.{TABELA}`
        WHERE data_inicio >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 35 DAY)
    """

    df = client.query(query).to_dataframe(create_bqstorage_client=False)
    df["data_inicio"] = (
        pd.to_datetime(df["data_inicio"], utc=True)
        .dt.tz_convert("America/Sao_Paulo")
        .dt.tz_localize(None)
    )
    df["data"] = df["data_inicio"].dt.date

    # compatibilidade com dados antigos
    for col in [
        "stats_enviadas", "stats_servidor", "stats_recebidas",
        "stats_visualizadas", "stats_nao_enviadas", "stats_erro",
    ]:
        if col not in df.columns:
            df[col] = 0

    df["carteira"] = df["titulo"].apply(extrair_carteira)
    return df


def carregar_dados():
    return cached("dados", CACHE_TTL, _carregar_dados)


def _carregar_boletos():
    """Baixa o .xlsx do Drive e retorna (df_boletos_pagos, avisos).

    Levanta exceção se não conseguir conectar/baixar (nesse caso não cacheia).
    """
    avisos = []

    scopes = ["https://www.googleapis.com/auth/drive.readonly"]
    creds, _ = default(scopes=scopes)
    drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)

    request = drive_service.files().get_media(fileId=DRIVE_FILE_ID)
    arquivo = BytesIO()
    downloader = MediaIoBaseDownload(arquivo, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    arquivo.seek(0)

    frames = []
    abas = pd.read_excel(arquivo, sheet_name=None, engine="openpyxl")

    col_valor_opcoes = ["VALOR BOLETO", "VALOR ACORDO"]
    col_ho_opcoes = ["HO"]
    col_data_opcoes = ["DATA PAGTO.", "DATA PAGAM"]
    col_status = "STATUS"

    for nome_aba in ABAS_CREDORES:
        try:
            if nome_aba not in abas:
                avisos.append(f"Aba não encontrada no Excel: {nome_aba}")
                continue

            df_aba = abas[nome_aba].copy()
            df_aba.columns = [str(c).strip() for c in df_aba.columns]

            # nomes de colunas variam entre as abas
            col_valor = next((c for c in col_valor_opcoes if c in df_aba.columns), None)
            col_ho = next((c for c in col_ho_opcoes if c in df_aba.columns), None)
            col_data = next((c for c in col_data_opcoes if c in df_aba.columns), None)

            faltando = []
            if col_valor is None:
                faltando.append("/".join(col_valor_opcoes))
            if col_data is None:
                faltando.append("/".join(col_data_opcoes))
            if col_status not in df_aba.columns:
                faltando.append(col_status)
            if faltando:
                avisos.append(f"Aba {nome_aba} sem colunas necessárias: {', '.join(faltando)}")
                continue

            colunas_usar = [col_valor, col_data, col_status] + ([col_ho] if col_ho else [])
            df_aba = df_aba[colunas_usar].copy()
            df_aba["credor"] = "OUTROS" if nome_aba == "OUTRAS" else nome_aba

            df_aba = df_aba[
                df_aba[col_status].astype(str).str.strip().str.upper() == "PAGO"
            ].copy()

            df_aba[col_valor] = limpar_moeda(df_aba[col_valor])
            df_aba["honorario"] = limpar_moeda(df_aba[col_ho]) if col_ho else 0.0
            df_aba[col_data] = pd.to_datetime(df_aba[col_data], dayfirst=True, errors="coerce")

            df_aba = df_aba.dropna(subset=[col_valor, col_data])
            df_aba["honorario"] = df_aba["honorario"].fillna(0.0)
            df_aba = df_aba.rename(columns={col_valor: "valor", col_data: "data_pagto"})
            df_aba["data"] = df_aba["data_pagto"].dt.date

            frames.append(df_aba[["data", "valor", "honorario", "credor"]])

        except Exception as e:
            avisos.append(f"Erro ao ler aba {nome_aba}: {repr(e)}")
            continue

    if not frames:
        return pd.DataFrame(columns=["data", "valor", "honorario", "credor"]), avisos

    return pd.concat(frames, ignore_index=True), avisos


def carregar_boletos():
    """Retorna (df, avisos). Se falhar a conexão, devolve df vazio + aviso (sem cachear)."""
    try:
        return cached("boletos", CACHE_TTL, _carregar_boletos)
    except Exception as e:
        vazio = pd.DataFrame(columns=["data", "valor", "honorario", "credor"])
        return vazio, [f"Erro ao conectar ao arquivo Excel no Google Drive: {repr(e)}"]


# ---------- CÁLCULOS ----------

def janelas(periodo: str):
    """Retorna (ini, fim, ini_anterior, fim_anterior, rotulo_anterior)."""
    hoje = hoje_brasil()

    if periodo == "dia":
        ontem = hoje - pd.Timedelta(days=1)
        anteontem = hoje - pd.Timedelta(days=2)
        return ontem, ontem, anteontem, anteontem, "o dia retrasado"

    dias = 7 if periodo == "semana" else 30
    ini = hoje - pd.Timedelta(days=dias - 1)
    fim_ant = hoje - pd.Timedelta(days=dias)
    ini_ant = fim_ant - pd.Timedelta(days=dias - 1)
    rotulo = "a semana anterior" if periodo == "semana" else "o mês anterior"
    return ini, hoje, ini_ant, fim_ant, rotulo


def filtrar_intervalo(df, ini, fim):
    return df[(df["data"] >= ini) & (df["data"] <= fim)]


def calcular_metricas(df_filtrado, df_boletos, data_inicio, data_fim):
    """Indicadores de um período. Retorna None se não houver campanhas."""
    if df_filtrado.empty:
        return None

    total_enviadas = int(df_filtrado["stats_enviadas"].fillna(0).sum())
    total_visualizadas = int(df_filtrado["stats_visualizadas"].fillna(0).sum())
    taxa_geral = round((total_visualizadas / total_enviadas) * 100, 1) if total_enviadas > 0 else 0
    total_campanhas = int(df_filtrado["campaign_id"].nunique())
    custo_total = total_enviadas * CUSTO_POR_MENSAGEM

    df_bol_periodo = filtrar_intervalo(df_boletos, data_inicio, data_fim)
    total_boletos = float(df_bol_periodo["valor"].sum())
    total_honorarios = float(df_bol_periodo["honorario"].sum())

    return {
        "campanhas": total_campanhas,
        "enviadas": total_enviadas,
        "visualizadas": total_visualizadas,
        "taxa_abertura": float(taxa_geral),
        "custo": round(float(custo_total), 2),
        "boletos": total_boletos,
        "honorarios": total_honorarios,
    }


def montar_tabela_listas(df_filtrado):
    tabela = (
        df_filtrado.groupby("titulo")
        .agg(
            carteira=("carteira", "first"),
            enviadas=("stats_enviadas", "sum"),
            servidor=("stats_servidor", "sum"),
            recebidas=("stats_recebidas", "sum"),
            visualizadas=("stats_visualizadas", "sum"),
            nao_enviadas=("stats_nao_enviadas", "sum"),
            erro=("stats_erro", "sum"),
        )
        .reset_index()
    )
    tabela["pct_abertura"] = pct_abertura(tabela["visualizadas"], tabela["enviadas"])
    tabela = tabela.sort_values("enviadas", ascending=False)
    return para_json(tabela)


def montar_tabela_carteiras(df_filtrado):
    resumo = (
        df_filtrado.groupby("carteira")[
            ["stats_enviadas", "stats_servidor", "stats_recebidas",
             "stats_visualizadas", "stats_nao_enviadas"]
        ]
        .sum()
        .reset_index()
    )
    resumo["pct_abertura"] = pct_abertura(resumo["stats_visualizadas"], resumo["stats_enviadas"])
    resumo = resumo.sort_values("stats_enviadas", ascending=False)
    resumo = resumo.rename(columns={
        "stats_enviadas": "enviadas",
        "stats_servidor": "servidor",
        "stats_recebidas": "recebidas",
        "stats_visualizadas": "visualizadas",
        "stats_nao_enviadas": "nao_enviadas",
    })
    return para_json(resumo)


def montar_evolucao(df_filtrado):
    evolucao = (
        df_filtrado.groupby("data")[["stats_enviadas", "stats_visualizadas"]]
        .sum()
        .reset_index()
        .sort_values("data")
        .rename(columns={"stats_enviadas": "enviadas", "stats_visualizadas": "lidas"})
    )
    evolucao["data"] = evolucao["data"].astype(str)
    return para_json(evolucao)


def filtrar_carteiras(df, df_boletos, carteiras):
    if carteiras:
        df = df[df["carteira"].isin(carteiras)]
        df_boletos = df_boletos[df_boletos["credor"].isin(carteiras)]
    return df, df_boletos


# ---------- ENDPOINTS ----------

@router.get("/carteiras")
def listar_carteiras():
    df = carregar_dados()
    return {"carteiras": sorted(df["carteira"].unique().tolist())}


@router.get("/painel/{periodo}")
def painel(
    periodo: Literal["dia", "semana", "mes"],
    carteiras: Optional[list[str]] = Query(default=None, description="Repita o param: ?carteiras=CARTEIRA_B&carteiras=CARTEIRA_E"),
):
    """
    Retorna tudo que o painel mostrava para o período:
    métricas atuais, métricas do período anterior, variação %, tabela por lista,
    comparativo por carteira e evolução diária.
    """
    df = carregar_dados()
    df_boletos, avisos = carregar_boletos()
    df, df_boletos = filtrar_carteiras(df, df_boletos, carteiras)

    ini, fim, ini_ant, fim_ant, rotulo_ant = janelas(periodo)

    df_atual = filtrar_intervalo(df, ini, fim)
    df_ant = filtrar_intervalo(df, ini_ant, fim_ant)

    metricas = calcular_metricas(df_atual, df_boletos, ini, fim)
    metricas_ant = calcular_metricas(df_ant, df_boletos, ini_ant, fim_ant)

    variacao = None
    if metricas and metricas_ant:
        variacao = {k: variacao_pct(metricas[k], metricas_ant[k]) for k in metricas}

    resposta = {
        "periodo": periodo,
        "intervalo": {"inicio": str(ini), "fim": str(fim)},
        "intervalo_anterior": {"inicio": str(ini_ant), "fim": str(fim_ant), "rotulo": rotulo_ant},
        "carteiras_filtradas": carteiras or [],
        "total_campanhas_carregadas": int(len(df)),
        "metricas": metricas,
        "metricas_anterior": metricas_ant,
        "variacao_pct": variacao,
        "avisos": avisos,
        "tabela_listas": [],
        "tabela_carteiras": [],
        "evolucao_diaria": [],
    }

    if not df_atual.empty:
        resposta["tabela_listas"] = montar_tabela_listas(df_atual)
        resposta["tabela_carteiras"] = montar_tabela_carteiras(df_atual)
        resposta["evolucao_diaria"] = montar_evolucao(df_atual)

    return resposta


@router.post("/cache/limpar")
def limpar_cache():
    with _lock:
        _cache.clear()
    return {"status": "cache limpo"}
