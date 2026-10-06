import { useState } from "react";
import { supabase } from "../../supabaseClient";
import "./adminhome.css";

const API_URL = import.meta.env.VITE_API_URL as string;

async function authHeaders() {
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${session?.access_token}`,
  };
}

export default function AdminRelatorios() {
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
    <div className="admin-home">
      <header className="admin-home-header">
        <h1>Relatórios</h1>
        <p>Exporta dados de desempenho/RV do período</p>
      </header>
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
    </div>
  );
}