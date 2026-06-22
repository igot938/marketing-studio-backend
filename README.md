# Marketing Studio — Backend (FastAPI)

Backend que serve a UI Higgsfield-like e orquestra geração de vídeo/copy
usando o repositório [Open-Generative-AI](https://github.com/Anil-matcha/Open-Generative-AI)
e provedores como **MuAPI**, OpenAI, Replicate, HuggingFace.

## 1. Pré-requisitos
- Python 3.10+
- `git`
- (Opcional) GPU + CUDA se for rodar modelos locais do Open-Generative-AI

## 2. Setup local

```bash
# 1. Crie uma pasta e copie main.py, requirements.txt e .env.example para dentro
mkdir marketing-studio-backend && cd marketing-studio-backend

# 2. Ambiente virtual
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate

# 3. Dependências
pip install -r requirements.txt

# 4. Clone o repo open-source (em qualquer lugar)
git clone https://github.com/Anil-matcha/Open-Generative-AI ~/Open-Generative-AI

# 5. Configure variáveis de ambiente
cp .env.example .env
# Edite .env e preencha:
#   OPENAI_API_KEY=...
#   MUAPI_API_KEY=...                       <-- sua chave MuAPI
#   OPEN_GEN_AI_PATH=/Users/voce/Open-Generative-AI
```

## 3. Rodar

```bash
uvicorn main:app --reload --port 8000
# Docs interativas: http://localhost:8000/docs
# Health:           http://localhost:8000/health
```

## 4. Onde inserir suas chaves no código

Tudo é carregado de `.env`. Os pontos de injeção no `main.py` estão marcados
com comentários:

- `# >>> API KEY` — linhas onde a chave é lida ou enviada nos headers
  (`OPENAI_API_KEY`, `MUAPI_API_KEY`, etc).
- `# >>> OPEN-GENERATIVE-AI HOOK` — onde você troca o stub pelas funções
  reais importadas do repositório clonado (ex.: `from text_to_video import
  generate_video`).

## 5. Conectar com o frontend (TanStack Start)

No frontend, edite `src/lib/marketing.functions.ts` e faça os handlers
encaminharem para o FastAPI:

```ts
const PY = process.env.PY_BACKEND_URL ?? "http://localhost:8000";
const r = await fetch(`${PY}/api/generate-video`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});
return await r.json();
```

## 6. Endpoints

| Método | Rota                      | Descrição                              |
|-------:|---------------------------|----------------------------------------|
| POST   | `/api/generate-script`    | Gera hook/body/CTA                     |
| POST   | `/api/generate-video`     | Cria job de vídeo (assíncrono)         |
| GET    | `/api/jobs/{job_id}`      | Consulta status do job                 |
| POST   | `/api/tools/url-to-ad`    | Scrape de URL de produto               |
| GET    | `/health`                 | Healthcheck + providers configurados   |
