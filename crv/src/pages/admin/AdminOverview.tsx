import "./adminhome.css";

export default function AdminOverview() {
  return (
    <div className="admin-home">
      <header className="admin-home-header">
        <h1>Painel Admin</h1>
        <p>Gestão de colaboradores e RV</p>
      </header>
      <p style={{ color: "#94a3b8" }}>
        Use o menu à esquerda para registrar advertências, ativar o bônus de ativação ou gerar relatórios.
      </p>
    </div>
  );
}