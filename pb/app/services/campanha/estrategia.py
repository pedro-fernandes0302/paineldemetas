import io
import json
import os
import re

import pandas as pd
from google.cloud import storage

PASTA_ESTRATEGIA = "estrategia/"

# Valores que significam "sem filtro de atraso" (pega geral / 100%)
VALORES_SEM_FAIXA = ["NAN", "", "-", "100", "100%", "1", "1.0", "GERAL"]


def carregar_config():
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def pegar_arquivo_mais_recente_bucket(prefixo=PASTA_ESTRATEGIA):
    config = carregar_config()
    storage_client = storage.Client(project=config["projeto"])
    blobs = list(storage_client.list_blobs(config["bucket"], prefix=prefixo))

    arquivos = [
        blob for blob in blobs
        if not blob.name.endswith("/")
        and blob.name.lower().endswith((".xlsx", ".xls"))
    ]

    if not arquivos:
        raise FileNotFoundError(
            f"Nenhum Excel encontrado no bucket '{config['bucket']}' "
            f"dentro da pasta '{prefixo}'."
        )

    arquivo_mais_recente = max(arquivos, key=lambda blob: blob.updated)
    print(f"Estratégia encontrada: gs://{config['bucket']}/{arquivo_mais_recente.name}")
    return arquivo_mais_recente


def baixar_excel_estrategia():
    blob = pegar_arquivo_mais_recente_bucket()

    # Recria o blob sem a generation "congelada" do list_blobs,
    # pra sempre baixar a versão mais recente e evitar 404 por
    # sobrescrita concorrente do arquivo no bucket.
    config = carregar_config()
    storage_client = storage.Client(project=config["projeto"])
    blob_atual = storage_client.bucket(blob.bucket.name).blob(blob.name)

    buffer = io.BytesIO(blob_atual.download_as_bytes())
    buffer.seek(0)
    return buffer


def normalizar(valor):
    return str(valor).strip().upper()


def normalizar_percentual(valor):
    texto = normalizar(valor)

    if texto in ["NAN", "", "-", "100", "100%", "1", "1.0"]:
        return 100

    texto = texto.replace("%", "").replace(",", ".").strip()

    try:
        numero = float(texto)
        return int(numero * 100) if numero <= 1 else int(numero)
    except Exception:
        return 100


def resolver_credor(carteira, config):
    """
    Retorna o nome real do credor para usar no filtro SQL.
    Primeiro tenta bater com o mapa do config; se não achar, usa a carteira como está.
    """
    carteira_upper = normalizar(carteira)
    credores = {k.upper(): v for k, v in config.get("credores", {}).items()}
    return credores.get(carteira_upper, carteira)


def expandir_faixa_dias(faixa_raw):
    """
    Converte QUALQUER faixa de atraso (em dias ou anos, com a granularidade
    que a planilha pedir) direto num intervalo numérico de dias:

        "2 A 5 ANOS"        -> (730, 1825)
        "0 A 365 DIAS"      -> (0, 365)
        "361 A 720 DIAS"    -> (361, 720)
        "ACIMA DE 7 ANOS"   -> (2555, None)
        "ACIMA DE 720 DIAS" -> (720, None)

    Não depende mais de bater com uma lista fixa de faixas — funciona pra
    qualquer intervalo que a estratégia pedir. Se a faixa for 100% / GERAL /
    vazia -> (None, None), sem filtro de atraso.

    Retorna tupla (dias_inicio, dias_fim). dias_fim None = sem teto (>=).
    """
    texto = normalizar(faixa_raw)

    if texto in VALORES_SEM_FAIXA:
        return None, None

    multiplicador = 365 if "ANO" in texto else 1
    numeros = [int(n) for n in re.findall(r"\d+", texto)]

    if not numeros:
        # Não é uma faixa numérica (provavelmente é um marcador tipo "EXTRAJUDICIAL")
        return None, None

    if "ACIMA" in texto:
        return numeros[0] * multiplicador, None

    if len(numeros) >= 2:
        return numeros[0] * multiplicador, numeros[1] * multiplicador

    # Só um número e não é "ACIMA" -> trata como piso, sem teto
    return numeros[0] * multiplicador, None


def eh_marcador(faixa_raw):
    """
    Uma faixa é tratada como marcador (ex: "EXTRAJUDICIAL", "AJUIZAMENTO")
    quando não é 100%/GERAL/vazia e não contém nenhum número.
    """
    texto = normalizar(faixa_raw)
    if texto in VALORES_SEM_FAIXA:
        return False
    return not re.search(r"\d", texto)


def montar_chave(carteira, faixa, tipo, defasagem_min=None, valor_min=None):
    """
    Monta o nome único do template para uso como nome de tabela no BigQuery.

    Quando DEFASAGEM/VALOR_MINIMO estão preenchidos, entram no nome também
    -- senão duas linhas que só se diferenciam por essas colunas (mesma
    CARTEIRA+FAIXA_ATRASO+TIPO) geram a MESMA chave e uma sobrescreve a
    tabela da outra no BigQuery.
    """
    carteira = normalizar(carteira).replace(" ", "_")
    tipo = normalizar(tipo).replace(" ", "")
    faixa_norm = normalizar(faixa)

    eh_geral = faixa_norm in ["NAN", "", "-", "100", "100%", "1", "1.0"]

    if eh_geral:
        base = f"{carteira}_{tipo}"
    elif "," in faixa_norm:
        # Lista de coligadas (tem vírgula) -> nome curto, já que BigQuery não aceita
        # vírgula em ID de tabela e a lista pode ser grande demais pro nome.
        qtd = len(re.findall(r"\d+", faixa_norm))
        base = f"{carteira}_COLIGADAS{qtd}_{tipo}"
    else:
        faixa_limpa = (
            faixa_norm
            .replace(" A ", "A")
            .replace(" ANOS", "")
            .replace(" DE ", "")
            .replace(" DIAS", "")
            .replace(" ", "")
        )
        base = f"{carteira}_{faixa_limpa}_{tipo}"

    sufixos = []
    if defasagem_min is not None:
        sufixos.append(f"DEF{int(defasagem_min)}")
    if valor_min is not None:
        sufixos.append(f"VAL{int(valor_min)}")

    if sufixos:
        base = f"{base}_" + "_".join(sufixos)

    return base


def extrair_coligadas(valor):
    """
    Extrai a info de coligada da faixa (só usado pra carteira CARTEIRA_A). Aceita dois formatos:

    - LISTA: números separados por vírgula, ex: "51, 24, 21, 53 e 68"
      -> filtro vira COLIGADA IN (51, 24, 21, 53, 68)
    - INTERVALO: dois números com "A" no meio, ex: "51 A 68"
      -> filtro vira COLIGADA BETWEEN 51 AND 68

    Retorna tupla (inicio, fim, lista):
        - intervalo encontrado  -> (inicio, fim, None)
        - lista encontrada      -> (None, None, [51, 24, 21, ...])
        - nada encontrado       -> (None, None, None)
    """
    texto = normalizar(valor)

    if "," in texto:
        numeros = [int(n) for n in re.findall(r"\d+", texto)]
        return None, None, numeros if numeros else None

    numeros = re.findall(r"\d+", texto)
    if len(numeros) >= 2:
        return int(numeros[0]), int(numeros[1]), None

    return None, None, None


def pegar_percentual_linha(linha):
    for coluna in ["%", "PERCENTUAL", "PORCENTAGEM"]:
        if coluna in linha.index:
            return normalizar_percentual(linha[coluna])
    return 100


def pegar_template_digisac_linha(linha):
    coluna = "TEMPLATE_DIGISAC"
    if coluna not in linha.index:
        return ""
    valor = str(linha[coluna]).strip()
    if valor.upper() in ["NAN", "", "-"]:
        return ""
    return valor


def pegar_defasagem_linha(linha):
    """
    Lê a coluna DEFASAGEM da planilha (opcional). Quando preenchida, filtra
    a coluna DEFASAGEM (campo próprio da base, diferente de ATRASO) > esse
    valor, sem teto -- aplicado JUNTO com o filtro de FAIXA_ATRASO, não
    sobrescreve nada.

    Retorna int ou None (coluna ausente, vazia ou valor inválido).
    """
    coluna = "DEFASAGEM"
    if coluna not in linha.index:
        return None

    valor = linha[coluna]

    # NaN do pandas (célula vazia lida como float)
    if isinstance(valor, float) and pd.isna(valor):
        return None

    # Já vem numérico (int/float) direto do Excel: usa direto, sem
    # passar pelo parser de texto BR (que quebraria "30.0" -> "300")
    if isinstance(valor, (int, float)):
        return int(valor)

    valor = str(valor).strip()
    if valor.upper() in ["NAN", "", "-"]:
        return None

    # Só aplica a troca de ponto/vírgula (formato BR) quando é texto de
    # verdade digitado na planilha (ex: "1.825" ou "1825,0")
    texto = valor.replace(".", "").replace(",", ".").strip()
    try:
        return int(float(texto))
    except Exception:
        print(f"[ATENCAO] DEFASAGEM '{valor}' inválida, ignorando coluna nessa linha")
        return None


def pegar_valor_minimo_linha(linha):
    """
    Lê a coluna VALOR_MINIMO da planilha (opcional). Quando preenchida,
    filtra VALOR_ATUALIZADO >= esse valor -- aplicado JUNTO com os demais
    filtros da linha (FAIXA_ATRASO, DEFASAGEM etc.), não sobrescreve nada.

    Aceita tanto número puro do Excel (7000, 7000.0) quanto texto no
    formato BR digitado na planilha ("7.000,00").

    Retorna float ou None (coluna ausente, vazia ou valor inválido).
    """
    coluna = "VALOR_MINIMO"
    if coluna not in linha.index:
        return None

    valor = linha[coluna]

    if isinstance(valor, float) and pd.isna(valor):
        return None

    if isinstance(valor, (int, float)):
        return float(valor)

    valor = str(valor).strip()
    if valor.upper() in ["NAN", "", "-"]:
        return None

    texto = valor.replace("R$", "").replace(" ", "")
    texto = texto.replace(".", "").replace(",", ".").strip()
    try:
        return float(texto)
    except Exception:
        print(f"[ATENCAO] VALOR_MINIMO '{valor}' inválido, ignorando coluna nessa linha")
        return None


def ler_estrategia(buffer=None):
    """
    Se vier um buffer (ex: planilha que o front mandou direto pro backend),
    lê ela direto e nem toca no bucket. Se não vier nada, mantém o
    comportamento antigo: baixa a estratégia mais recente do bucket.
    """
    if buffer is None:
        buffer = baixar_excel_estrategia()
    df = pd.read_excel(buffer)

    colunas_obrigatorias = ["CARTEIRA", "FAIXA_ATRASO", "TIPO"]
    faltando = [col for col in colunas_obrigatorias if col not in df.columns]
    if faltando:
        raise ValueError(
            f"Colunas faltando na estratégia: {faltando}. "
            f"Colunas encontradas: {list(df.columns)}"
        )

    config = carregar_config()
    templates = []

    for _, linha in df.iterrows():
        carteira_raw = str(linha["CARTEIRA"]).strip()
        faixa_raw = str(linha["FAIXA_ATRASO"]).strip()
        tipo_raw = str(linha["TIPO"]).strip()

        if normalizar(carteira_raw) in ["NAN", ""]:
            continue

        carteira_upper = normalizar(carteira_raw)
        credor_real = resolver_credor(carteira_raw, config)

        # Expande faixa de atraso: se tiver número, vira intervalo de dias;
        # se não tiver número (e não for GERAL/100%), é tratado como marcador.
        marcador = normalizar(faixa_raw) if eh_marcador(faixa_raw) else None
        atraso_dias_inicio, atraso_dias_fim = expandir_faixa_dias(faixa_raw)

        # DEFASAGEM (coluna opcional): filtra o campo DEFASAGEM de verdade
        # (é uma coluna própria da base, diferente de ATRASO). Aplica JUNTO
        # com o filtro de FAIXA_ATRASO, não sobrescreve nada.
        defasagem_min = pegar_defasagem_linha(linha)

        # VALOR_MINIMO (coluna opcional): filtra VALOR_ATUALIZADO >= valor,
        # também em paralelo com os outros filtros.
        valor_min = pegar_valor_minimo_linha(linha)

        # Monta filtro de CPC (aceita "CPC", "SEMCPC", "COM CPC", "SEM CPC" etc.)
        tipo_norm = normalizar(tipo_raw)
        if tipo_norm == "GERAL":
            filtro_cpc = None
        elif "SEM" in tipo_norm:
            filtro_cpc = "SEM CPC"
        elif "CPC" in tipo_norm:
            filtro_cpc = "COM CPC"
        else:
            filtro_cpc = None

        # CARTEIRA_A: FAIXA_ATRASO é usado pra coligada (intervalo OU lista), não pra dias de
        # atraso. Extrai coligada e, se encontrou algo, zera atraso/marcador pra não
        # aplicar os dois filtros ao mesmo tempo por engano.
        coligada_inicio, coligada_fim, coligada_lista = None, None, None
        if carteira_upper == "CARTEIRA_A":
            coligada_inicio, coligada_fim, coligada_lista = extrair_coligadas(faixa_raw)
            if coligada_inicio is not None or coligada_lista is not None:
                atraso_dias_inicio, atraso_dias_fim = None, None
                marcador = None

        chave = montar_chave(carteira_raw, faixa_raw, tipo_raw, defasagem_min, valor_min)
        percentual = pegar_percentual_linha(linha)
        template_digisac = pegar_template_digisac_linha(linha)

        item = {
            "template": chave,
            "credor": credor_real,
            "atraso_dias_inicio": atraso_dias_inicio,  # int ou None
            "atraso_dias_fim": atraso_dias_fim,        # int ou None (None = sem teto)
            "filtro_cpc": filtro_cpc,           # "COM CPC", "SEM CPC" ou None
            "marcador": marcador,               # ex: "EXTRAJUDICIAL", "AJUIZAMENTO" ou None
            "percentual": percentual,
            "template_digisac": template_digisac,
            "coligada_inicio": coligada_inicio,  # int ou None (apenas CARTEIRA_A, modo intervalo)
            "coligada_fim": coligada_fim,        # int ou None (apenas CARTEIRA_A, modo intervalo)
            "coligada_lista": coligada_lista,    # list[int] ou None (apenas CARTEIRA_A, modo lista)
            "defasagem_min": defasagem_min,      # int ou None (filtra DEFASAGEM > valor)
            "valor_min": valor_min,              # float ou None (filtra VALOR_ATUALIZADO >= valor)
        }

        templates.append(item)
        print(
            f"Template lido: {chave} | credor={credor_real} | "
            f"atraso={atraso_dias_inicio}-{atraso_dias_fim} | cpc={filtro_cpc} | "
            f"defasagem>{defasagem_min} | valor>={valor_min}"
        )

    print(f"\nTotal de templates carregados da estratégia: {len(templates)}")
    return templates


if __name__ == "__main__":
    for t in ler_estrategia():
        print(t)
