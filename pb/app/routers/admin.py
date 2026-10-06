"""
Rotas do painel admin. Registre este router no seu app/__init__.py ou main.py com:
    app.include_router(admin.router)
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException

from ..auth import UsuarioLogado
from ..middleware.permissions import admin_ou_rh, admin_rh_ou_vice, apenas_admin
from ..schemas import (
    RegistrarAdvertenciaRequest,
    RegistrarAdvertenciaResponse,
    AtivarRequest,
    AtivarResponse,
    RelatorioExportRequest,
)
from ..supabase_client import _get_supabase_client, buscar_flags_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/registrar", response_model=RegistrarAdvertenciaResponse)
def registrar_advertencia(
    dados: RegistrarAdvertenciaRequest,
    usuario: UsuarioLogado = Depends(admin_rh_ou_vice),
):
    """
    Registra advertência ou erro grave de um colaborador (por email).
    Erro grave vai pra tabela erros_graves; senão vai pra advertencias -
    mesmas tabelas que buscar_flags_admin() já lê.
    """
    sb = _get_supabase_client()
    tabela = "erros_graves" if dados.grave else "advertencias"
    sb.table(tabela).insert(
        {
            "email": dados.email,
            "motivo": dados.motivo,
            "registrado_por": usuario.email,
        }
    ).execute()

    flags = buscar_flags_admin(dados.email)
    return RegistrarAdvertenciaResponse(
        email=dados.email,
        tem_advertencia=flags["tem_advertencia"] or not dados.grave,
        tem_erro_grave=flags["tem_erro_grave"] or dados.grave,
        registrado_em=datetime.now(timezone.utc),
    )


@router.post("/ativar", response_model=AtivarResponse)
def ativar_bonus(
    dados: AtivarRequest,
    usuario: UsuarioLogado = Depends(admin_ou_rh),
):
    """Ativa o bônus de ativação (ciclo 1 ou 2) pra um colaborador - registra a flag no Supabase."""
    if dados.ciclo not in (1, 2):
        raise HTTPException(status_code=400, detail="Ciclo deve ser 1 ou 2.")

    sb = _get_supabase_client()
    sb.table("ativacoes").upsert(
        {
            "email": dados.email,
            "ciclo": dados.ciclo,
            "ativo": True,
            "ativado_por": usuario.email,
        },
        on_conflict="email,ciclo",
    ).execute()

    return AtivarResponse(
        email=dados.email,
        ativado_ciclo1=dados.ciclo == 1,
        ativado_ciclo2=dados.ciclo == 2,
    )


@router.post("/desativar", response_model=AtivarResponse)
def desativar_bonus(
    dados: AtivarRequest,
    usuario: UsuarioLogado = Depends(admin_ou_rh),
):
    """Desativa o bônus de ativação (ciclo 1 ou 2) pra um colaborador - zera a flag no Supabase."""
    if dados.ciclo not in (1, 2):
        raise HTTPException(status_code=400, detail="Ciclo deve ser 1 ou 2.")

    sb = _get_supabase_client()
    sb.table("ativacoes").upsert(
        {
            "email": dados.email,
            "ciclo": dados.ciclo,
            "ativo": False,
            "ativado_por": usuario.email,
        },
        on_conflict="email,ciclo",
    ).execute()

    return AtivarResponse(
        email=dados.email,
        ativado_ciclo1=False,
        ativado_ciclo2=False,
    )
@router.post("/relatorios")
def exportar_relatorio(
    filtro: RelatorioExportRequest,
    usuario: UsuarioLogado = Depends(admin_ou_rh),
):
    """
    Exporta dados de desempenho/RV do período pra CSV ou Sheets.
    Reaproveite aqui a lógica que já existe em rv_calculator.py / sheets_client.py.
    """
    # exemplo: dados = rv_calculator.calcular_periodo(filtro.periodo_inicio, filtro.periodo_fim, filtro.equipe)
    return {
        "mensagem": "Relatório gerado",
        "periodo": f"{filtro.periodo_inicio} a {filtro.periodo_fim}",
        "equipe": filtro.equipe or "todas",
    }