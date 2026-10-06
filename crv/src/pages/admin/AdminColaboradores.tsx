import { useEffect, useState } from "react";
import { supabase } from "../../supabaseClient";
import "./adminhome.css";

const API_URL = import.meta.env.VITE_API_URL as string;

interface DepartamentoResumo {
  name: string;
  onlineUserCount: number;
  offlineUserCount: number;
  absentUserCount: number;
  onQueueTicketCount: number;
  openTicketCount: number;
}

const TODAS_SUBEQUIPES: sub[] = ["SUBEQUIPE 1", "SUBEQUIPE 2", "SUBEQUIPE 3"];

interface TotaisGerais {
  openTickets: number;
  queueTickets: number;
  usersWithAttendance: number;
  usersWithoutAttendance: number;
  onlineUsersCount: number;
  offlineUsersCount: number;
  absentUsersCount: number;
}
type sub = "SUBEQUIPE 1" | "SUBEQUIPE 2" | "SUBEQUIPE 3";
interface Atendente {
  nome: string;
  status: string;
  chamadosAbertos: number | null;
  subequipe?: sub;
  bruto:Json;
}

type Json = Record<string, unknown>;

function ehObjeto(valor: unknown): valor is Json {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor);
}

// Lê um campo do objeto tentando vários caminhos (ex.: "name" ou "user.name").
// Os nomes de campo do attendance-resume ainda não foram confirmados, então
// aqui ficam os candidatos. Quando souber o nome real, deixe só ele.
function pegar(obj: Json, caminhos: string[]): unknown {
  for (const caminho of caminhos) {
    let atual: unknown = obj;
    for (const parte of caminho.split(".")) {
      atual = ehObjeto(atual) ? atual[parte] : undefined;
    }
    if (atual !== undefined && atual !== null) return atual;
  }
  return undefined;
}

// Acha a primeira lista de objetos dentro do JSON, esteja onde estiver.
function acharLista(payload: unknown, profundidade = 0): Json[] {
  if (Array.isArray(payload)) return payload.filter(ehObjeto);
  if (ehObjeto(payload) && profundidade < 3) {
    for (const valor of Object.values(payload)) {
      const lista = acharLista(valor, profundidade + 1);
      if (lista.length > 0) return lista;
    }
  }
  return [];
}

function normalizarAtendente(item: Json): Atendente {
  const nome = pegar(item, ["name", "userName", "user.name", "attendant.name"]);
  const status = pegar(item, ["status", "userStatus", "user.status"]);
  const chamados = pegar(item, [
  "ticketsOpenCount", 
  "openTicketCount",
  "openTickets",
  "ticketCount",
  "totalTickets",
]);
  const tickets = pegar(item, ["tickets"]);
 function acharSubequipe(item: Json): sub | undefined {
  const departments = pegar(item, ["departments"]);
  if (!Array.isArray(departments)) return undefined;
  return departments.find(
    (d): d is sub => d === "SUBEQUIPE 1" || d === "SUBEQUIPE 2" || d === "SUBEQUIPE 3"
  );
}
  const subequipe = acharSubequipe(item);

return {
  nome: typeof nome === "string" ? nome : "(sem nome)",
  status: typeof status === "string" ? status.toLowerCase() : "desconhecido",
  chamadosAbertos:
    typeof chamados === "number" ? chamados : Array.isArray(tickets) ? tickets.length : null,
  subequipe,
  bruto: item,

};
}

function rotuloStatus(status: string): string {
  if (status === "online") return "Online";
  if (status === "offline") return "Offline";
  if (["absent", "away", "ausente"].includes(status)) return "Ausente";
  return status;
}


const ORDEM_STATUS: Record<string, number> = {
  online: 0,
  absent: 1,
  away: 1,
  ausente: 1,
  offline: 2,
};

async function authHeaders() {
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return {
    Authorization: `Bearer ${session?.access_token}`,
  };
}

async function buscarJson(caminho: string): Promise<unknown> {
  const headers = await authHeaders();
  const res = await fetch(`${API_URL}${caminho}`, { headers });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Erro ao buscar dados da Digisac");
  }
  return res.json();
}

export default function AdminColaboradores() {
  const [departamentos, setDepartamentos] = useState<DepartamentoResumo[]>([]);
  const [totais, setTotais] = useState<TotaisGerais | null>(null);
  const [atendentes, setAtendentes] = useState<Atendente[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState("");
  const [erroAtendentes, setErroAtendentes] = useState("");
  const [subequipeDoUsuario] = useState<sub | "ADMIN">("ADMIN"); // TODO: pegar do usuário real
  const abasVisiveis =
    subequipeDoUsuario === "ADMIN" ? TODAS_SUBEQUIPES : [subequipeDoUsuario];
  const [abaAtiva, setAbaAtiva] = useState<sub>(abasVisiveis[0]);
  const atendentesDaAba = atendentes.filter((a) => a.subequipe === abaAtiva);




  async function carregarResumo() {
    setErro("");
    try {
      const data = (await buscarJson("/api/digisac/agora/resumo")) as {
        totals?: unknown;
      };

      if (Array.isArray(data.totals)) {
        setDepartamentos(data.totals as DepartamentoResumo[]);
        setTotais(null);
      } else if (ehObjeto(data.totals)) {
        setTotais(data.totals as unknown as TotaisGerais);
        setDepartamentos([]);
      } else {
        setDepartamentos([]);
        setTotais(null);
      }
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro desconhecido");
    }
  }

  // Atendentes carregam separado: se falhar, departamentos e totais continuam na tela.
  // Atendentes carregam separado: se falhar, departamentos e totais continuam na tela.
  async function carregarAtendentes() {
    setErroAtendentes("");
    try {
      const lista = acharLista(
        await buscarJson("/api/digisac/agora/atendentes"),
      );
      console.log(lista[0]);
      setAtendentes(
        lista
          .map(normalizarAtendente)
          .sort(
            (a, b) =>
              (ORDEM_STATUS[a.status] ?? 3) - (ORDEM_STATUS[b.status] ?? 3) ||
              (b.chamadosAbertos ?? 0) - (a.chamadosAbertos ?? 0) ||
              a.nome.localeCompare(b.nome),
          ),
      );
    } catch (err) {
      setErroAtendentes(
        err instanceof Error ? err.message : "Erro desconhecido",
      );
    }
  }

  // O loading só liga na primeira carga. Nas atualizações de 30s a tela
  // continua visível, senão o painel inteiro some e volta a cada ciclo.
  async function carregar(primeira = false) {
    if (primeira) setLoading(true);
    await Promise.all([carregarResumo(), carregarAtendentes()]);
    setLoading(false);
  }

  useEffect(() => {
    Promise.resolve().then(() => carregar(true));
    const interval = setInterval(() => carregar(), 30000);
    return () => clearInterval(interval);
  }, []);

  const semDadosDepartamento = !totais && departamentos.length === 0;

  return (
    <div className="admin-home">
      <header className="admin-home-header">
        <h1>Colaboradores — Ao vivo</h1>
        <p>Atendimentos em tempo real na Digisac</p>
      </header>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {abasVisiveis.map((sub) => (
          <button
            key={sub}
            onClick={() => setAbaAtiva(sub)}
            style={{
              fontWeight: sub === abaAtiva ? "bold" : "normal",
              borderBottom: sub === abaAtiva ? "2px solid #3b82f6" : "none",
            }}
          >
            {sub}
          </button>
        ))}
      </div>
      {loading && semDadosDepartamento && atendentes.length === 0 && (
        <p
          style={{
            color: "#94a3b8",
            fontWeight: "bold",
            justifyContent: "center",
          }}
        >
          Carregando...
        </p>
      )}

      {erro && <p className="status-erro">{erro}</p>}

      {!loading && !erro && totais && (
        <div className="dash-metrics-grid" style={{ marginBottom: 16 }}>
          <div className="dash-metric-box">
            <p className="dash-metric-value emerald">
              {totais.onlineUsersCount}
            </p>
            <p className="dash-metric-label">Online agora</p>
          </div>
          <div className="dash-metric-box">
            <p className="dash-metric-value">{totais.offlineUsersCount}</p>
            <p className="dash-metric-label">Offline</p>
          </div>
          <div className="dash-metric-box">
            <p className="dash-metric-value">{totais.absentUsersCount}</p>
            <p className="dash-metric-label">Ausentes</p>
          </div>
          <div className="dash-metric-box">
            <p className="dash-metric-value">{totais.queueTickets}</p>
            <p className="dash-metric-label">Na fila</p>
          </div>
          <div className="dash-metric-box">
            <p className="dash-metric-value">{totais.openTickets}</p>
            <p className="dash-metric-label">Tickets abertos</p>
          </div>
          <div className="dash-metric-box">
            <p className="dash-metric-value">{totais.usersWithAttendance}</p>
            <p className="dash-metric-label">Atendentes ativos</p>
          </div>
        </div>
      )}

      {!loading && !erro && departamentos.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h3 className="dash-card-title" style={{ marginBottom: 12 }}>
            Por departamento
          </h3>
          <div className="dash-row-list">
            {departamentos.map((d) => (
              <div key={d.name} className="dash-row">
                <span className="dash-check-item">
                  <span
                    className={`dash-dot ${d.onlineUserCount > 0 ? "ok" : ""}`}
                  ></span>
                  {d.name}
                </span>
                <span className="dash-row-value">
                  {d.onlineUserCount} online · {d.absentUserCount} ausentes ·{" "}
                  {d.offlineUserCount} offline
                  {d.onQueueTicketCount > 0
                    ? ` · ${d.onQueueTicketCount} na fila`
                    : ""}
                  {d.openTicketCount > 0
                    ? ` · ${d.openTicketCount} abertos`
                    : ""}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {erroAtendentes && <p className="status-erro">{erroAtendentes}</p>}

      {!loading && !erroAtendentes && atendentes.length > 0 && (
        <div className="card">
          <h3 className="dash-card-title" style={{ marginBottom: 12 }}>
            Por atendente
          </h3>
          <div className="dash-row-list">
            {atendentesDaAba.map((a) => (
              <div key={a.nome} className="dash-row">
                <details className="infos-atendentes">
                    <summary> 
                  <span className="dash-check-item">
                    {a.nome}
                  <span
                    className={`dash-dot ${a.status === "online" ? "ok" : ""}`}
                    >      
                    </span>
                </span>
                <span className="dash-row-value">
                      {rotuloStatus(a.status)}
                </span>
                  </summary>
                  <p>Informações adicionais sobre {a.nome}</p>
                  <p>chamados abertos {a.chamadosAbertos} </p>
                  </details>
              </div>
            ))}
          </div>
          {/* Temporário: mostra os nomes dos campos que a Digisac devolveu, para
              conferir se nome, status e chamados foram lidos do campo certo. */}
        </div>
      )}

      {!loading &&
        !erro &&
        !erroAtendentes &&
        semDadosDepartamento &&
        atendentes.length === 0 && (
          <p
            style={{
              color: "#94a3b8",
              fontWeight: "bold",
              justifyContent: "center",
            }}
          >
            Nenhum dado disponível agora.
          </p>
        )}
    </div>
  );
}
