FROM python:3.11-slim

WORKDIR /app

# Instala dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código (credenciais vêm de variáveis de ambiente, nunca da imagem)
COPY . .

# Porta que o Cloud Run usa
ENV PORT=8080
EXPOSE 8080

# Comando pra rodar
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]