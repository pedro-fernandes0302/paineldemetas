import { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth, Cargo } from "../AuthContext";

interface ProtectedRouteProps {
  children: ReactNode;
  cargosPermitidos: Cargo[];
}

export function ProtectedRoute({ children, cargosPermitidos }: ProtectedRouteProps) {
  const { cargo, loading } = useAuth();

  if (loading) {
    return <div>Carregando...</div>;
  }

  const permitidosLower = cargosPermitidos.map((c) => c.toLowerCase());
  if (!cargo || !permitidosLower.includes(cargo.toLowerCase())) {
    return <Navigate to="/nao-autorizado" replace />;
  }

  return <>{children}</>;
}