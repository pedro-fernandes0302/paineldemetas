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

export default function AdminRegistrar() {
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
    <div className="admin-home">
      <header className="admin-home-header">
        <h1>Registrar advertência</h1>
        <p>Advertência ou erro grave de um colaborador</p>
      </header>
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
    </div>
  );
}