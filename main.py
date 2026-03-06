"""
Voice Agent con Simli Avatar - Backend FastAPI
Pipeline: OpenAI Whisper STT → OpenAI GPT-4o-mini → ElevenLabs TTS (PCM16) → Simli Avatar
Todo en streaming via WebSocket para latencia minima
"""

import os
import io
import json
import re
import base64
import asyncio
import logging
import secrets
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pydantic import BaseModel, Field
import httpx
from openai import AsyncOpenAI
from livekit.api import AccessToken, VideoGrants

# ──────────────────────────────────────────────
# Configuracion
# ──────────────────────────────────────────────
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
SIMLI_API_KEY = os.getenv("SIMLI_API_KEY", "")
SIMLI_FACE_ID = os.getenv("SIMLI_FACE_ID", "")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")
AGENT_NAME = os.getenv("AGENT_NAME", "Asistente Virtual")
AGENT_LANGUAGE = os.getenv("AGENT_LANGUAGE", "es")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice-agent")

# ──────────────────────────────────────────────
# Cargar contexto del producto
# ──────────────────────────────────────────────
def load_product_context():
    context = ""
    docs_dir = Path("docs")
    if docs_dir.exists():
        for pattern in ["*.txt", "*.md"]:
            for f in docs_dir.glob(pattern):
                content = f.read_text(encoding="utf-8").strip()
                if content:
                    context += f"\n--- {f.name} ---\n{content}\n"
    return context

PRODUCT_CONTEXT = load_product_context()

SYSTEM_PROMPT = f"""Eres el Asistente Oficial de Biowel. Tu nombre es {AGENT_NAME}.

Reglas estrictas:
- Solo puedes responder preguntas relacionadas con Biowel
- Solo debes usar la informacion oficial de Biowel que tengas disponible
- Si alguien te pregunta sobre algo que no esta relacionado con Biowel, responde amablemente que solo puedes ayudar con temas de Biowel
- OBLIGATORIO: Responde UNICA y EXCLUSIVAMENTE en español - espanol latinoamericano. NUNCA respondas en otro idioma bajo ninguna circunstancia, sin importar en que idioma te escriban.
- Se amable, entusiasta y profesional
- Usa un tono conversacional y natural

{f'Informacion oficial de Biowel:{PRODUCT_CONTEXT}' if PRODUCT_CONTEXT else 'No hay informacion de producto cargada aun. Responde de forma general y amable sobre Biowel.'}"""

# ──────────────────────────────────────────────
# FastAPI App + OpenAI Client
# ──────────────────────────────────────────────
app = FastAPI(title="Voice Agent con Simli Avatar")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


# ──────────────────────────────────────────────
# Modelo para request de token
# ──────────────────────────────────────────────
class TokenRequest(BaseModel):
    model_config = {"populate_by_name": True}
    room_name: str = Field(
        default="stand-biowel",
        alias="roomName",
        pattern=r"^[a-zA-Z0-9_-]{1,50}$",
    )

# ──────────────────────────────────────────────
# Endpoints REST
# ──────────────────────────────────────────────
@app.get("/")
async def root():
    return FileResponse("static/index.html")

@app.get("/api/config")
async def get_config():
    """Configuracion publica para el frontend (solo lo necesario)"""
    return JSONResponse({
        "agent_name": AGENT_NAME,
        "agent_language": AGENT_LANGUAGE,
        "has_openai": bool(OPENAI_API_KEY),
        "has_elevenlabs": bool(ELEVENLABS_API_KEY),
        "has_simli": bool(SIMLI_API_KEY),
        "simli_api_key": SIMLI_API_KEY,
        "simli_face_id": SIMLI_FACE_ID,
        "livekit_url": LIVEKIT_URL,
    })

# ──────────────────────────────────────────────
# Token LiveKit (POST)
# ──────────────────────────────────────────────
@app.post("/api/token")
async def create_token(body: TokenRequest):
    """Genera un token de LiveKit para que el frontend se conecte a la sala."""
    if not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        return JSONResponse(
            status_code=500,
            content={"error": "LiveKit not configured"},
        )

    identity = f"stand-user-{secrets.token_hex(4)}"

    token = (
        AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name("Visitante Stand")
        .with_ttl(timedelta(hours=6))
        .with_grants(VideoGrants(
            room_join=True,
            room=body.room_name,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
        ))
        .to_jwt()
    )

    logger.info(f"Token generado room={body.room_name} identity={identity}")

    return JSONResponse({
        "token": token,
        "url": LIVEKIT_URL,
        "roomName": body.room_name,
        "identity": identity,
    })

# ──────────────────────────────────────────────
# STT con OpenAI Whisper
# ──────────────────────────────────────────────
async def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/webm") -> str:
    """Transcribe audio usando OpenAI Whisper"""
    if not openai_client:
        return ""
    try:
        # Determinar extension segun mime type
        ext_map = {
            "audio/webm": "webm",
            "audio/mp4": "mp4",
            "audio/wav": "wav",
            "audio/mpeg": "mp3",
            "audio/ogg": "ogg",
        }
        ext = ext_map.get(mime_type, "webm")

        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = f"audio.{ext}"

        transcript = await openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="es",
            prompt="Transcripcion en espanol de una conversacion sobre Biowel, software de gestion clinica.",
        )
        text = transcript.text.strip()

        # Filtrar transcripciones que no sean en espanol (Whisper a veces detecta chino u otros idiomas con ruido)
        if text and re.search(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]', text):
            logger.warning(f"Whisper devolvio texto no-espanol, descartando: {text[:50]}")
            return ""

        return text
    except Exception as e:
        logger.error(f"Whisper STT error: {e}")
        return ""

# ──────────────────────────────────────────────
# LLM Streaming con OpenAI GPT-4o-mini
# ──────────────────────────────────────────────
async def stream_llm_response(messages):
    """Genera respuesta del LLM token por token"""
    if not openai_client:
        yield "Lo siento, el servicio de IA no esta configurado."
        return
    try:
        stream = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=2048,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
    except Exception as e:
        logger.error(f"LLM error: {e}")
        yield "Lo siento, tuve un problema procesando tu pregunta."

# ──────────────────────────────────────────────
# TTS Streaming PCM16 (ElevenLabs)
# ──────────────────────────────────────────────
async def stream_tts_pcm(text):
    """
    Genera audio TTS en formato PCM16 a 16kHz desde ElevenLabs.
    Este formato es compatible directamente con Simli.
    """
    if not ELEVENLABS_API_KEY:
        logger.warning("ElevenLabs API key no configurada")
        return

    url = (
        f"https://api.elevenlabs.io/v1/text-to-speech/"
        f"{ELEVENLABS_VOICE_ID}/stream?output_format=pcm_16000"
    )
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.5,
            "use_speaker_boost": True,
        },
    }

    try:
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST", url, headers=headers, json=payload, timeout=30.0
            ) as response:
                if response.status_code == 200:
                    async for chunk in response.aiter_bytes(chunk_size=4096):
                        if chunk:
                            yield chunk
                else:
                    body = await response.aread()
                    logger.error(
                        f"ElevenLabs error {response.status_code}: {body[:200]}"
                    )
    except Exception as e:
        logger.error(f"TTS error: {e}")

# ──────────────────────────────────────────────
# WebSocket - Pipeline principal
# ──────────────────────────────────────────────
@app.websocket("/ws/agent")
async def websocket_agent(ws: WebSocket):
    await ws.accept()
    conversation_history = []
    logger.info("Cliente conectado al WebSocket")

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            # Keep-alive
            if msg_type == "ping":
                await ws.send_json({"type": "pong"})
                continue

            # Audio blob del usuario (grabado en el frontend)
            if msg_type == "audio_blob":
                audio_b64 = data.get("data", "")
                mime_type = data.get("mime_type", "audio/webm")

                if not audio_b64:
                    continue

                # Decodificar audio
                audio_bytes = base64.b64decode(audio_b64)
                logger.info(f"Audio recibido: {len(audio_bytes)} bytes ({mime_type})")

                # ── Paso 1: STT con Whisper ──
                await ws.send_json({"type": "status", "status": "transcribing"})
                user_text = await transcribe_audio(audio_bytes, mime_type)

                if not user_text:
                    await ws.send_json({"type": "status", "status": "ready"})
                    await ws.send_json({
                        "type": "error",
                        "message": "No se pudo entender el audio. Intenta de nuevo.",
                    })
                    continue

                logger.info(f"Usuario: {user_text}")

                # Enviar transcripcion al frontend
                await ws.send_json({
                    "type": "transcript",
                    "text": user_text,
                })

                # Agregar a historial
                conversation_history.append(
                    {"role": "user", "content": user_text}
                )
                # Mantener ultimos 6 turnos (12 mensajes)
                if len(conversation_history) > 12:
                    conversation_history = conversation_history[-12:]

                # ── Paso 2: LLM con GPT-4o-mini ──
                await ws.send_json({"type": "status", "status": "thinking"})

                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT}
                ] + conversation_history

                full_response = ""
                current_sentence = ""
                sentence_punctuation = {".", "!", "?"}

                async for token in stream_llm_response(messages):
                    full_response += token
                    current_sentence += token

                    # Token al frontend para display en tiempo real
                    await ws.send_json({"type": "token", "token": token})

                    # Detectar fin de oracion para TTS por chunks
                    stripped = current_sentence.rstrip()
                    if stripped and stripped[-1] in sentence_punctuation:
                        sentence = current_sentence.strip()
                        if sentence and len(sentence) > 20:
                            # ── Paso 3: TTS con ElevenLabs ──
                            await ws.send_json(
                                {"type": "status", "status": "speaking"}
                            )
                            async for pcm_chunk in stream_tts_pcm(sentence):
                                pcm_b64 = base64.b64encode(pcm_chunk).decode()
                                await ws.send_json({
                                    "type": "audio_chunk",
                                    "format": "pcm16",
                                    "sample_rate": 16000,
                                    "data": pcm_b64,
                                })
                        current_sentence = ""

                # Procesar texto restante
                remaining = current_sentence.strip()
                if remaining and len(remaining) > 3:
                    await ws.send_json(
                        {"type": "status", "status": "speaking"}
                    )
                    async for pcm_chunk in stream_tts_pcm(remaining):
                        pcm_b64 = base64.b64encode(pcm_chunk).decode()
                        await ws.send_json({
                            "type": "audio_chunk",
                            "format": "pcm16",
                            "sample_rate": 16000,
                            "data": pcm_b64,
                        })

                # Senales de finalizacion
                await ws.send_json({
                    "type": "response_text_done",
                    "text": full_response,
                })
                await ws.send_json({"type": "audio_done"})
                await ws.send_json({"type": "status", "status": "ready"})

                # Agregar respuesta al historial
                conversation_history.append(
                    {"role": "assistant", "content": full_response}
                )
                logger.info(f"Agente: {full_response[:80]}...")

    except WebSocketDisconnect:
        logger.info("Cliente desconectado")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")

# ──────────────────────────────────────────────
# Archivos estaticos
# ──────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

# ──────────────────────────────────────────────
# Inicio
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    logger.info(f"Iniciando {AGENT_NAME}...")
    logger.info(f"OpenAI:     {'OK' if OPENAI_API_KEY else 'FALTA'}")
    logger.info(f"ElevenLabs: {'OK' if ELEVENLABS_API_KEY else 'FALTA'}")
    logger.info(f"Simli:      {'OK' if SIMLI_API_KEY else 'FALTA'}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
