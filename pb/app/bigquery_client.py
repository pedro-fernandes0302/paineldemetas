"""
Cliente BigQuery - busca colaboradores na tabela do projeto.
Usa Application Default Credentials (ADC) - funciona localmente e no Cloud Run.
NÃO precisa de arquivo JSON de service account.
"""
import google.auth
from google.api_core.exceptions import GoogleAPIError
from google.cloud import bigquery


class ColaboradorNaoEncontrado(Exception):
    """Levantado quando o email não existe na tabela de colaboradores."""
    pass


class BigQueryError(Exception):
    """Levantado quando a consulta ao BigQuery falha (permissão, rede, credencial, etc.)."""
    pass


def get_colaborador_por_email(
    email: str,
    project_id: str,
    dataset: str,
    table: str,
) -> dict:
    """
    Busca um colaborador no BigQuery pelo email.

    Args:
        email: Email do colaborador (vem do JWT do Supabase).
        project_id: ID do projeto GCP (ex: meu-projeto-gcp).
        dataset: Nome do dataset (ex: rh).
        table: Nome da tabela (ex: colaboradores).

    Returns:
        dict com nome, cargo, equipe, digisac_user_id.

    Raises:
        ColaboradorNaoEncontrado: se o email não for encontrado.
        BigQueryError: se a consulta falhar (permissão, rede, credencial, etc.).
    """
    try:
        # Pega credenciais do ambiente (funciona no Cloud Run automaticamente)
        credentials, _ = google.auth.default()
        client = bigquery.Client(credentials=credentials, project=project_id)

        query = f"""
            SELECT nome, cargo, equipe, digisac_user_id
            FROM `{project_id}.{dataset}.{table}`
            WHERE LOWER(email) = LOWER(@email)
            LIMIT 1
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("email", "STRING", email)
            ]
        )

        results = client.query(query, job_config=job_config).result()
    except GoogleAPIError as exc:
        raise BigQueryError(
            f"Erro ao consultar BigQuery ({project_id}.{dataset}.{table}): {exc}"
        ) from exc

    for row in results:
        return {
            "nome": row.nome,
            "cargo": row.cargo,
            "equipe": row.equipe,
            "digisac_user_id": row.digisac_user_id,
        }

    raise ColaboradorNaoEncontrado(
        f"Colaborador com email {email} não encontrado na tabela {project_id}.{dataset}.{table}"
    )