#!/bin/bash
echo "🚀 Iniciando deploy automático do NiverSigloc..."

echo "📥 Puxando código do GitHub..."
git pull origin main

echo "📦 Construindo imagem Docker..."
docker build -t niversiglo .

echo "🛑 Parando e removendo container antigo..."
docker rm -f niversigloc || true

echo "▶️ Iniciando novo container..."
docker run -d --name niversigloc --env-file .env -p 8090:8090 --restart always niversiglo

echo "✅ Deploy concluído com sucesso!"
docker ps | grep niversigloc
