const API_URL = import.meta.env.VITE_API_URL;
import { useState, useCallback, useEffect, useRef } from "react";
import { SupabaseClient, Session } from "@supabase/supabase-js";
import { Link } from "react-router-dom";
import "./dashboard.css";

interface DashboardProps {
  session: Session;
  supabase: SupabaseClient;
}

interface RVResumo {
  total: number;
  individual: number;
  coletivo: number;
  bonus_qualidade: number;
  bonus_consistencia: number;
  bonus_ativado: number;
}

interface BreakdownIndividual {
  semana1: number;
  semana2: number;
  semana3: number;
  semana4: number;
}

interface BreakdownColetivo {
  subequipe: number;
  geral_time: number;
}

interface BreakdownQualidade {
  tempo_atendimento: number;
  primeira_resposta: number;
  nps: number;
  novos_cpcs: number;
  registro_sistema: number;
  avaliacao_google: number;
  zero_erros: number;
}

interface Breakdown {
  individual_por_semana: BreakdownIndividual;
  coletivo: BreakdownColetivo;
  qualidade: BreakdownQualidade;
}

interface Flags {
  tem_erro_grave: boolean;
  tem_advertencia: boolean;
  perdeu_bonus_zero_erros: boolean;
  perdeu_bonus_qualidade_por_erro: boolean;
  ativado_ciclo1: boolean;
  ativado_ciclo2: boolean;
}

interface Faixas {
  individual: string;
  subequipe: string;
  geral_time: string;
}

interface MetricasBrutas {
  meta_individual_pct: number | null;
  meta_subequipe_pct: number | null;
  meta_geral_time_pct: number | null;
  tempo_medio_atendimento_min: number | null;
  primeira_resposta_min: number | null;
  nps_pct: number | null;
  novos_cpcs: number | null;
  registro_sistema_pct: number | null;
  avaliacoes_google: number | null;
  semanas_batidas: number;
}

interface MetricasAtendimento {
  tempo_medio_atendimento_seg: number;
  primeira_resposta_seg: number;
  qtd_chamados_fechados: number;
  qtd_com_primeira_resposta: number;
}

interface CsatData {
  csat_total_respostas: number;
  csat_percentual: number | null;
  csat_totalmente_satisfeitos: number;
  csat_satisfeitos: number;
  csat_neutros: number;
  csat_insatisfeitos: number;
  csat_totalmente_insatisfeitos: number;
  csat_invalidos: number;
  ai_csat_total_respostas: number;
  ai_csat_percentual: number | null;
  ai_csat_totalmente_satisfeitos: number;
  ai_csat_satisfeitos: number;
  ai_csat_neutros: number;
  ai_csat_insatisfeitos: number;
  ai_csat_totalmente_insatisfeitos: number;
  ai_csat_invalidos: number;
}

interface DesempenhoData {
  nome: string;
  cargo: string;
  equipe: string;
  periodo_inicio: string;
  periodo_fim: string;
  metricas_atendimento: MetricasAtendimento;
  csat: CsatData;
  rv: RVResumo;
  breakdown: Breakdown;
  flags: Flags;
  faixas: Faixas;
  metricas_brutas: MetricasBrutas;
}

export default function Dashboard({ session, supabase }: DashboardProps) {
  const [data, setData] = useState<DesempenhoData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const initialized = useRef(false);

  const fetchDesempenho = useCallback(async () => {
    try {
      const token = session.access_token;
      const res = await fetch(`${API_URL}/api/desempenho/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Erro ao carregar dados");
      }

      const json: DesempenhoData = await res.json();
      setData(json);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Erro desconhecido");
      }
    } finally {
      setLoading(false);
    }
  }, [session.access_token]);

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    Promise.resolve().then(() => fetchDesempenho());
  }, [fetchDesempenho]);

  const handleLogout = async () => {
    await supabase.auth.signOut();
  };

  if (loading) {
    return (
      <div className="dash-loading">
        <div className="dash-spinner"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dash-error-page">
        <div className="card dash-error-card">
          <div className="dash-error-icon">⚠️</div>
          <h2>Erro ao carregar</h2>
          <p>{error}</p>
          <button onClick={fetchDesempenho} className="dash-btn-retry">
            Tentar novamente
          </button>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const rv = data.rv;
  const breakdown = data.breakdown;
  const flags = data.flags;
  const faixas = data.faixas;
  const metricas = data.metricas_brutas;
  const atendimento = data.metricas_atendimento;
  const csat = data.csat;

  const formatMoney = (v: number) =>
    v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

  const formatPct = (v: number | null) =>
    v !== null && v !== undefined ? `${v.toFixed(1)}%` : "-";

  const formatMin = (v: number | null) =>
    v !== null && v !== undefined ? `${v.toFixed(0)} min` : "-";

  const getFaixaLabel = (f: string) => {
    const map: Record<string, string> = {
      abaixo_95: "< 95%",
      "95_99": "95% – 99%",
      "100_119": "100% – 119%",
      "120_149": "120% – 149%",
      "150_199": "150% – 199%",
      "200_ou_mais": "≥ 200%",
    };
    return map[f] || f;
  };

  const getFaixaColor = (f: string) => {
    if (f === "abaixo_95") return "badge-red";
    if (f === "95_99") return "badge-yellow";
    return "badge-green";
  };

  return (
    <div className="dash-page">
      <header className="dash-header">
        <div className="dash-header-inner">
          <div className="dash-header-left">
            <div className="dash-logo">
              <span style={{ fontSize: 28 }} aria-hidden="true">📊</span>
            </div>
            <div className="dash-header-title">
              <h1>Painel RV</h1>
              <p>
                {data.nome} · {data.cargo} · {data.equipe}
              </p>
            </div>
          </div>
          <div className="dash-header-actions">
            {["admin", "rh", "vice-lider"].includes(
              data.cargo.toLowerCase(),
            ) && (
              <Link to="/admin" className="dash-link-admin">
                Admin
              </Link>
            )}
            <button onClick={handleLogout} className="dash-btn-logout">
              Sair
            </button>
          </div>
        </div>
      </header>

      <main className="dash-main">
        <div className="card-highlight dash-total-card">
          <p className="dash-total-label">Remuneração Variável Total</p>
          <p className="dash-total-value">{formatMoney(rv.total)}</p>
          <div className="dash-total-badges">
            <span className={getFaixaColor(faixas.individual)}>
              Individual: {getFaixaLabel(faixas.individual)}
            </span>
            <span className={getFaixaColor(faixas.subequipe)}>
              Sub: {getFaixaLabel(faixas.subequipe)}
            </span>
          </div>
        </div>

        <div className="dash-grid">
          <div className="card">
            <div className="dash-card-header">
              <h3 className="dash-card-title">RV Individual</h3>
              <span className="badge-green">{formatMoney(rv.individual)}</span>
            </div>
            <div className="dash-row-list">
              <div className="dash-row">
                <span>Semana 1</span>
                <span className="dash-row-value">
                  {formatMoney(breakdown.individual_por_semana.semana1)}
                </span>
              </div>
              <div className="dash-row">
                <span>Semana 2</span>
                <span className="dash-row-value">
                  {formatMoney(breakdown.individual_por_semana.semana2)}
                </span>
              </div>
              <div className="dash-row">
                <span>Semana 3</span>
                <span className="dash-row-value">
                  {formatMoney(breakdown.individual_por_semana.semana3)}
                </span>
              </div>
              <div className="dash-row">
                <span>Semana 4</span>
                <span className="dash-row-value">
                  {formatMoney(breakdown.individual_por_semana.semana4)}
                </span>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="dash-card-header">
              <h3 className="dash-card-title">RV Coletivo</h3>
              <span className="badge-blue">{formatMoney(rv.coletivo)}</span>
            </div>
            <div className="dash-row-list">
              <div className="dash-row">
                <span>Subequipe</span>
                <span className="dash-row-value">
                  {formatMoney(breakdown.coletivo.subequipe)}
                </span>
              </div>
              <div className="dash-row">
                <span>Geral do Time</span>
                <span className="dash-row-value">
                  {formatMoney(breakdown.coletivo.geral_time)}
                </span>
              </div>
              <div className="dash-row-divider">
                <div className="dash-row">
                  <span>Meta Sub</span>
                  <span className="dash-row-highlight">
                    {formatPct(metricas.meta_subequipe_pct)}
                  </span>
                </div>
                <div className="dash-row" style={{ marginTop: 4 }}>
                  <span>Meta Geral</span>
                  <span className="dash-row-highlight">
                    {formatPct(metricas.meta_geral_time_pct)}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="dash-card-header">
              <h3 className="dash-card-title">Bônus Qualidade</h3>
              <span
                className={`badge ${rv.bonus_qualidade > 0 ? "badge-green" : "badge-red"}`}
              >
                {formatMoney(rv.bonus_qualidade)}
              </span>
            </div>
            <div className="dash-row-list">
              {[
                {
                  label: "Tempo atend. < 1h",
                  val: breakdown.qualidade.tempo_atendimento,
                  ok: breakdown.qualidade.tempo_atendimento > 0,
                },
                {
                  label: "1ª resposta < 30min",
                  val: breakdown.qualidade.primeira_resposta,
                  ok: breakdown.qualidade.primeira_resposta > 0,
                },
                {
                  label: "NPS > 80%",
                  val: breakdown.qualidade.nps,
                  ok: breakdown.qualidade.nps > 0,
                },
                {
                  label: "Novos CPCs > 100",
                  val: breakdown.qualidade.novos_cpcs,
                  ok: breakdown.qualidade.novos_cpcs > 0,
                },
                {
                  label: "Registro ≥ 95%",
                  val: breakdown.qualidade.registro_sistema,
                  ok: breakdown.qualidade.registro_sistema > 0,
                },
                {
                  label: "Avaliações Google ≥ 2",
                  val: breakdown.qualidade.avaliacao_google,
                  ok: breakdown.qualidade.avaliacao_google > 0,
                },
                {
                  label: "Zero erros",
                  val: breakdown.qualidade.zero_erros,
                  ok: breakdown.qualidade.zero_erros > 0,
                },
              ].map((item, i) => (
                <div key={i} className="dash-row">
                  <span className="dash-check-item">
                    <span className={`dash-dot ${item.ok ? "ok" : ""}`}></span>
                    {item.label}
                  </span>
                  <span className={`dash-check-value ${item.ok ? "ok" : ""}`}>
                    {formatMoney(item.val)}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="dash-card-header">
              <h3 className="dash-card-title">Consistência Semanal</h3>
              <span
                className={`badge ${rv.bonus_consistencia > 0 ? "badge-green" : "badge-red"}`}
              >
                {formatMoney(rv.bonus_consistencia)}
              </span>
            </div>
            <div className="dash-row-list">
              <div className="dash-row">
                <span>Semanas batidas</span>
                <span className="dash-row-value">
                  {metricas.semanas_batidas}/4
                </span>
              </div>
              <div className="dash-row">
                <span>3 de 4 semanas</span>
                <span className="dash-row-highlight">+ R$ 30</span>
              </div>
              <div className="dash-row">
                <span>4 de 4 semanas</span>
                <span className="dash-row-highlight">+ R$ 50</span>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="dash-card-header">
              <h3 className="dash-card-title">Bônus de ativação</h3>
              <span
                className={`badge ${rv.bonus_ativado > 0 ? "badge-green" : "badge-red"}`}
              >
                {formatMoney(rv.bonus_ativado)}
              </span>
            </div>
            <div className="dash-row-list">
              <div className="dash-row">
                <span>Ciclo 01</span>
                <span
                  className={`dash-check-value ${flags.ativado_ciclo1 ? "ok" : ""}`}
                >
                  {flags.ativado_ciclo1 ? "✓ Ativo (+R$ 25)" : "—"}
                </span>
              </div>
              <div className="dash-row">
                <span>Ciclo 02</span>
                <span
                  className={`dash-check-value ${flags.ativado_ciclo2 ? "ok" : ""}`}
                >
                  {flags.ativado_ciclo2 ? "✓ Ativo (+R$ 25)" : "—"}
                </span>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="dash-card-header">
              <h3 className="dash-card-title">Situação</h3>
            </div>
            <div className="dash-row-list">
              {flags.tem_erro_grave && (
                <div className="dash-flag-box erro">
                  ⚠️ Erro grave registrado — bônus de qualidade zerado
                </div>
              )}
              {flags.tem_advertencia && !flags.tem_erro_grave && (
                <div className="dash-flag-box aviso">
                  ⚠️ Advertência registrada — perdeu bônus de zero erros
                </div>
              )}
              {!flags.tem_erro_grave && !flags.tem_advertencia && (
                <div className="dash-flag-box ok">
                  ✅ Sem pendências administrativas
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="card">
          <h3
            className="dash-card-title"
            style={{ fontSize: 18, marginBottom: 16 }}
          >
            Métricas de Atendimento
          </h3>
          <div className="dash-metrics-grid">
            <div className="dash-metric-box">
              <p className="dash-metric-value">
                {formatMin(atendimento.tempo_medio_atendimento_seg / 60)}
              </p>
              <p className="dash-metric-label">Tempo Médio Atendimento</p>
            </div>
            <div className="dash-metric-box">
              <p className="dash-metric-value">
                {formatMin(atendimento.primeira_resposta_seg / 60)}
              </p>
              <p className="dash-metric-label">Primeira Resposta</p>
            </div>
            <div className="dash-metric-box">
              <p className="dash-metric-value">
                {atendimento.qtd_chamados_fechados}
              </p>
              <p className="dash-metric-label">Chamados Fechados</p>
            </div>
            <div className="dash-metric-box">
              <p className="dash-metric-value emerald">
                {formatPct(csat.csat_percentual)}
              </p>
              <p className="dash-metric-label">CSAT</p>
            </div>
          </div>
        </div>

        <p className="dash-periodo">
          Período: {new Date(data.periodo_inicio).toLocaleDateString("pt-BR")} —{" "}
          {new Date(data.periodo_fim).toLocaleDateString("pt-BR")}
        </p>
      </main>
    </div>
  );
}
