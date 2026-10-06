#!/bin/bash
# ---------------------------------------------------------------------------
# Cria o dataset "rh" e a tabela "colaboradores" no BigQuery via linha de comando.
#
# Pré-requisitos:
#   1. Google Cloud SDK instalado (traz o comando `bq` junto):
#        curl https://sdk.cloud.google.com | bash
#        exec -l $SHELL
#   2. Autenticado:
#        gcloud auth login
#        gcloud config set project SEU_PROJECT_ID
#
# Uso:
#   PROJECT_ID=seu-projeto-gcp ./setup_bigquery.sh
# ---------------------------------------------------------------------------
set -e

PROJECT_ID="${PROJECT_ID:?defina PROJECT_ID, ex: PROJECT_ID=meu-projeto ./setup_bigquery.sh}"
DATASET="rh"
TABLE="colaboradores"
LOCATION="southamerica-east1"

echo "==> Criando dataset ${PROJECT_ID}:${DATASET} (região ${LOCATION})..."
bq mk --dataset --location="${LOCATION}" "${PROJECT_ID}:${DATASET}"

echo "==> Criando tabela ${DATASET}.${TABLE}..."
bq mk --table \
  "${PROJECT_ID}:${DATASET}.${TABLE}" \
  "$(dirname "$0")/colaboradores_schema.json"

echo "==> Pronto. Tabela criada, vazia. Pra inserir os colaboradores:"
echo ""
echo "  bq query --use_legacy_sql=false '"
echo "  INSERT INTO \`${PROJECT_ID}.${DATASET}.${TABLE}\`"
echo "    (email, nome, cargo, equipe, digisac_user_id, ativo)"
echo "  VALUES"
echo "    (\"joao@empresa.com\", \"João Silva\", \"Vendedor\", \"Equipe A\", \"id-no-digisac\", true)"
echo "  '"
echo ""
echo "Ou carregue de um CSV (colunas na mesma ordem do schema, sem cabeçalho):"
echo "  bq load --source_format=CSV ${PROJECT_ID}:${DATASET}.${TABLE} colaboradores.csv"
