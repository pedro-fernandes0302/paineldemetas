#$import obrigatorios
import logging
import os
from datetime import datetime, timedelta
import json
import pandas as pd
import requests
from google.cloud import bigquery
from google.cloud import storage

from app.config import get_settings

logging.basicConfig(
    filename="pipeline.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

settings = get_settings()

PROJETO = os.getenv("GCP_PROJECT_ID", "seu-projeto-gcp")
DATASET = os.getenv("BQ_DATASET_CAMPANHA", "cobranca")
BUCKET = os.getenv("GCS_BUCKET", "seu-bucket")
PASTA_SAIDA_LOCAL = "saida_local/"   # pasta local temporaria (Colab/Cloud Run)
PASTA_SAIDA_BUCKET = "saida/"        # prefixo dentro do bucket (GCS_BUCKET)

# token e URL da Digisac agora vêm do .env / app/config.py (mesma fonte que
# o digisac.py já usa), em vez de ficar hardcoded aqui no arquivo
DIGISAC_BASE_URL = settings.digisac_base_url
DIGISAC_HEADERS = {"Authorization": f"Bearer {settings.digisac_token}"}

# possiveis nomes de coluna pra cliente/telefone nas tabelas do BigQuery,
# em ordem de prioridade (a primeira que existir na tabela e usada)
COLUNAS_CLIENTE_POSSIVEIS = ["CLIENTE", "Nome", "nome_cliente","nomecliente"]
COLUNAS_TELEFONE_POSSIVEIS = ["MAIS_55", "Telefone", "telefone"]

# nomes fixos das colunas de saida do CSV -- essas 2 SEMPRE vem primeiro,
# nessa ordem, com esse nome exato (e' o que o Digisac espera pro
# nome/telefone de contato), independente do que o template pedir.
# O "nome do cliente de novo" (2a vez, dentro do corpo da mensagem) NAO e'
# mais fixo aqui -- ele sai como uma variavel extra normal la embaixo, com
# o nome exato que o template usa pra essa variavel (nome_cliente,
# NOMECLIENTE, etc.), porque cada template pode nomear ela diferente.
COLUNAS_FIXAS = ["Nome", "Telefone"]

# variaveis do template que nao batem literalmente com o nome da coluna na
# tabela do BigQuery -> mapeia pro nome real da coluna
# IMPORTANTE: todas as chaves aqui tem que estar em minusculo, porque o
# lookup sempre e feito com var.lower() (dict.get e case-sensitive, entao
# uma chave "NOMEALUNO" em maiusculo NUNCA batia com "nomealuno" antes)
ALIAS_VARIAVEIS = {
    "nome_credor": "CREDOR",
    "nomecredor": "CREDOR",
    "credor": "CREDOR",
    "nomealuno": "CLIENTE",
    "nome_cliente": "CLIENTE",
    "cliente": "CLIENTE",
    "nomecliente": "CLIENTE",
    "aluno_cliente": "CLIENTE",
    "valor_atualizado": "VALOR_ATUALIZADO",
    "valoratualizado": "VALOR_ATUALIZADO",
    "valor_quitacao": "VALOR_QUITACAO",
    "valorquitacao": "VALOR_QUITACAO",
}


def gerar_variaveis_computadas():
    """Variaveis do template que nao existem na tabela do BigQuery, mas dao
    pra calcular na hora de gerar o CSV (nao dependem de nenhuma coluna)."""
    amanha = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    return {
        "data_hoje": amanha,  # no template "data_hoje" na real e o dia seguinte (prazo)
    }


def buscar_variaveis_template(nome_template):
    """Busca o template pelo name/internalName na Digisac e retorna a lista
    de variaveis (params) do BODY. Ex: ['nome_cliente', 'valor_desconto']"""
    page = 1
    per_page = 40
    ids_vistos = set()

    while True:
        resp = requests.get(
            f"{DIGISAC_BASE_URL}/whatsapp-business-templates",
            headers=DIGISAC_HEADERS,
            params={"perPage": per_page, "page": page},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        itens = data.get("data", data) if isinstance(data, dict) else data
        if not itens:
            break

        ids_pagina = {item.get("id") for item in itens}
        if ids_pagina and ids_pagina.issubset(ids_vistos):
            break
        ids_vistos.update(ids_pagina)

        for t in itens:
            if t.get("name") == nome_template or t.get("internalName") == nome_template:
                for comp in t.get("components", []):
                    if comp.get("type") == "BODY":
                        return comp.get("params") or []
                return []

        if len(itens) < per_page:
            break
        page += 1

    logging.warning(f"Template '{nome_template}' nao encontrado na Digisac")
    return []


def enviar_arquivo_para_bucket(caminho_local, nome_bucket, caminho_destino):
    """Sobe um arquivo local pro GCS e retorna um dict com info do blob,
    incluindo o link publico do console (webViewLink) e o nome/id do objeto."""
    client = storage.Client(project=PROJETO)
    bucket = client.bucket(nome_bucket)

    nome_base = os.path.basename(caminho_local)
    blob_path = os.path.join(caminho_destino, nome_base).replace("\\", "/")
    blob = bucket.blob(blob_path)

    blob.upload_from_filename(caminho_local)

    web_view_link = (
        f"https://console.cloud.google.com/storage/browser/_details/"
        f"{nome_bucket}/{blob_path}"
    )

    return {
        "id": blob_path,
        "webViewLink": web_view_link,
        "gs_uri": f"gs://{nome_bucket}/{blob_path}",
    }


def _achar_coluna(df, candidatas):
    """Retorna o nome da primeira coluna de 'candidatas' que existe no df
    (comparando sem diferenciar maiusculo/minusculo), ou None se nao achar."""
    colunas_lower = {c.lower(): c for c in df.columns}
    for candidata in candidatas:
        if candidata.lower() in colunas_lower:
            return colunas_lower[candidata.lower()]
    return None
def carregar_desconto():
    """Baixa e lê o desconto.json do bucket (mesmo padrão do config.json)."""
    storage_client = storage.Client(project=PROJETO)
    blob = storage_client.bucket(BUCKET).blob("desconto.json")
    conteudo = blob.download_as_text()
    return json.loads(conteudo)["desconto"] / 100


def carregar_honorarios_por_contrato():
    """
    Baixa o mesmo Excel de clientes usado no ingestao.py (aba 'Cobrança') e monta
    um lookup CONTRATO -> TOTAL COM HO, pra calcular valor_atualizado/valor_quitacao
    na hora de gerar o CSV de saída.
    """
    from .ingestao import baixar_excel_bucket  # reaproveita a função que já existe

    buffer = baixar_excel_bucket()
    cobranca = pd.read_excel(buffer, sheet_name="Cobrança")

    cobranca["CONTRATO"] = cobranca["CONTRATO"].astype(str).str.strip()
    cobranca["TOTAL COM HO"] = pd.to_numeric(cobranca["TOTAL COM HO"], errors="coerce")

    return cobranca.set_index("CONTRATO")["TOTAL COM HO"].to_dict()

def gerar_saida(nome_tabela, template_digisac=None, percentual=100):
    """
    nome_tabela: chave da estrategia.py, usada pra achar a tabela no BigQuery
                 (dados_tratados_{nome_tabela})
    template_digisac: nome do template la na Digisac (campo TEMPLATE_DIGISAC
                       da planilha), usado pra buscar variaveis extras alem
                       das 3 fixas (ex: data_hoje, nome_credor).

    A saida SEMPRE comeca com essas 2 colunas fixas, nessa ordem e com esse
    nome exato (e' o padrao que o Digisac espera pro contato):
      - Nome
      - Telefone

    Depois dessas 2, TODAS as outras variaveis que o template pedir (nome do
    cliente de novo dentro do corpo, data_hoje, nome_credor, valor_atualizado,
    valor_quitacao...) sao adicionadas como colunas extras, na ordem em que
    aparecem no template, e com o NOME EXATO que o template usa pra cada
    variavel -- sem forcar maiusculo nem trocar underscore. Se o template
    pede "nome_cliente" a coluna sai "nome_cliente"; se pede "NOMECLIENTE"
    sai "NOMECLIENTE". O Digisac casa a variavel pelo nome exato, entao
    mudar a caixa quebra o envio.
    """
    client = bigquery.Client(project=PROJETO)

    query = f"""
        SELECT *
        FROM `{PROJETO}.{DATASET}.dados_tratados_{nome_tabela}`
    """

    df = client.query(query).to_dataframe()

    if percentual < 100 and len(df) > 0:
        df = df.sample(frac=percentual / 100).reset_index(drop=True)

    col_cliente = _achar_coluna(df, COLUNAS_CLIENTE_POSSIVEIS)
    col_telefone = _achar_coluna(df, COLUNAS_TELEFONE_POSSIVEIS)

    if not col_cliente:
        raise ValueError(
            f"Nao encontrei coluna de cliente (tentei {COLUNAS_CLIENTE_POSSIVEIS}) "
            f"na tabela dados_tratados_{nome_tabela}"
        )
    if not col_telefone:
        raise ValueError(
            f"Nao encontrei coluna de telefone (tentei {COLUNAS_TELEFONE_POSSIVEIS}) "
            f"na tabela dados_tratados_{nome_tabela}"
        )

    # 1) monta as 2 colunas fixas primeiro -- essas nunca mudam de nome nem de ordem
    df_saida = pd.DataFrame()
    df_saida["Nome"] = df[col_cliente]
    df_saida["Telefone"] = df[col_telefone]

    # 2) busca variaveis extras do template (se tiver template informado) e
    #    adiciona como colunas depois das 2 fixas. Isso inclui o nome do
    #    cliente de novo (ex: nome_cliente, NOMECLIENTE) quando o template
    #    pedir -- so' "nome" e "telefone" ficam de fora, porque ja' viram
    #    as colunas fixas Nome/Telefone acima.
    variaveis_nao_encontradas = []
    if template_digisac:
        variaveis = buscar_variaveis_template(template_digisac)
        computadas = gerar_variaveis_computadas()

        for var in variaveis:
            if var.lower() in ("nome", "telefone"):
                continue  # ja cobertos pelas 2 colunas fixas acima

            nome_coluna_extra = var  # nome EXATO da variavel, sem .upper()
            if nome_coluna_extra in df_saida.columns:
                continue  # ja adicionada (evita duplicar se o template repetir a variavel)

            # 2a) variavel computada (ex: data_hoje = amanha)
            if var.lower() in computadas:
                df_saida[nome_coluna_extra] = computadas[var.lower()]
                continue
            # 2b) variavel de nome do cliente de novo, com outro nome
            #     (cliente, nome_cliente, nomecliente, nomealuno,
            #     aluno_cliente...) -> reusa a mesma coluna de cliente que
            #     ja achamos pro Nome fixo. Lista tem que bater com as
            #     variantes de cliente no ALIAS_VARIAVEIS la em cima, senao
            #     essas variantes caem no fallback fixo (2c/2d) e podem nao
            #     achar a coluna se o nome real no BigQuery for diferente
            #     de "CLIENTE".
            VARIANTES_CLIENTE = ("cliente", "nome_cliente", "nomecliente", "nomealuno", "aluno_cliente")
            if var.lower() in VARIANTES_CLIENTE:
                df_saida[nome_coluna_extra] = df[col_cliente]
                continue

            # 2c) tenta achar coluna com o MESMO NOME da variavel
            match = next((c for c in df.columns if c.lower() == var.lower()), None)

            # 2d) se nao achou, tenta pelo alias (ex: nome_credor -> CREDOR)
            if not match:
                nome_coluna_alvo = ALIAS_VARIAVEIS.get(var.lower())
                if nome_coluna_alvo:
                    match = next(
                        (c for c in df.columns if c.lower() == nome_coluna_alvo.lower()),
                        None,
                    )

            if match:
                df_saida[nome_coluna_extra] = df[match]
            else:
                variaveis_nao_encontradas.append(var)
                logging.warning(
                    f"Variavel '{var}' do template '{template_digisac}' nao encontrada "
                    f"na tabela dados_tratados_{nome_tabela} - confere se precisa "
                    f"criar essa coluna no BigQuery"
                )

    if variaveis_nao_encontradas:
        print(
            f"[ATENCAO] Tabela '{nome_tabela}' / template '{template_digisac}': "
            f"faltam as variaveis {variaveis_nao_encontradas} -- o CSV vai sair "
            f"sem esses dados, confere no BigQuery antes de disparar."
        )

    agora = datetime.now().strftime("%d-%m-%Y_%H-%M-%S")
    nome_base = f"saida_robo_{nome_tabela}_{agora}.csv"

    os.makedirs(PASTA_SAIDA_LOCAL, exist_ok=True)
    nome_arquivo = os.path.join(PASTA_SAIDA_LOCAL, nome_base)

    df_saida.to_csv(
        nome_arquivo,
        index=False,
        sep=";",
        encoding="utf-8-sig"
    )

    nome_bucket = BUCKET
    caminho_destino = PASTA_SAIDA_BUCKET

    resultado_upload = enviar_arquivo_para_bucket(
        nome_arquivo,
        nome_bucket,
        caminho_destino
    )
    url_bucket = resultado_upload.get("webViewLink", resultado_upload.get("id"))

    logging.info(
        f"Arquivo CSV gerado: {nome_arquivo} com {len(df_saida)} linhas, "
        f"colunas: {list(df_saida.columns)}"
    )
    print(f"Arquivo CSV gerado: {nome_arquivo} com {len(df_saida)} linhas!")

    return df_saida, nome_arquivo, url_bucket


def rodar_pipeline():
    from .estrategia import ler_estrategia

    itens = ler_estrategia()
    resultados = []

    for item in itens:
        if not item["template_digisac"]:
            logging.info(
                f"Template '{item['template']}' sem TEMPLATE_DIGISAC preenchido "
                f"na planilha - CSV vai sair so com as 3 colunas fixas"
            )

        try:
            df, arquivo, url = gerar_saida(
                nome_tabela=item["template"],
                template_digisac=item.get("template_digisac"),
                percentual=item["percentual"],
            )
            resultados.append((item["template"], arquivo, url))
        except Exception as e:
            logging.error(f"Erro gerando saida pro template '{item['template']}': {e}")
            print(f"Erro no template '{item['template']}': {e}")

    return resultados


if __name__ == "__main__":
    rodar_pipeline()