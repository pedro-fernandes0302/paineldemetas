import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./AuthContext";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { supabase } from "./supabaseClient";
import { useState, useEffect } from "react";
import { Session } from "@supabase/supabase-js";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import { AdminLayout } from "./pages/admin/AdminLayout";
import AdminOverview from "./pages/admin/AdminOverview";
import AdminRegistrar from "./pages/admin/AdminRegistrar";
import AdminAtivar from "./pages/admin/AdminAtivar";
import AdminColaboradores from "./pages/admin/AdminColaboradores.tsx";
import AdminCriarlista from "./pages/admin/AdminCriarlista"
import AdminPainelCampanhas from "./pages/admin/AdiminCampanhas"

function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      setLoading(false);
    });
    const { data: listener } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        setSession(session);
      },
    );
    return () => listener.subscription.unsubscribe();
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-500"></div>
      </div>
    );
  }

  if (!session) {
    return <Login supabase={supabase} />;
  }

  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route
            path="/"
            element={<Dashboard session={session} supabase={supabase} />}
          />
          <Route
            path="/admin"
            element={
              <ProtectedRoute cargosPermitidos={["admin", "rh", "vice-lider"]}>
                <AdminLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<AdminOverview />} />
            <Route path="colaboradores" element={<AdminColaboradores />} />
            <Route path="registrar" element={<AdminRegistrar />} />
            <Route path="ativar" element={<AdminAtivar />} />
            <Route path="criar-lista" element={<AdminCriarlista />} />
            <Route path="painel-campanhas" element={<AdminPainelCampanhas />} />
          </Route>
          <Route path="/nao-autorizado" element={<div>Acesso negado</div>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
