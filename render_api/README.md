# Render API do Vobila

Este diretório contém uma primeira API web separada do `sistema.py` para publicar no Render.

## O que ela já faz

- `GET /health`
- `GET /produtos`
- `GET /delivery-web-config`
- `GET /clientes`
- `GET /pedidos-status`
- `POST /cliente`
- `POST /pedido`
- `POST /pix`
- `POST /pix-status`

## Limitações desta primeira versão

- Usa arquivos JSON locais em `render_api/data`
- Não conversa com o PDV desktop automaticamente
- O status do PIX ainda é básico
- Em produção, o ideal é usar banco de dados ou disco persistente

## Rodar localmente

```bash
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Configuração no Render

- Root Directory: `render_api`
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

## Próximos passos

1. Subir esta API no GitHub
2. Criar o Web Service no Render
3. Testar a URL `/health`
4. Apontar o `restaurantevobila` para a URL pública da API
