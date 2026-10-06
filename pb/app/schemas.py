"""
Modelos Pydantic para as respostas da API.
"""
from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class MetricasAtendimento(BaseModel):
    tempo_medio_atendimento_seg: Optional[float]
    primeira_resposta_seg: Optional[float]
    qtd_chamados_fechados: int
    qtd_com_primeira_resposta: int


class Csat(BaseModel):
    csat_total_respostas: int
    csat_percentual: Optional[float]
    csat_totalmente_satisfeitos: int
    csat_satisfeitos: int
    csat_neutros: int
    csat_insatisfeitos: int
    csat_totalmente_insatisfeitos: int
    csat_invalidos: int
    ai_csat_total_respostas: int
    ai_csat_percentual: Optional[float]
    ai_csat_totalmente_satisfeitos: int
    ai_csat_satisfeitos: int
    ai_csat_neutros: int
    ai_csat_insatisfeitos: int
    ai_csat_totalmente_insatisfeitos: int
    ai_csat_invalidos: int


class RVResumo(BaseModel):
    total: float
    individual: float
    coletivo: float
    bonus_qualidade: float
    bonus_consistencia: float
    bonus_ativado: float


class RVBreakdownQualidade(BaseModel):
    tempo_atendimento: float
    primeira_resposta: float
    nps: float
    novos_cpcs: float
    registro_sistema: float
    avaliacao_google: float
    zero_erros: float


class RVFlags(BaseModel):
    tem_erro_grave: bool
    tem_advertencia: bool
    perdeu_bonus_zero_erros: bool
    perdeu_bonus_qualidade_por_erro: bool
    ativado_ciclo1: bool
    ativado_ciclo2: bool


class RVFaixas(BaseModel):
    individual: str
    subequipe: str
    geral_time: str


class MetricasBrutas(BaseModel):
    meta_individual_pct: Optional[float]
    meta_subequipe_pct: Optional[float]
    meta_geral_time_pct: Optional[float]
    tempo_medio_atendimento_min: Optional[float]
    primeira_resposta_min: Optional[float]
    nps_pct: Optional[float]
    novos_cpcs: Optional[int]
    registro_sistema_pct: Optional[float]
    avaliacoes_google: Optional[int]
    semanas_batidas: int


class DesempenhoResponse(BaseModel):
    nome: str
    cargo: str
    equipe: str | None = None
    periodo_inicio: str
    periodo_fim: str
    metricas_atendimento: MetricasAtendimento
    csat: Csat
    
    # RV completo
    rv: RVResumo
    breakdown: dict
    flags: RVFlags
    faixas: RVFaixas
    metricas_brutas: MetricasBrutas

    """
ADICIONAR ao final do seu app/schemas.py existente
(reaproveita os imports que já estão lá: BaseModel, Optional, datetime)
"""


class ColaboradorResumo(BaseModel):
    email: str
    nome: str
    cargo: str
    equipe: str | None = None
    digisac_user_id: Optional[str]


class RegistrarAdvertenciaRequest(BaseModel):
    email: str
    motivo: str
    grave: bool = False  # True vai pra "erros_graves", False vai pra "advertencias"


class RegistrarAdvertenciaResponse(BaseModel):
    email: str
    tem_advertencia: bool
    tem_erro_grave: bool
    registrado_em: datetime


class AtivarRequest(BaseModel):
    email: str
    ciclo: int  # 1 ou 2


class AtivarResponse(BaseModel):
    email: str
    ativado_ciclo1: bool
    ativado_ciclo2: bool


class RelatorioExportRequest(BaseModel):
    periodo_inicio: str
    periodo_fim: str
    equipe: Optional[str] = None


class TemplateCampanha(BaseModel):
    template: str
    credor: str
    percentual: float
    template_digisac: str | None = None
    atraso_dias_inicio: int | None = None
    atraso_dias_fim: int | None = None
    filtro_cpc: str | None = None
    marcador: str | None = None
    coligada_inicio: int | None = None
    coligada_fim: int | None = None
    coligada_lista: list[int] | None = None
    defasagem_min: float | None = None
    valor_min: float | None = None


class ProcessarCampanhaBody(BaseModel):
    templates: list[TemplateCampanha]
    carteira: str | None = None