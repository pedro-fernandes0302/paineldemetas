// components/Sidebar.tsx
// Menu lateral do painel admin. Os itens exibidos mudam conforme o cargo do usuário logado.

import { NavLink } from "react-router-dom";
import { useAuth } from "../AuthContext";

interface MenuItem {
  label: string;
  path: string;
  cargos: string[]; // quem pode ver esse item (sempre em lowercase)
}

const MENU_ITEMS: MenuItem[] = [
  { label: "Visão geral", path: "/admin", cargos: ["admin", "rh", "vice-lider"] },
  { label: "Colaboradores", path: "/admin/colaboradores", cargos: ["admin", "rh","vice-lider"] },
  { label: "Registrar advertência", path: "/admin/registrar", cargos: ["admin", "rh", "vice-lider"] },
  { label: "Ativar bônus", path: "/admin/ativar", cargos: ["admin", "rh","vice-lider"] },
  {label: "Menu Dashboard", path:"/", cargos:["admin", "rh","vice-lider"]},
  { label: "Criar Lista", path: "/admin/criar-lista", cargos: ["admin", "rh", "vice-lider"] },
  { label: "Painel de Campanhas", path: "/admin/painel-campanhas", cargos: ["admin", "vice-lider"] },
];

export function Sidebar() {
  const { cargo } = useAuth();

  // cargo já vem normalizado em lowercase do AuthContext
  const itensVisiveis = MENU_ITEMS.filter((item) => cargo && item.cargos.includes(cargo));
  console.log("cargo na sidebar:", cargo);
  console.log("itens visíveis:", itensVisiveis);
  return (
    <aside className="admin-sidebar">
      <nav>
        <ul>
          {itensVisiveis.map((item) => (
            <li key={item.path}>
              <NavLink
                to={item.path}
                end={item.path === "/admin"}
                className={({ isActive }) => (isActive ? "ativo" : "")}
              >
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  );
}

