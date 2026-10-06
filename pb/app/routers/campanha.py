"""
Router do módulo de campanhas.

/ingerir recebe a pesquisa-cliente (arquivo) e joga pro BigQuery.
/processar recebe os templates em JSON e gera as listas/CSVs.
"""
import io
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ..auth import UsuarioLogado
from ..middleware.permissions import admin_rh_ou_vice
from app.schemas.campanha import ProcessarCampanhaBody
from app.services.campanha.ingestao import ingerir_arquivo
from app.services.campanha.saida_robo import gerar_saida
from app.services.campanha.transformacao import transformar

router = APIRouter(prefix="/api/campanha", tags=["campanha"])


@router.post("/ingerir")
async def ingerir_campanha(
    pesquisa_cliente: UploadFile = File(...),
    usuario: UsuarioLogado = Depends(admin_rh_ou_vice),
):
    try:
        buffer_pesquisa = io.BytesIO(await pesquisa_cliente.read())
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro lendo o arquivo enviado: {e}")

    try:
        df = ingerir_arquivo(buffer=buffer_pesquisa)
    except Exception as e:
        logging.error(f"Erro na ingestão da pesquisa-cliente: {e}")
        raise HTTPException(status_code=422, detail=f"Erro na ingestão da pesquisa-cliente: {e}")

    return {
        "linhas_ingeridas": len(df),
        "disparado_por": usuario.email,
    }


@router.post("/processar")
async def processar_campanha(
    body: ProcessarCampanhaBody,
    usuario: UsuarioLogado = Depends(admin_rh_ou_vice),
):
    templates = body.templates

    if body.carteira:
        prefixo = body.carteira.strip().upper() + "_"
        templates = [t for t in templates if t.template.upper().startswith(prefixo)]

    if not templates:
        return {
            "total_templates": 0,
            "resultados": [],
            "aviso": "Nenhum template encontrado pros filtros informados.",
        }

    resultados = []
    for template in templates:
        nome_template = template.template

        if not template.template_digisac:
            resultados.append({
                "template": nome_template,
                "status": "pulado",
                "motivo": "sem TEMPLATE_DIGISAC na planilha",
            })
            continue

        try:
            total_linhas = transformar(
                nome_template,
                credor=template.credor,
                atraso_dias_inicio=template.atraso_dias_inicio,
                atraso_dias_fim=template.atraso_dias_fim,
                filtro_cpc=template.filtro_cpc,
                marcador=template.marcador,
                coligada_inicio=template.coligada_inicio,
                coligada_fim=template.coligada_fim,
                coligada_lista=template.coligada_lista,
                defasagem_min=template.defasagem_min,
                valor_min=template.valor_min,
            )

            _, caminho_arquivo, url_bucket = gerar_saida(
                nome_tabela=nome_template,
                template_digisac=template.template_digisac,
                percentual=template.percentual,
            )

            resultados.append({
                "template": nome_template,
                "status": "ok",
                "linhas_filtradas": total_linhas,
                "url_csv": url_bucket,
            })

        except Exception as e:
            logging.error(f"Erro no template {nome_template}: {e}")
            resultados.append({
                "template": nome_template,
                "status": "erro",
                "motivo": str(e),
            })

    return {
        "total_templates": len(templates),
        "resultados": resultados,
        "disparado_por": usuario.email,
    }