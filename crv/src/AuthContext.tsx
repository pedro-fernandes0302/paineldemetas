// AuthContext.tsx
// Carrega a sessão do Supabase (pro token) e busca cargo/equipe na SUA API
// (rota /api/desempenho/me, que já devolve cargo e equipe no DesempenhoResponse).

import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { supabase } from "./supabaseClient";

// ajuste pra URL real do seu backend (Cloud Run) - configure VITE_API_URL no .env do frontend
const API_URL = import.meta.env.VITE_API_URL as string;

export type Cargo = "admin" | "rh" | "vice-lider" | "colaborador";

interface AuthContextType {
  userId: string | null;
  cargo: Cargo | null;
  equipe: string | null;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType>({
  userId: null,
  cargo: null,
  equipe: null,
  loading: true,
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [userId, setUserId] = useState<string | null>(null);
  const [cargo, setCargo] = useState<Cargo | null>(null);
  const [equipe, setEquipe] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function carregarPerfil() {
      const {
        data: { session },
      } = await supabase.auth.getSession();

      if (!session) {
        setLoading(false);
        return;
      }

      setUserId(session.user.id);

      try {
        const resposta = await fetch(`${API_URL}/api/desempenho/me`, {
          headers: { Authorization: `Bearer ${session.access_token}` },
        });

        if (resposta.ok) {
          const dados = await resposta.json();
          // normaliza pra minúsculo — o backend manda "RH", "admin", "Vice-lider" etc,
          // e o resto do app (Sidebar, ProtectedRoute) compara sempre em lowercase.
          const cargoNormalizado = (dados.cargo as string)?.toLowerCase() as Cargo;
          setCargo(cargoNormalizado ?? null);
          setEquipe(dados.equipe ?? null);
        }
      } catch {
        // se a API cair, o usuário fica sem cargo -> ProtectedRoute bloqueia por segurança
      }

      setLoading(false);
    }

    carregarPerfil();
  }, []);

  return (
    <AuthContext.Provider value={{ userId, cargo, equipe, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => useContext(AuthContext);