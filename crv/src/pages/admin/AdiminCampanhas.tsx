import { useEffect, useState } from "react";
const API_URL = import.meta.env.VITE_API_URL;

interface FaixaData {
    inicio: string;
    fim: string;
    rotulo?: string;
}

interface Metricas {
    campanhas: number;
    enviadas: number;
    visualizadas: number;
    taxa_abertura: number;
    custo: number;
    boletos: number;
    honorarios: number;
}

type VariacaoPct = Partial<Record<keyof Metricas, number | null>>;

interface ListaCampanha {
    titulo: string;
    carteira: string;
    enviadas: number;
    servidor: number;
    recebidas: number;
    visualizadas: number;
    nao_enviadas: number;
    erro: number;
    pct_abertura: number;
}

interface CarteiraResumo {
    carteira: string;
    enviadas: number;
    servidor: number;
    recebidas: number;
    visualizadas: number;
    nao_enviadas: number;
    pct_abertura: number;
}

interface PontoEvolucao {
    data: string;
    enviadas: number;
    lidas: number;
}
type Periodo = "dia" | "semana" | "mes";

interface PainelDigisac {
    periodo: Periodo;
    intervalo: FaixaData;
    intervalo_anterior: FaixaData;
    carteiras_filtradas: string[];
    total_campanhas_carregadas: number;
    metricas: Metricas | null;
    metricas_anterior: Metricas | null;
  variacao_pct: VariacaoPct | null;
  avisos: string[];
  tabela_listas: ListaCampanha[];
  tabela_carteiras: CarteiraResumo[];
  evolucao_diaria: PontoEvolucao[];
}



export default function AdminPainelCampanhas() {
  const [periodo, setPeriodo] = useState<Periodo>("dia");
  const [carteirasDisponiveis, setCarteirasDisponiveis] = useState<string[]>([]);
  const [carteirasFiltro, setCarteirasFiltro] = useState<string[]>([]);
  const [dados, setDados] = useState<PainelDigisac | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  async function carregarPainel() {
    try {
      setErro(null);

      const params = new URLSearchParams();
      carteirasFiltro.forEach((c) => params.append("carteiras", c));

      const qs = params.toString(); // "" quando não tem filtro
      const url = `${API_URL}/admin/painel-digisac/${periodo}${qs ? `?${qs}` : ""}`;

      const res = await fetch(url, {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("token") ?? ""}`,
        },
      });

      if (!res.ok) {
        throw new Error(`Erro ${res.status} ao carregar painel`);
      }

      setDados(await res.json());
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Erro desconhecido");
    }
  }

  useEffect(() => {
    carregarPainel();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [periodo, carteirasFiltro]);

  return (
    <div className="admin-home">
      <div className="filtros">
        <select
          value={periodo}
          onChange={(e) => setPeriodo(e.target.value as Periodo)}
        >
          <option value="dia">Dia</option>
          <option value="semana">Semana</option>
          <option value="mes">Mês</option>
        </select>

        {carteirasDisponiveis.map((c) => (
          <label key={c}>
            <input
              type="checkbox"
              checked={carteirasFiltro.includes(c)}
              onChange={() =>
                setCarteirasFiltro((prev) =>
                  prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]
                )
              }
            />
            {c}
          </label>
        ))}
      </div>

      {erro && <p className="erro">{erro}</p>}
      {!dados && !erro && <p>Carregando...</p>}
      {dados && <pre>{JSON.stringify(dados, null, 2)}</pre>}
    </div>
  );
}