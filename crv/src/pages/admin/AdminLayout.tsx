import { Outlet } from "react-router-dom";
import { Sidebar } from "../../components/Sidebar";
import "./admin.css";

export function AdminLayout() {
  return (
    <div className="admin-layout">
      <Sidebar />
      <main className="admin-content">
        <Outlet />
      </main>
    </div>
  );
}