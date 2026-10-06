import io
import logging
import os

import pandas as pd
from google.cloud import bigquery, storage

logging.basicConfig(
    filename="pipeline.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

PROJETO = os.getenv("GCP_PROJECT_ID", "seu-projeto-gcp")
DATASET = os.getenv("BQ_DATASET_CAMPANHA", "cobranca")
TABELA = "dados_brutos_com_formulas"

BUCKET = os.getenv("GCS_BUCKET", "seu-bucket")
PASTA_CLIENTES = "clientes/"

COLUNAS_ESPERADAS = [
    "CLIENTE",
    "NUMERO",
    "CREDOR",
    "CPC",
    "ATRASO",
    "CONTRATO",
    "COLIGADA",
    "MARCADOR_ORIGINAL",
    "RISCO"
]


def calcular_atraso(row):
    """
    Retorna o atraso em dias (número inteiro), sem categorizar em faixas.
    A categorização em faixas agora é feita na hora do filtro (transformacao.py),
    com base no que a planilha de estratégia pedir — não fica mais travada
    em buckets fixos definidos aqui.
    """
    dias = row["ATRASO"]

    try:
        dias = float(dias)
    except Exception:
        return None

    if dias < 0:
        return None

    return int(dias)


def pegar_arquivo_mais_recente_bucket(prefixo=PASTA_CLIENTES):
    storage_client = storage.Client(project=PROJETO)
    blobs = list(storage_client.list_blobs(BUCKET, prefix=prefixo))

    arquivos = [
        blob for blob in blobs
        if not blob.name.endswith("/")
        and blob.name.lower().endswith((".xlsx", ".xls"))
    ]

    if not arquivos:
        raise FileNotFoundError(
            f"Nenhum Excel encontrado no bucket '{BUCKET}' dentro da pasta '{prefixo}'."
        )

    arquivo_mais_recente = max(arquivos, key=lambda blob: blob.updated)

    print(f"Arquivo de clientes encontrado: gs://{BUCKET}/{arquivo_mais_recente.name}")
    logging.info(f"Arquivo de clientes encontrado: {arquivo_mais_recente.name}")

    return arquivo_mais_recente


def baixar_excel_bucket():
    blob = pegar_arquivo_mais_recente_bucket()

    # Recria o blob sem a generation "congelada" do list_blobs,
    # pra sempre baixar a versão mais recente e evitar 404 por
    # sobrescrita concorrente do arquivo no bucket.
    storage_client = storage.Client(project=PROJETO)
    blob_atual = storage_client.bucket(BUCKET).blob(blob.name)

    conteudo = blob_atual.download_as_bytes()

    buffer = io.BytesIO(conteudo)
    buffer.seek(0)
    return buffer


def validar_colunas(df, colunas, nome_aba):
    faltando = [col for col in colunas if col not in df.columns]

    if faltando:
        raise ValueError(
            f"Colunas faltando na aba {nome_aba}: {faltando}. "
            f"Colunas encontradas: {list(df.columns)}"
        )


def carregar_e_filtrar(buffer):
    cobranca = pd.read_excel(buffer, sheet_name="Cobrança")
    buffer.seek(0)
    telefones = pd.read_excel(buffer, sheet_name="Telefones")

    validar_colunas(
        cobranca,
        ["CPF/CNPJ", "CLIENTE", "CREDOR", "ATRASO", "CONTRATO", "ACORDO", "MARCADOR", "RISCO"],
        "Cobrança"
    )

    validar_colunas(
        telefones,
        ["CPF/CNPJ", "CLIENTE", "CONTATO", "ATIVO", "NUMERO",],
        "Telefones"
    )

    cobranca["CPF/CNPJ"] = cobranca["CPF/CNPJ"].astype(str).str.strip()
    telefones["CPF/CNPJ"] = telefones["CPF/CNPJ"].astype(str).str.strip()

    cobranca_apto = cobranca[
        cobranca["ACORDO"].astype(str).str.strip().str.upper() == "NÃO"
    ][
        ["CPF/CNPJ", "CLIENTE", "CREDOR", "ATRASO", "CONTRATO", "ACORDO", "MARCADOR", "RISCO"]
    ]

    df = telefones.merge(
        cobranca_apto,
        on="CPF/CNPJ",
        how="inner",
        suffixes=("_tel", "_cob")
    )

    df = df.rename(columns={"CLIENTE_cob": "CLIENTE"})

    if "CLIENTE_tel" in df.columns:
        df = df.drop(columns=["CLIENTE_tel"])

    df["MARCADOR_ORIGINAL"] = (
        df["MARCADOR"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    marcador_upper = df["MARCADOR"].astype(str).str.strip().str.upper()

    # Tenta pegar o número no início do marcador (ex: "42 - PORTAL...").
    # Quando não tem (ex: marcador é só "COLIGADA 18"), cai pro padrão
    # "COLIGADA <numero>" em qualquer parte do texto.
    coligada_inicio = marcador_upper.str.extract(r"^(\d+)", expand=False)
    coligada_fallback = marcador_upper.str.extract(r"COLIGADA\s+(\d+)", expand=False)

    df["COLIGADA"] = (
        coligada_inicio
        .fillna(coligada_fallback)
        .fillna(0)
        .astype(int)
    )

    df = df.drop(columns=["MARCADOR"])

    df["CPC"] = df["CONTATO"].apply(
        lambda x: "COM CPC" if str(x).strip().upper() == "SIM" else "SEM CPC"
    )
#documentação
    df["ATRASO"] = df.apply(calcular_atraso, axis=1)
    df = df[df["ATRASO"].notna()]
    df["ATRASO"] = df["ATRASO"].astype(int)

    df = df[df["ATIVO"].astype(str).str.strip().str.upper() == "SIM"]

    df["NUMERO"] = (
        df["NUMERO"]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
    )

    df = df[df["NUMERO"].str.len() == 11]
    df = df[df.duplicated(subset="NUMERO", keep=False) == False]

    return df


def enviar_bigquery(df):
    client = bigquery.Client(project=PROJETO)
    tabela_id = f"{PROJETO}.{DATASET}.{TABELA}"

    df = df.rename(columns={"CPF/CNPJ": "CPF_CNPJ"})

    job = client.load_table_from_dataframe(
        df,
        tabela_id,
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
    )

    job.result()

    logging.info(f"Tabela carregada com {len(df)} linhas em {tabela_id}")
    print(f"Ingestão concluída: {len(df)} linhas enviadas para {tabela_id}")


def ingerir_arquivo(buffer=None):
    """
    Se vier um buffer (ex: arquivo que o front mandou direto pro backend),
    usa ele direto e nem toca no bucket. Se não vier nada, mantém o
    comportamento antigo: baixa o Excel mais recente do bucket.
    """
    if buffer is None:
        logging.info("Baixando Excel mais recente do bucket...")
        buffer = baixar_excel_bucket()
    else:
        logging.info("Usando arquivo de pesquisa-cliente recebido do front...")

    logging.info("Aplicando filtros e fórmulas...")
    df = carregar_e_filtrar(buffer)

    for col in COLUNAS_ESPERADAS:
        if col not in df.columns:
            raise ValueError(f"Coluna obrigatória ausente após tratamento: {col}")

    antes = len(df)
    df = df.drop_duplicates()
    df = df[df["CLIENTE"].astype(str).str.strip() != ""]

    logging.info(f"{antes - len(df)} linhas removidas na limpeza final")

    enviar_bigquery(df)
    return df


if __name__ == "__main__":
    try:
        ingerir_arquivo()
    except Exception as e:
        logging.error(f"Erro na ingestão: {e}")
        print(f"Erro: {e}")
        raise