"""
Marketing Studio — FastAPI backend
==================================

Backend que conecta a UI do Marketing Studio (TanStack/React) aos modelos
generativos do repositório Open-Generative-AI:
    https://github.com/Anil-matcha/Open-Generative-AI

Rotas expostas:
    POST /api/generate-script   -> gera copy do anúncio (hook/body/CTA)
    POST /api/generate-video    -> pipeline principal produto + avatar + prompt -> vídeo
    POST /api/tools/url-to-ad   -> faz scrape de uma URL (Shopify/Amazon) e devolve dados
    GET  /api/jobs/{job_id}     -> consulta status de um job de vídeo
    GET  /health                -> healthcheck

>>> ONDE INSERIR CHAVES DE API <<<
    Tudo é lido de variáveis de ambiente (.env). Procure por blocos marcados
    com "# >>> API KEY". As principais são:
        OPENAI_API_KEY        -> LLM para o gerador de script
        MUAPI_API_KEY         -> MuAPI (geração de vídeo/imagem)
        REPLICATE_API_TOKEN   -> opcional, modelos hospedados
        HF_TOKEN              -> opcional, modelos HuggingFace
        OPEN_GEN_AI_PATH      -> caminho local para o repo Open-Generative-AI

>>> ONDE PLUGAR O REPO Open-Generative-AI <<<
    Procure por "# >>> OPEN-GENERATIVE-AI HOOK".
"""

from __future__ import annotations

import os
import sys
import uuid
import asyncio
import logging
from pathlib import Path
from typing import Literal, Optional

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, HttpUrl

# ------------------------------------------------------------------ #
# Config / env
# ------------------------------------------------------------------ #
load_dotenv()

# >>> API KEY: chaves usadas pelo backend ------------------------------------
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY", "")
MUAPI_API_KEY       = os.getenv("MUAPI_API_KEY", "")        # <-- sua chave MuAPI
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")
HF_TOKEN            = os.getenv("HF_TOKEN", "")
# ---------------------------------------------------------------------------

# >>> OPEN-GENERATIVE-AI HOOK ------------------------------------------------
# Caminho local onde você clonou https://github.com/Anil-matcha/Open-Generative-AI
# Ex.: export OPEN_GEN_AI_PATH=/Users/voce/code/Open-Generative-AI
OPEN_GEN_AI_PATH = os.getenv("OPEN_GEN_AI_PATH", "")
if OPEN_GEN_AI_PATH and Path(OPEN_GEN_AI_PATH).exists():
    sys.path.insert(0, OPEN_GEN_AI_PATH)
    # Agora você pode importar livremente módulos do repo, por exemplo:
    # from text_to_video import generate_video as ogai_text_to_video
    # from virtual_tryon import fuse_product_avatar
# ---------------------------------------------------------------------------

_default_origins = "http://localhost:5173,http://localhost:8080,http://localhost:3000"
_env_origins = os.getenv("ALLOWED_ORIGINS", _default_origins)
ALLOWED_ORIGINS = [o.strip() for o in _env_origins.split(",") if o.strip()]
# Regex que libera qualquer subdomínio *.lovable.app (preview + published)
ALLOWED_ORIGIN_REGEX = os.getenv("ALLOWED_ORIGIN_REGEX", r"https://.*\.lovable\.app")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("marketing-studio")

# ------------------------------------------------------------------ #
# FastAPI app
# ------------------------------------------------------------------ #
app = FastAPI(
    title="Marketing Studio API",
    version="0.1.0",
    description="Backend de geração de vídeos publicitários (Higgsfield-like).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=ALLOWED_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------ #
# In-memory job store (troque por Redis/Postgres em produção)
# ------------------------------------------------------------------ #
JOBS: dict[str, dict] = {}

# ------------------------------------------------------------------ #
# Schemas
# ------------------------------------------------------------------ #
StyleLiteral = Literal["unboxing", "hook", "setting"]


class GenerateScriptIn(BaseModel):
    product_url: Optional[HttpUrl] = None
    product_name: Optional[str] = None
    description: Optional[str] = None
    tone: str = Field(default="energetic", description="energetic | calm | luxury | funny")


class GenerateScriptOut(BaseModel):
    hook: str
    body: str
    cta: str


class GenerateVideoIn(BaseModel):
    prompt: str
    style: StyleLiteral = "hook"
    product_image_url: Optional[HttpUrl] = None
    avatar_image_url: Optional[HttpUrl] = None
    duration_seconds: int = Field(default=5, ge=3, le=15)
    aspect_ratio: str = Field(default="9:16")


class GenerateVideoOut(BaseModel):
    job_id: str
    status: Literal["queued", "processing", "done", "failed"]
    preview_url: Optional[str] = None


class UrlToAdIn(BaseModel):
    url: HttpUrl


class UrlToAdOut(BaseModel):
    url: HttpUrl
    title: str
    description: str
    images: list[str]


# ------------------------------------------------------------------ #
# Helpers — wrappers para o repo Open-Generative-AI / MuAPI
# ------------------------------------------------------------------ #
async def _llm_generate_copy(payload: GenerateScriptIn) -> GenerateScriptOut:
    """
    Gera copy do anúncio.
    >>> OPEN-GENERATIVE-AI HOOK:
        Substitua o bloco abaixo por uma chamada real ao módulo de LLM do repo,
        por exemplo:
            from text_generation import generate
            text = generate(prompt=..., api_key=OPENAI_API_KEY)
    """
    if not OPENAI_API_KEY:
        # fallback determinístico se a chave não foi configurada
        base = payload.product_name or (str(payload.product_url) if payload.product_url else "este produto")
        return GenerateScriptOut(
            hook=f"Pare de rolar — {base} muda tudo.",
            body="Mostre o produto em ação, com o avatar reagindo de forma autêntica.",
            cta="Toque para garantir o seu hoje ✦",
        )

    # Exemplo de chamada real à OpenAI (descomente quando quiser usar):
    # async with httpx.AsyncClient(timeout=60) as client:
    #     r = await client.post(
    #         "https://api.openai.com/v1/chat/completions",
    #         headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},   # >>> API KEY
    #         json={
    #             "model": "gpt-4o-mini",
    #             "messages": [
    #                 {"role": "system", "content": "Você é copywriter de anúncios curtos."},
    #                 {"role": "user", "content": f"Crie hook/body/CTA para: {payload.model_dump()}"},
    #             ],
    #         },
    #     )
    #     data = r.json()
    #     # parse o conteúdo e devolva GenerateScriptOut(...)

    return GenerateScriptOut(
        hook="Hook gerado por LLM.",
        body="Body gerado por LLM.",
        cta="CTA gerado por LLM.",
    )


async def _muapi_generate_video(job_id: str, payload: GenerateVideoIn) -> None:
    """
    Dispara a geração de vídeo na MuAPI (ou em qualquer provider equivalente)
    e atualiza JOBS[job_id] conforme o progresso.

    >>> API KEY: usa MUAPI_API_KEY
    >>> OPEN-GENERATIVE-AI HOOK: para rodar 100% local, troque este bloco por
        uma chamada aos scripts de difusão image-to-video do repo.
    """
    JOBS[job_id]["status"] = "processing"
    try:
        if not MUAPI_API_KEY:
            # Modo simulado — útil para desenvolvimento sem chave
            await asyncio.sleep(2)
            JOBS[job_id].update(status="done", preview_url="https://example.com/mock.mp4")
            return

        async with httpx.AsyncClient(timeout=120) as client:
            # NOTE: ajuste endpoint/payload conforme a doc atual da MuAPI.
            r = await client.post(
                "https://api.muapi.ai/v1/video/generate",
                headers={"Authorization": f"Bearer {MUAPI_API_KEY}"},   # >>> API KEY
                json={
                    "prompt": payload.prompt,
                    "style": payload.style,
                    "product_image": str(payload.product_image_url) if payload.product_image_url else None,
                    "avatar_image": str(payload.avatar_image_url) if payload.avatar_image_url else None,
                    "duration": payload.duration_seconds,
                    "aspect_ratio": payload.aspect_ratio,
                },
            )
            r.raise_for_status()
            data = r.json()
            JOBS[job_id].update(
                status="done",
                preview_url=data.get("video_url") or data.get("url"),
                provider_response=data,
            )
    except Exception as exc:  # pragma: no cover
        log.exception("video generation failed")
        JOBS[job_id].update(status="failed", error=str(exc))


# ------------------------------------------------------------------ #
# Routes
# ------------------------------------------------------------------ #
@app.get("/health")
async def health():
    return {
        "ok": True,
        "open_gen_ai_loaded": bool(OPEN_GEN_AI_PATH and Path(OPEN_GEN_AI_PATH).exists()),
        "providers": {
            "openai":    bool(OPENAI_API_KEY),
            "muapi":     bool(MUAPI_API_KEY),
            "replicate": bool(REPLICATE_API_TOKEN),
            "hf":        bool(HF_TOKEN),
        },
    }


@app.post("/api/generate-script", response_model=GenerateScriptOut)
async def generate_script(payload: GenerateScriptIn):
    return await _llm_generate_copy(payload)


@app.post("/api/generate-video", response_model=GenerateVideoOut)
async def generate_video(payload: GenerateVideoIn, background: BackgroundTasks):
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "queued", "input": payload.model_dump(mode="json")}
    background.add_task(_muapi_generate_video, job_id, payload)
    return GenerateVideoOut(job_id=job_id, status="queued", preview_url=None)


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return {"job_id": job_id, **job}


@app.post("/api/tools/url-to-ad", response_model=UrlToAdOut)
async def url_to_ad(payload: UrlToAdIn):
    """
    Faz scrape simples de uma página de produto (Shopify/Amazon/genérico).
    Para sites com JS pesado, troque httpx por playwright.
    """
    try:
        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 MarketingStudioBot"},
        ) as client:
            r = await client.get(str(payload.url))
            r.raise_for_status()
    except Exception as exc:
        raise HTTPException(400, f"failed to fetch url: {exc}")

    soup = BeautifulSoup(r.text, "html.parser")
    title = (soup.title.string or "").strip() if soup.title else ""
    desc_tag = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    description = (desc_tag.get("content") if desc_tag else "") or ""
    images = list({
        img.get("src") for img in soup.find_all("img")
        if img.get("src", "").startswith("http")
    })[:10]

    return UrlToAdOut(url=payload.url, title=title, description=description, images=images)


# ------------------------------------------------------------------ #
# Local dev entrypoint
# ------------------------------------------------------------------ #
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
