import { useState } from "react";
import { supabase } from "../../supabaseClient";
import "./adminhome.css";

const API_URL = import.meta.env.VITE_API_URL as string;

type Aba = "advertencia" | "ativacao" | "relatorio";

export default function AdminHome() {
  const [aba, setAba] = useState<Aba>("advertencia");

  return (
    <div className="admin-home">
      <header className="admin-home-header">
        <h1>Painel Admin</h1>
        <p>Gestão de colaboradores e RV</p>
      </header>

      <div className="admin-tabs">
        {[
          { id: "advertencia" as Aba, label: "Advertência / Erro grave" },
          { id: "ativacao" as Aba, label: "Ativar bônus" },
          { id: "relatorio" as Aba, label: "Relatórios" },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setAba(tab.id)}
            className={`admin-tab ${aba === tab.id ? "ativo" : ""}`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {aba === "advertencia" && <FormAdvertencia />}
      {aba === "ativacao" && <FormAtivacao />}
      {aba === "relatorio" && <FormRelatorio />}
    </div>
  );
}

async function authHeaders() {
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${session?.access_token}`,
  };
}

function FormAdvertencia() {
  const [email, setEmail] = useState("");
  const [motivo, setMotivo] = useState("");
  const [grave, setGrave] = useState(false);
  const [status, setStatus] = useState<{ tipo: "ok" | "erro"; msg: string } | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setEnviando(true);
    setStatus(null);
    try {
      const res = await fetch(`${API_URL}/api/admin/registrar`, {
        method: "POST",
        headers: await authHeaders(),
        body: JSON.stringify({ email, motivo, grave }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Erro ao registrar");
      setStatus({ tipo: "ok", msg: `Registrado para ${data.email}.` });
      setEmail("");
      setMotivo("");
      setGrave(false);
    } catch (err) {
      setStatus({ tipo: "erro", msg: err instanceof Error ? err.message : "Erro desconhecido" });
    } finally {
      setEnviando(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="card admin-form">
      <div className="admin-field">
        <label>E-mail do colaborador</label>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="colaborador@empresa.com"
        />
      </div>
      <div className="admin-field">
        <label>Motivo</label>
        <textarea required value={motivo} onChange={(e) => setMotivo(e.target.value)} rows={3} />
      </div>
      <label className="admin-checkbox">
        <input type="checkbox" checked={grave} onChange={(e) => setGrave(e.target.checked)} />
        Erro grave (zera bônus de qualidade)
      </label>
      <button type="submit" disabled={enviando} className="btn-primary">
        {enviando ? "Enviando..." : "Registrar"}
      </button>
      {status && <p className={status.tipo === "ok" ? "status-ok" : "status-erro"}>{status.msg}</p>}
    </form>
  );
}

function FormAtivacao() {
  const [email, setEmail] = useState("");
  const [ciclo, setCiclo] = useState<1 | 2>(1);
  const [status, setStatus] = useState<{ tipo: "ok" | "erro"; msg: string } | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function enviar(acao: "ativar" | "desativar") {
    setEnviando(true);
    setStatus(null);
    try {
      const res = await fetch(`${API_URL}/api/admin/${acao}`, {
        method: "POST",
        headers: await authHeaders(),
        body: JSON.stringify({ email, ciclo }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `Erro ao ${acao}`);
      const verbo = acao === "ativar" ? "ativado" : "desativado";
      setStatus({ tipo: "ok", msg: `Bônus de ciclo ${ciclo} ${verbo} para ${data.email}.` });
      setEmail("");
    } catch (err) {
      setStatus({ tipo: "erro", msg: err instanceof Error ? err.message : "Erro desconhecido" });
    } finally {
      setEnviando(false);
    }
  }

  return (
    <form onSubmit={(e) => e.preventDefault()} className="card admin-form">
      <div className="admin-field">
        <label>E-mail do colaborador</label>
        <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      </div>
      <div className="admin-field">
        <label>Ciclo</label>
        <select value={ciclo} onChange={(e) => setCiclo(Number(e.target.value) as 1 | 2)}>
          <option value={1}>Ciclo 01</option>
          <option value={2}>Ciclo 02</option>
        </select>
      </div>
      <div className="admin-actions">
        <button type="button" onClick={() => enviar("ativar")} disabled={enviando || !email} className="btn-primary">
          {enviando ? "Enviando..." : "Ativar"}
        </button>
        <button type="button" onClick={() => enviar("desativar")} disabled={enviando || !email} className="btn-danger">
          {enviando ? "Enviando..." : "Desativar"}
        </button>
      </div>
      {status && <p className={status.tipo === "ok" ? "status-ok" : "status-erro"}>{status.msg}</p>}
    </form>
  );
}

function FormRelatorio() {
  const [inicio, setInicio] = useState("");
  const [fim, setFim] = useState("");
  const [equipe, setEquipe] = useState("");
  const [status, setStatus] = useState<{ tipo: "ok" | "erro"; msg: string } | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setEnviando(true);
    setStatus(null);
    try {
      const res = await fetch(`${API_URL}/api/admin/relatorios`, {
        method: "POST",
        headers: await authHeaders(),
        body: JSON.stringify({ periodo_inicio: inicio, periodo_fim: fim, equipe: equipe || null }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Erro ao gerar relatório");
      setStatus({ tipo: "ok", msg: data.mensagem });
    } catch (err) {
      setStatus({ tipo: "erro", msg: err instanceof Error ? err.message : "Erro desconhecido" });
    } finally {
      setEnviando(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="card admin-form">
      <div className="admin-grid-2">
        <div className="admin-field">
          <label>Início</label>
          <input type="date" required value={inicio} onChange={(e) => setInicio(e.target.value)} />
        </div>
        <div className="admin-field">
          <label>Fim</label>
          <input type="date" required value={fim} onChange={(e) => setFim(e.target.value)} />
        </div>
      </div>
      <div className="admin-field">
        <label>Equipe (opcional)</label>
        <input value={equipe} onChange={(e) => setEquipe(e.target.value)} placeholder="Deixe vazio para todas" />
      </div>
      <button type="submit" disabled={enviando} className="btn-primary">
        {enviando ? "Gerando..." : "Gerar relatório"}
      </button>
      {status && <p className={status.tipo === "ok" ? "status-ok" : "status-erro"}>{status.msg}</p>}
    </form>
  );
}