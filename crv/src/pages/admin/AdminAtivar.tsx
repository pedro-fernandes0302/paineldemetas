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

export default function AdminAtivar() {
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
    <div className="admin-home">
      <header className="admin-home-header">
        <h1>Ativar bônus</h1>
        <p>Ativa ou desativa o ciclo do bônus para um colaborador</p>
      </header>
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
    </div>
  );
}