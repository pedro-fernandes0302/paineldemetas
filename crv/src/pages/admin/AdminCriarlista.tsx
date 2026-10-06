import { useState } from "react";
import { supabase } from "../../supabaseClient";
import "./adminhome.css";

const API_URL = import.meta.env.VITE_API_URL as string;

type FiltroCpc = "COM CPC" | "SEM CPC" | undefined; // undefined = sem filtro (GERAL)

interface TemplateCampanha {
  template: string;
  credor: string;
  percentual: number;
  template_digisac?: string;
  atraso_dias_inicio?: number;
  atraso_dias_fim?: number;
  filtro_cpc?: FiltroCpc;
  marcador?: string;
  coligada_inicio?: number;
  coligada_fim?: number;
  coligada_lista?: number[];
  defasagem_min?: number;
  valor_min?: number;
}

interface ResultadoTemplate {
  template: string;
  status: "ok" | "erro" | "pulado";
  linhas_filtradas?: number;
  url_csv?: string;
  motivo?: string;
}

async function authHeaders() {
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return {
    Authorization: `Bearer ${session?.access_token}`,
  };
}

function statusClasse(status: ResultadoTemplate["status"]) {
  if (status === "ok") return "status-ok";
  if (status === "erro") return "status-erro";
  return "status-pulado";
}

export default function AdminCriarlista() {
  const [templates, setTemplates] = useState<TemplateCampanha[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [draft, setDraft] = useState<Partial<TemplateCampanha>>({});
  const [arquivoPesquisa, setArquivoPesquisa] = useState<File | null>(null);
  const [arquivoLista, setArquivoLista] = useState<ResultadoTemplate[]>([]);

  function adicionarTemplate() {
    if (!draft.template || !draft.credor || !draft.percentual) {
      setErro("Preencha template, credor e percentual.");
      return;
    }
    setTemplates((anterior) => [...anterior, draft as TemplateCampanha]);
    setDraft({});
    setErro(null);
  }

  function removerTemplate(index: number) {
    setTemplates((anterior) => anterior.filter((_, i) => i !== index));
  }

  async function gerarListas() {
    if (!arquivoPesquisa) {
      setErro("Selecione o arquivo da pesquisa-cliente antes de continuar.");
      return;
    }

    const formData = new FormData();
    formData.append("pesquisa_cliente", arquivoPesquisa);

    const headers = await authHeaders();
    const post = await fetch(`${API_URL}${"/ingerir"}`, {
      method: "POST",
      headers,
      body: formData,
    });

    if (!post.ok) {
      const data = await post.json();
      throw new Error(data.detail || "Erro ao manda estrategia ao sistema");
    }
    const headers2 = { ...headers, "Content-Type": "application/json" };

    const mandar = await fetch(`${API_URL}${"/processar"}`, {
      method: "POST",
      headers: headers2,
      body: JSON.stringify({ templates }),
    });

    if (!mandar.ok) {
      const dataError = await mandar.json();
      throw new Error(
        dataError.detail || "Erro ao manda estrategia ao sistema",
      );
    }

    const data = await mandar.json();
    setArquivoLista(data.resultados);
  }

  return (
    <>
      <header className="admin-home-header">
        <h1>Criar listas de mensagens automatica</h1>
        <p>
          Crie listas com o formulario a baixo para realizar a produção de lista
          - Esse Processo pode demorar alguns minutos
        </p>
      </header>
      <div className="admin-form">
        <input
          type="file"
          className="admin-file-input"
          onChange={(e) => setArquivoPesquisa(e.target.files?.[0] ?? null)}
        />

        <ul className="lista-templates">
          {templates.map((t, index) => (
            <li key={index}>
              {t.template} - {t.credor}
              <button
                className="btn-danger"
                onClick={() => removerTemplate(index)}
              >
                Remover
              </button>
            </li>
          ))}
        </ul>

        <div className="admin-field">
          <input
            type="text"
            placeholder="Nome do template"
            value={draft.template ?? ""}
            onChange={(e) =>
              setDraft((anterior) => ({
                ...anterior,
                template: e.target.value,
              }))
            }
          />
        </div>

        <div className="admin-field">
          <input
            type="text"
            placeholder="Credor"
            value={draft.credor ?? ""}
            onChange={(e) =>
              setDraft((anterior) => ({ ...anterior, credor: e.target.value }))
            }
          />
        </div>

        <div className="admin-field">
          <input
            type="number"
            placeholder="Percentual"
            value={draft.percentual ?? ""}
            onChange={(e) =>
              setDraft((anterior) => ({
                ...anterior,
                percentual:
                  e.target.value === "" ? undefined : Number(e.target.value),
              }))
            }
          />
        </div>

        <div className="admin-field">
          <input
            type="text"
            placeholder="Template Digisac"
            value={draft.template_digisac ?? ""}
            onChange={(e) =>
              setDraft((anterior) => ({
                ...anterior,
                template_digisac: e.target.value,
              }))
            }
          />
        </div>

        <div className="admin-field">
          <input
            type="number"
            placeholder="Atraso dias início"
            value={draft.atraso_dias_inicio ?? ""}
            onChange={(e) =>
              setDraft((anterior) => ({
                ...anterior,
                atraso_dias_inicio:
                  e.target.value === "" ? undefined : Number(e.target.value),
              }))
            }
          />
        </div>

        <div className="admin-field">
          <input
            type="number"
            placeholder="Atraso dias fim"
            value={draft.atraso_dias_fim ?? ""}
            onChange={(e) =>
              setDraft((anterior) => ({
                ...anterior,
                atraso_dias_fim:
                  e.target.value === "" ? undefined : Number(e.target.value),
              }))
            }
          />
        </div>

        <div className="admin-field">
          <select
            value={draft.filtro_cpc ?? ""}
            onChange={(e) =>
              setDraft((anterior) => ({
                ...anterior,
                filtro_cpc:
                  e.target.value === ""
                    ? undefined
                    : (e.target.value as FiltroCpc),
              }))
            }
          >
            <option value="">Geral (sem filtro)</option>
            <option value="COM CPC">Com CPC</option>
            <option value="SEM CPC">Sem CPC</option>
          </select>
        </div>

        <div className="admin-field">
          <input
            type="text"
            placeholder="Marcador"
            value={draft.marcador ?? ""}
            onChange={(e) =>
              setDraft((anterior) => ({
                ...anterior,
                marcador: e.target.value,
              }))
            }
          />
        </div>

        <div className="admin-field">
          <input
            type="number"
            placeholder="Coligada início"
            value={draft.coligada_inicio ?? ""}
            onChange={(e) =>
              setDraft((anterior) => ({
                ...anterior,
                coligada_inicio:
                  e.target.value === "" ? undefined : Number(e.target.value),
              }))
            }
          />
        </div>

        <div className="admin-field">
          <input
            type="number"
            placeholder="Coligada fim"
            value={draft.coligada_fim ?? ""}
            onChange={(e) =>
              setDraft((anterior) => ({
                ...anterior,
                coligada_fim:
                  e.target.value === "" ? undefined : Number(e.target.value),
              }))
            }
          />
        </div>

        <div className="admin-field">
          <input
            type="text"
            placeholder="Coligada lista (ex: 1,2,3)"
            onChange={(e) => {
              const valores = e.target.value
                .split(",")
                .map((v) => Number(v.trim()))
                .filter((v) => !isNaN(v));
              setDraft((anterior) => ({
                ...anterior,
                coligada_lista: valores,
              }));
            }}
          />
        </div>

        <div className="admin-field">
          <input
            type="number"
            placeholder="Defasagem mínima"
            value={draft.defasagem_min ?? ""}
            onChange={(e) =>
              setDraft((anterior) => ({
                ...anterior,
                defasagem_min:
                  e.target.value === "" ? undefined : Number(e.target.value),
              }))
            }
          />
        </div>

        <div className="admin-field">
          <input
            type="number"
            placeholder="Valor mínimo"
            value={draft.valor_min ?? ""}
            onChange={(e) =>
              setDraft((anterior) => ({
                ...anterior,
                valor_min:
                  e.target.value === "" ? undefined : Number(e.target.value),
              }))
            }
          />
        </div>

        <button className="btn-primary" onClick={adicionarTemplate}>
          Adicionar template
        </button>

        <ul className="lista-resultados">
          {arquivoLista.map((r, index) => (
            <li key={index}>
              {r.template}
              <span className={statusClasse(r.status)}>{r.status}</span>
            </li>
          ))}
        </ul>

        <button className="btn-primary" onClick={gerarListas}>
          Gerar listas
        </button>

        {erro && <p className="status-erro">{erro}</p>}

        <ul className="lista-resultados">
          {arquivoLista.map((r, index) => (
            <li key={index}>
              {r.template}
              <span className={statusClasse(r.status)}>{r.status}</span>
              {r.status === "ok" && r.url_csv && (
                <a
                  href={r.url_csv}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn-primary"
                >
                  Baixar CSV
                </a>
              )}
              {r.motivo && <span className="status-erro">{r.motivo}</span>}
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
