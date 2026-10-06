"""
Rota de atendentes da tela Agora (Digisac) para o rv-backend.

Como encaixar no projeto:
1. Salve este arquivo ao lado do arquivo que já tem a rota /api/digisac/agora/resumo.
2. Ajuste os dois imports marcados com "AJUSTE" (mesmos da rota do resumo).
3. Registre o router no main.py, do mesmo jeito que o router do resumo:
       app.include_router(digisac_atendentes.router)
"""
import requests
from fastapi import APIRouter, Depends, HTTPException

from app.config import get_settings  # AJUSTE: caminho de onde vem o get_settings()
from app.auth import get_current_user  # AJUSTE: a MESMA dependência de login usada na rota do resumo

router = APIRouter(prefix="/api/digisac/agora", tags=["digisac"])


def _base_url(settings) -> str:
    """Garante o https:// mesmo se digisac_base_url vier só com o domínio."""
    base = settings.digisac_base_url.strip().rstrip("/")
    return base if base.startswith(("http://", "https://")) else f"https://{base}"


def buscar_atendentes_agora(settings) -> dict | list:
    """Chama o attendance-resume da Digisac e devolve o JSON como veio."""
    url = f"{_base_url(settings)}/api/v1/now/attendance-resume"
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {settings.digisac_token}"},
            timeout=30,
        )
    except requests.exceptions.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Falha de conexão com a Digisac: {exc}") from exc
        
    if resp.status_code != 200:
        # O front lê o campo "detail" e mostra na tela.
        raise HTTPException(
            status_code=502,
            detail=f"Digisac respondeu {resp.status_code} em attendance-resume: {resp.text[:200]}",
        )
    try:
        return resp.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="A Digisac devolveu uma resposta que não é JSON") from exc





@router.get("/atendentes")
def atendentes(settings=Depends(get_settings), _usuario=Depends(get_current_user)):
    return buscar_atendentes_agora(settings)