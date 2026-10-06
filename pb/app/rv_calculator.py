"""
Motor de cálculo da Remuneração Variável (RV).
Baseado em uma planilha de política de RV (valores aqui são ilustrativos).
"""
from typing import Optional
from dataclasses import dataclass


@dataclass
class MetricasRV:
    meta_individual_pct: Optional[float] = None
    meta_subequipe_pct: Optional[float] = None
    meta_geral_time_pct: Optional[float] = None
    tempo_medio_atendimento_min: Optional[float] = None
    primeira_resposta_min: Optional[float] = None
    nps_pct: Optional[float] = None
    novos_cpcs: int = 0
    registro_sistema_pct: Optional[float] = None
    avaliacoes_google: Optional[int] = None
    tem_erro_grave: bool = False
    tem_advertencia: bool = False
    ativado_ciclo1: bool = False
    ativado_ciclo2: bool = False
    cargo: str = "operador"
    semanas_batidas: int = 0


@dataclass
class ResultadoRV:
    rv_total: float
    rv_individual: float
    rv_coletivo: float
    bonus_qualidade: float
    bonus_consistencia: float
    bonus_ativado: float
    semana1_rv: float
    semana2_rv: float
    semana3_rv: float
    semana4_rv: float
    subequipe_rv: float
    geral_time_rv: float
    qualidade_tempo_atendimento: float
    qualidade_primeira_resposta: float
    qualidade_nps: float
    qualidade_cpcs: float
    qualidade_registro: float
    qualidade_google: float
    qualidade_zero_erros: float
    perdeu_bonus_zero_erros: bool
    perdeu_bonus_qualidade_por_erro: bool
    faixa_individual: str
    faixa_subequipe: str
    faixa_geral_time: str


TABELA_INDIVIDUAL_OPERADOR = {
    "abaixo_95": 0,
    "95_99": 10,
    "100_119": 20,
    "120_149": 30,
    "150_199": 40,
    "200_ou_mais": 40,
}

TABELA_INDIVIDUAL_VICE_LIDER = {
    "abaixo_95": 0,
    "95_99": 25,
    "100_119": 50,
    "120_149": 50,
    "150_199": 75,
    "200_ou_mais": 75,
}

TABELA_COLETIVO = {
    "abaixo_95": 0,
    "95_99": 0,
    "100_119": 20,
    "120_149": 20,
    "150_199": 40,
    "200_ou_mais": 40,
}


def _faixa_por_percentual(pct: Optional[float]) -> str:
    if pct is None:
        return "abaixo_95"
    if pct < 95:
        return "abaixo_95"
    elif pct < 100:
        return "95_99"
    elif pct < 120:
        return "100_119"
    elif pct < 150:
        return "120_149"
    elif pct < 200:
        return "150_199"
    else:
        return "200_ou_mais"


def _get_tabela_individual(cargo: str) -> dict:
    # CORREÇÃO: trata cargo None ou vazio como "operador"
    if not cargo:
        return TABELA_INDIVIDUAL_OPERADOR
    if cargo.lower() in ["vice_lider", "vice-lider", "vice lider", "lider"]:
        return TABELA_INDIVIDUAL_VICE_LIDER
    return TABELA_INDIVIDUAL_OPERADOR


def calcular_rv(m: MetricasRV) -> ResultadoRV:
    tabela_ind = _get_tabela_individual(m.cargo)
    faixa_ind = _faixa_por_percentual(m.meta_individual_pct)
    rv_individual = tabela_ind.get(faixa_ind, 0)
    rv_por_semana = rv_individual / 4 if rv_individual > 0 else 0

    faixa_sub = _faixa_por_percentual(m.meta_subequipe_pct)
    faixa_geral = _faixa_por_percentual(m.meta_geral_time_pct)
    subequipe_rv = TABELA_COLETIVO.get(faixa_sub, 0)
    geral_time_rv = TABELA_COLETIVO.get(faixa_geral, 0)
    rv_coletivo = subequipe_rv + geral_time_rv

    q_tempo = 10.0 if (m.tempo_medio_atendimento_min is not None and m.tempo_medio_atendimento_min < 60) else 0.0
    q_resposta = 10.0 if (m.primeira_resposta_min is not None and m.primeira_resposta_min < 30) else 0.0
    q_nps = 10.0 if (m.nps_pct is not None and m.nps_pct > 80) else 0.0
    q_cpcs = 10.0 if (m.novos_cpcs is not None and m.novos_cpcs > 100) else 0.0
    q_registro = 10.0 if (m.registro_sistema_pct is not None and m.registro_sistema_pct >= 95) else 0.0
    q_google = 5.0 if (m.avaliacoes_google is not None and m.avaliacoes_google >= 2) else 0.0

    tem_problema = m.tem_erro_grave or m.tem_advertencia
    q_zero_erros = 5.0 if not tem_problema else 0.0

    bonus_qualidade = q_tempo + q_resposta + q_nps + q_cpcs + q_registro + q_google + q_zero_erros

    perdeu_tudo_qualidade = m.tem_erro_grave
    if perdeu_tudo_qualidade:
        bonus_qualidade = 0.0

    if m.semanas_batidas >= 4:
        bonus_consistencia = 25.0
    elif m.semanas_batidas >= 3:
        bonus_consistencia = 15.0
    else:
        bonus_consistencia = 0.0

    bonus_ativado = 0.0
    if m.ativado_ciclo1:
        bonus_ativado += 25.0
    if m.ativado_ciclo2:
        bonus_ativado += 25.0

    rv_total = rv_individual + rv_coletivo + bonus_qualidade + bonus_consistencia + bonus_ativado

    return ResultadoRV(
        rv_total=round(rv_total, 2),
        rv_individual=round(rv_individual, 2),
        rv_coletivo=round(rv_coletivo, 2),
        bonus_qualidade=round(bonus_qualidade, 2),
        bonus_consistencia=round(bonus_consistencia, 2),
        bonus_ativado=round(bonus_ativado, 2),
        semana1_rv=round(rv_por_semana, 2),
        semana2_rv=round(rv_por_semana, 2),
        semana3_rv=round(rv_por_semana, 2),
        semana4_rv=round(rv_por_semana, 2),
        subequipe_rv=round(subequipe_rv, 2),
        geral_time_rv=round(geral_time_rv, 2),
        qualidade_tempo_atendimento=round(q_tempo, 2),
        qualidade_primeira_resposta=round(q_resposta, 2),
        qualidade_nps=round(q_nps, 2),
        qualidade_cpcs=round(q_cpcs, 2),
        qualidade_registro=round(q_registro, 2),
        qualidade_google=round(q_google, 2),
        qualidade_zero_erros=round(q_zero_erros, 2),
        perdeu_bonus_zero_erros=tem_problema,
        perdeu_bonus_qualidade_por_erro=perdeu_tudo_qualidade,
        faixa_individual=faixa_ind,
        faixa_subequipe=faixa_sub,
        faixa_geral_time=faixa_geral,
    )


def calcular_rv_completo(
    nome: str,
    email: str,
    cargo: str,
    equipe: str,
    digisac_user_id: str,
    metas_sheets: dict,
    metricas_digisac: dict,
    flags_admin: dict,
) -> dict:
    # CORREÇÃO: trata cargo None ou vazio como "operador"
    cargo_normalizado = cargo if cargo else "operador"

    m = MetricasRV(
        meta_individual_pct=metas_sheets.get("meta_individual"),
        meta_subequipe_pct=metas_sheets.get("meta_subequipe"),
        meta_geral_time_pct=metas_sheets.get("meta_geral_time"),
        tempo_medio_atendimento_min=metricas_digisac.get("tempo_medio_atendimento_min"),
        primeira_resposta_min=metricas_digisac.get("primeira_resposta_min"),
        nps_pct=metricas_digisac.get("nps_pct"),
        novos_cpcs=metricas_digisac.get("novos_cpcs"),
        registro_sistema_pct=metricas_digisac.get("registro_sistema_pct"),
        avaliacoes_google=metricas_digisac.get("avaliacoes_google"),
        tem_erro_grave=flags_admin.get("tem_erro_grave", False),
        tem_advertencia=flags_admin.get("tem_advertencia", False),
        ativado_ciclo1=flags_admin.get("ativado_ciclo1", False),
        ativado_ciclo2=flags_admin.get("ativado_ciclo2", False),
        cargo=cargo_normalizado,
        semanas_batidas=metas_sheets.get("semanas_batidas", 0),
    )

    r = calcular_rv(m)

    return {
        "nome": nome,
        "cargo": cargo_normalizado,
        "equipe": equipe,
        "rv": {
            "total": r.rv_total,
            "individual": r.rv_individual,
            "coletivo": r.rv_coletivo,
            "bonus_qualidade": r.bonus_qualidade,
            "bonus_consistencia": r.bonus_consistencia,
            "bonus_ativado": r.bonus_ativado,
        },
        "breakdown": {
            "individual_por_semana": {
                "semana1": r.semana1_rv,
                "semana2": r.semana2_rv,
                "semana3": r.semana3_rv,
                "semana4": r.semana4_rv,
            },
            "coletivo": {
                "subequipe": r.subequipe_rv,
                "geral_time": r.geral_time_rv,
            },
            "qualidade": {
                "tempo_atendimento": r.qualidade_tempo_atendimento,
                "primeira_resposta": r.qualidade_primeira_resposta,
                "nps": r.qualidade_nps,
                "novos_cpcs": r.qualidade_cpcs,
                "registro_sistema": r.qualidade_registro,
                "avaliacao_google": r.qualidade_google,
                "zero_erros": r.qualidade_zero_erros,
            },
        },
        "flags": {
            "tem_erro_grave": m.tem_erro_grave,
            "tem_advertencia": m.tem_advertencia,
            "perdeu_bonus_zero_erros": r.perdeu_bonus_zero_erros,
            "perdeu_bonus_qualidade_por_erro": r.perdeu_bonus_qualidade_por_erro,
            "ativado_ciclo1": m.ativado_ciclo1,
            "ativado_ciclo2": m.ativado_ciclo2,
        },
        "faixas": {
            "individual": r.faixa_individual,
            "subequipe": r.faixa_subequipe,
            "geral_time": r.faixa_geral_time,
        },
        "metricas_brutas": {
            "meta_individual_pct": m.meta_individual_pct,
            "meta_subequipe_pct": m.meta_subequipe_pct,
            "meta_geral_time_pct": m.meta_geral_time_pct,
            "tempo_medio_atendimento_min": m.tempo_medio_atendimento_min,
            "primeira_resposta_min": m.primeira_resposta_min,
            "nps_pct": m.nps_pct,
            "novos_cpcs": m.novos_cpcs,
            "registro_sistema_pct": m.registro_sistema_pct,
            "avaliacoes_google": m.avaliacoes_google,
            "semanas_batidas": m.semanas_batidas,
        },
    }