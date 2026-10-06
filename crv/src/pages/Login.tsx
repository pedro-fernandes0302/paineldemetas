import { useState } from "react";
import { SupabaseClient } from "@supabase/supabase-js";
import "./login.css";

interface LoginProps {
  supabase: SupabaseClient;
}

export default function Login({ supabase }: LoginProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    const { error } = await supabase.auth.signInWithPassword({ email, password });

    if (error) {
      setError(error.message);
    }
    setLoading(false);
  };

  return (
    <div className="login-page">
      <div className="login-container">
        <div className="login-header">
          <div className="login-logo">
              <span style={{ fontSize: 40 }} aria-hidden="true">📊</span>
          </div>
          <h1>Painel RV</h1>
          <p>Sistema de Desempenho e Remuneração Variável</p>
        </div>

        <div className="card">
          <form onSubmit={handleLogin} className="login-form">
            <div className="login-field">
              <label>E-mail</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="seu@email.com"
                required
              />
            </div>

            <div className="login-field">
              <label>Senha</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
              />
            </div>

            {error && <div className="login-error">{error}</div>}

            <button type="submit" disabled={loading} className="login-submit">
              {loading ? "Entrando..." : "Entrar"}
            </button>
          </form>
        </div>

        <p className="login-footer">Use o mesmo e-mail cadastrado no sistema da empresa</p>
      </div>
    </div>
  );
}