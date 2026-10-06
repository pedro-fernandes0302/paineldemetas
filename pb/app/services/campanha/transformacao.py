#imports obrigatorios
import json
import logging
import os

from google.cloud import bigquery, storage

logging.basicConfig(
    filename="pipeline.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


def carregar_config():
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def carregar_desconto():
    """Lê o desconto.json do disco local (mesma pasta do config.json)."""
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "desconto.json")
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)["desconto"] / 100


def escapar_sql(valor):
    return str(valor).replace("'", "\\'").upper()


def montar_sql_valor_atualizado():
    """
    Monta a expressão SQL do TOTAL COM HO, replicando a planilha de honorários:

        JUROS        = RISCO * (1%/30) * ATRASO
        MULTAS       = RISCO * 2%
        TOTAL SEM HO = RISCO + JUROS + MULTAS
        % HO         = <=180d: 5% | <=1095d: 8% | <=1825d: 10% | senão: 20%
        VALOR_ATUALIZADO = TOTAL SEM HO * (1 + % HO)

    RISCO vem da planilha em formato BR (vírgula decimal, ex: "3700,60"),
    por isso troca vírgula por ponto ANTES do SAFE_CAST.
    """
    risco = "SAFE_CAST(REPLACE(CAST(RISCO AS STRING), ',', '.') AS FLOAT64)"
    atraso = "SAFE_CAST(ATRASO AS INT64)"

    juros = f"{risco} * (0.01/30) * {atraso}"
    multas = f"{risco} * 0.02"
    total_sem_ho = f"({risco} + {juros} + {multas})"

    perc_ho = f"""CASE
        WHEN {atraso} <= 180  THEN 0.05
        WHEN {atraso} <= 1095 THEN 0.08
        WHEN {atraso} <= 1825 THEN 0.10
        ELSE 0.20
    END"""

    return f"{total_sem_ho} * (1 + {perc_ho})"


def transformar(nome_template, credor, atraso_dias_inicio=None, atraso_dias_fim=None,
                filtro_cpc=None, marcador=None, coligada_inicio=None, coligada_fim=None,
                coligada_lista=None, defasagem_min=None, valor_min=None):
    """
    Cria a tabela dados_tratados_{nome_template} no BigQuery aplicando os
    filtros recebidos diretamente da estratégia.

    Parâmetros:
        nome_template     : chave única do template (ex: CARTEIRA_B_5A7_GERAL)
        credor            : nome real do credor para o LIKE. Aceita string única
                            (ex: "CARTEIRA_B - GRADUÇÃO E PÓS GRAD.") ou lista de nomes
                            (ex: CARTEIRA_K -> ["CARTEIRA_K FLV", "CARTEIRA_K - PESSOAL"])
        atraso_dias_inicio: int ou None. Filtra ATRASO >= esse valor (em dias)
        atraso_dias_fim   : int ou None. Filtra ATRASO <= esse valor (em dias).
                            Se só o início vier preenchido, filtra "a partir de" (sem teto).
        filtro_cpc        : "COM CPC", "SEM CPC" ou None (sem filtro)
        coligada_inicio   : int ou None (apenas CARTEIRA_A, modo intervalo — BETWEEN)
        coligada_fim      : int ou None (apenas CARTEIRA_A, modo intervalo — BETWEEN)
        coligada_lista    : list[int] ou None (apenas CARTEIRA_A, modo lista específica — IN (...)).
                            Se vier preenchida, tem prioridade sobre coligada_inicio/fim.
        defasagem_min     : int ou None. Filtra a coluna DEFASAGEM (campo próprio da
                            base, diferente de ATRASO) > esse valor, sem teto.
                            Aplica JUNTO com o filtro de FAIXA_ATRASO, não substitui.
        valor_min         : float ou None. Filtra VALOR_ATUALIZADO >= esse valor
                            (reaplica a mesma fórmula usada na coluna de saída).
                            Aplica JUNTO com os demais filtros.
    """
    config = carregar_config()
    projeto = config["projeto"]
    dataset = config["dataset"]
    tabela_origem = config["tabela_origem"]
    colunas_saida = config["colunas_saida"]

    sql_valor_atualizado = montar_sql_valor_atualizado()

    # só busca o desconto.json se algum template realmente precisar dele
    desconto = carregar_desconto() if "VALOR_QUITACAO" in colunas_saida else None

    # Monta SELECT com MAIS_55, VALOR_ATUALIZADO e VALOR_QUITACAO tratados
    colunas_processadas = []
    for col in colunas_saida:
        if col == "MAIS_55":
            colunas_processadas.append("CONCAT('55', CAST(NUMERO AS STRING)) AS MAIS_55")
        elif col == "VALOR_ATUALIZADO":
            colunas_processadas.append(f"ROUND(({sql_valor_atualizado}), 2) AS VALOR_ATUALIZADO")
        elif col == "VALOR_QUITACAO":
            colunas_processadas.append(f"ROUND(({sql_valor_atualizado}) * (1 - {desconto}), 2) AS VALOR_QUITACAO")
        else:
            colunas_processadas.append(col)
    colunas = ", ".join(colunas_processadas)

    # Filtro de credor — aceita string única OU lista de nomes (ex: CARTEIRA_K
    # cobrindo "CARTEIRA_K FLV" e "CARTEIRA_K - PESSOAL" ao mesmo tempo)
    if isinstance(credor, list):
        condicoes = " OR ".join(
            f"UPPER(CREDOR) LIKE '%{escapar_sql(c)}%'" for c in credor
        )
        filtro_credor = f"({condicoes})"
    else:
        filtro_credor = f"UPPER(CREDOR) LIKE '%{escapar_sql(credor)}%'"

    # Filtro de faixa de atraso (agora numérico, não mais texto de faixa fixa)
    if atraso_dias_inicio is not None and atraso_dias_fim is not None:
        filtro_atraso = (
            f"AND SAFE_CAST(ATRASO AS INT64) "
            f"BETWEEN {atraso_dias_inicio} AND {atraso_dias_fim}"
        )
    elif atraso_dias_inicio is not None:
        filtro_atraso = f"AND SAFE_CAST(ATRASO AS INT64) >= {atraso_dias_inicio}"
    else:
        filtro_atraso = ""

    # Filtro de CPC
    if filtro_cpc:
        filtro_cpc_sql = f"AND UPPER(CPC) = '{escapar_sql(filtro_cpc)}'"
    else:
        filtro_cpc_sql = ""

    # Filtro de marcador (ex: EXTRAJUDICIAL, AJUIZAMENTO)
    if marcador:
        filtro_marcador_sql = f"AND UPPER(MARCADOR_ORIGINAL) LIKE '%{escapar_sql(marcador)}%'"
    else:
        filtro_marcador_sql = ""

    # Filtro de coligada (apenas CARTEIRA_A). Lista específica tem prioridade sobre intervalo.
    if coligada_lista:
        valores_coligada = ", ".join(str(int(v)) for v in coligada_lista)
        filtro_coligada = (
            f"AND SAFE_CAST(COLIGADA AS INT64) IN ({valores_coligada})"
        )
    elif coligada_inicio is not None and coligada_fim is not None:
        filtro_coligada = (
            f"AND SAFE_CAST(COLIGADA AS INT64) "
            f"BETWEEN {coligada_inicio} AND {coligada_fim}"
        )
    else:
        filtro_coligada = ""

    # Filtro de DEFASAGEM (campo próprio da base, diferente de ATRASO).
    # "maior que" o valor informado, sem teto — aplica JUNTO com o filtro
    # de FAIXA_ATRASO (não substitui, é um filtro adicional).
    if defasagem_min is not None:
        filtro_defasagem = f"AND SAFE_CAST(DEFASAGEM AS INT64) > {defasagem_min}"
    else:
        filtro_defasagem = ""

    # Filtro de VALOR (VALOR_ATUALIZADO, o mesmo cálculo usado na coluna de
    # saída) — reaplica a mesma fórmula (RISCO + juros + multas + % HO) no
    # WHERE, já que VALOR_ATUALIZADO só existe como coluna calculada no SELECT.
    if valor_min is not None:
        filtro_valor = f"AND ({sql_valor_atualizado}) >= {valor_min}"
    else:
        filtro_valor = ""

    query = f"""
        CREATE OR REPLACE TABLE
        `{projeto}.{dataset}.dados_tratados_{nome_template}` AS

        SELECT {colunas}
        FROM `{projeto}.{dataset}.{tabela_origem}`
        WHERE {filtro_credor}
          {filtro_cpc_sql}
          {filtro_atraso}
          {filtro_marcador_sql}
          {filtro_coligada}
          {filtro_defasagem}
          {filtro_valor}
          AND NUMERO IS NOT NULL
          AND CLIENTE IS NOT NULL
          AND TRIM(CAST(CLIENTE AS STRING)) != ''
    """

    client = bigquery.Client(project=projeto)
    client.query(query).result()

    total = list(
        client.query(
            f"SELECT COUNT(*) AS total "
            f"FROM `{projeto}.{dataset}.dados_tratados_{nome_template}`"
        ).result()
    )[0].total

    logging.info(f"Template {nome_template}: {total} linhas tratadas")
    print(f"Template {nome_template}: {total} linhas filtradas!")

    return total
