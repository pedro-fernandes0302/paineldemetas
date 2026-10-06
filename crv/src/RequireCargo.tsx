import { useState, useEffect, ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { Session } from "@supabase/supabase-js";

const API_URL = import.meta.env.VITE_API_URL;

interface Props {
  session: Session;
  cargosPermitidos: string[];
  children: ReactNode;
}

export function RequireCargo({ session, cargosPermitidos, children }: Props) {
  const [cargo, setCargo] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

useEffect(() => {
  console.log("RequireCargo montado, buscando dados...");
  fetch(`${API_URL}/api/desempenho/me`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
  })
    .then((res) => {
      console.log("status da resposta:", res.status);
      if (!res.ok) throw new Error(`Erro ${res.status}`);
      return res.json();
    })
    .then((data) => {
      console.log("dados recebidos:", data);
      setCargo(data.cargo);
    })
    .catch((err) => console.error("Erro ao verificar cargo:", err))
    .finally(() => setLoading(false));
}, [session.access_token]);

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-500"></div>
      </div>
    );
  }

  const permitido = cargo && cargosPermitidos.map((c) => c.toLowerCase()).includes(cargo.toLowerCase());

  if (!permitido) {
    console.log("cargo recebido:", cargo, "| permitidos:", cargosPermitidos);
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}