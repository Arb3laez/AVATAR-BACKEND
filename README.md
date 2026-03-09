# Bio - Agente Avatar de Biowel

> Avatar digital con IA conversacional para el stand de Biowel en Facocaribe 2026.

**URL en produccion:** https://avatar.biowel.com.co/

---

## Que es Bio

Bio es un agente conversacional con avatar digital que representa a Biowel en el Congreso Internacional de Oftalmologia Facocaribe 2026. Escucha al visitante por voz, genera una respuesta inteligente y la reproduce con voz sintetizada mientras un avatar visual mueve los labios en tiempo real (lip-sync).

**Bio NO es un vendedor.** Es un asesor estrategico digital que:

- Diagnostica las necesidades del visitante segun su perfil (medico, gerencial o estrategico)
- Adapta el discurso automaticamente al tipo de interlocutor
- Conecta la tecnologia de Biowel con indicadores clinicos y financieros
- Genera reflexion estrategica e incentiva la conversacion con el equipo humano presente en el stand
- Genera leads cualificados para el equipo comercial

---

## Arquitectura

El sistema tiene dos componentes que corren en paralelo:

```
                         +---------------------------------------------+
                         |              biowel-back                    |
                         |                                             |
Visitante                |  +-- agent.py (LiveKit Agent) ------------+ |
  habla   --> [Mic] ---> |  |  OpenAI Realtime (STT + LLM + TTS)    | |---> [Simli Avatar]
                         |  |  Simli Avatar (lip-sync)               | |     (video + audio)
                         |  +----------------------------------------+ |
                         |                                             |
Frontend                 |  +-- main.py (FastAPI) -------------------+ |
  web     <-- REST ----> |  |  GET  /           Health check         | |
                         |  |  GET  /api/config  Config publica      | |
                         |  |  POST /api/token   Token LiveKit       | |
                         |  |  WS   /ws/agent    Pipeline de voz     | |
                         |  +----------------------------------------+ |
                         +---------------------------------------------+
```

### agent.py — Agente LiveKit (componente principal)

Pipeline de voz a voz en tiempo real con latencia minima:

| Paso | Tecnologia | Funcion |
|------|-----------|---------|
| 1. Captura de audio | LiveKit + VAD | Detecta cuando el visitante habla |
| 2. STT + LLM + TTS | OpenAI Realtime API | Transcribe, razona y sintetiza voz en un solo pipeline |
| 3. Avatar | Simli | Renderiza video con lip-sync sincronizado al audio |

Configuracion de voz:
- **Voz:** `shimmer` (femenina, OpenAI)
- **Temperatura:** 0.7
- **VAD threshold:** 0.8 (filtra ruido de congreso)
- **Reduccion de ruido:** `far_field` (ambientes ruidosos)
- **Transcripcion:** `gpt-4o-transcribe` en espanol
- **Eagerness:** `low` (no se interrumpe facilmente)

### main.py — API REST + WebSocket (servidor FastAPI)

Provee endpoints REST para el frontend y un pipeline WebSocket alternativo:

| Pipeline WS | Tecnologia | Formato |
|-------------|-----------|---------|
| STT | OpenAI Whisper | audio blob base64 → texto |
| LLM | GPT-4o-mini | streaming token por token |
| TTS | ElevenLabs v2 | PCM16 a 16kHz en chunks |

---

## Comportamiento inteligente

### Deteccion de perfil automatica

Bio clasifica al visitante por sus palabras y adapta la conversacion:

| Perfil | Palabras clave | Enfoque |
|--------|---------------|---------|
| **Medico** | consulta, diagnostico, cirugia, historia clinica | Calidad clinica, eficiencia, seguridad quirurgica |
| **Gerencial** | indicadores, glosas, facturacion, cartera | Reduccion de glosas, control financiero |
| **Estrategico** | rentabilidad, crecimiento, ROI, expansion | Margen operativo, ventaja competitiva |

### Manejo de interrupciones y ruido

Optimizado para ambientes ruidosos de congreso:

- **Interrupcion valida** (el usuario entendio, pregunta algo, se despide) → Bio responde normalmente
- **Interrupcion invalida** (ruido, voces de fondo, frases sin contexto) → Bio ignora y continua donde iba
- Filtro de caracteres no-espanol en Whisper (descarta texto en chino/japones/coreano generado por ruido)

### Manejo de objeciones

| Objecion | Respuesta |
|----------|-----------|
| "Ya tenemos sistema" | Redirige a optimizacion estrategica |
| "Funciona bien asi" | Plantea competitividad futura |
| "Es costoso" | Reenfoca en el costo de la ineficiencia |

### Escalamiento humano

Cuando piden precios, integraciones tecnicas o propuestas formales, Bio escala al equipo humano presente en el stand.

### Idioma

Bio responde **exclusivamente en espanol latinoamericano**, sin importar el idioma en que le hablen.

---

## Estructura del proyecto

```
biowel-back/
├── agent.py                        # Agente LiveKit (OpenAI Realtime + Simli)
├── main.py                         # API REST (FastAPI) + WebSocket pipeline
├── entrypoint.sh                   # Inicia ambos componentes
├── docs/
│   └── producto.txt                # Informacion oficial de Biowel (contexto del agente)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── DOCUMENTACION_AGENTE_BIO.txt    # Documentacion detallada del agente
├── .env.example
└── .gitignore
```

---

## Stack tecnologico

| Capa | Tecnologia |
|------|-----------|
| Backend | Python 3.11, FastAPI, Uvicorn |
| Agente de voz | LiveKit Agents SDK |
| IA (principal) | OpenAI Realtime API (voz a voz) |
| IA (alternativo) | OpenAI Whisper (STT) + GPT-4o-mini (LLM) |
| TTS (alternativo) | ElevenLabs Multilingual v2 |
| Avatar | Simli (lip-sync en tiempo real) |
| Infraestructura | LiveKit (WebRTC), Docker |

---

## API REST — Endpoints

### `GET /`

Health check.

```json
{ "status": "ok", "service": "Biowel Voice Agent API" }
```

### `GET /api/config`

Configuracion publica para el frontend.

```json
{
  "agent_name": "Asistente Virtual",
  "agent_language": "es",
  "has_openai": true,
  "has_elevenlabs": false,
  "has_simli": true,
  "simli_api_key": "...",
  "simli_face_id": "...",
  "livekit_url": "wss://..."
}
```

### `POST /api/token`

Genera un token JWT de LiveKit para conectarse a una sala.

**Body (acepta ambos formatos):**
```json
{ "roomName": "stand-biowel" }
```
```json
{ "room_name": "stand-biowel" }
```

Si no envias body, usa `"stand-biowel"` por defecto.

**Response:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "url": "wss://...",
  "roomName": "stand-biowel",
  "identity": "stand-user-c9a52e01"
}
```

**Errores:**

| Codigo | Descripcion |
|--------|-------------|
| 500 | `{"error": "LiveKit not configured"}` — Faltan LIVEKIT_API_KEY o LIVEKIT_API_SECRET |
| 422 | Validation Error — roomName invalido (solo alfanumerico, guiones, max 50 chars) |

### `WebSocket /ws/agent`

Pipeline de voz en tiempo real: STT (Whisper) → LLM (GPT-4o-mini) → TTS (ElevenLabs).

**Conexion:**
```javascript
const ws = new WebSocket("ws://tu-servidor:8000/ws/agent");
```

**Enviar audio:**
```json
{ "type": "audio_blob", "data": "<base64>", "mime_type": "audio/webm" }
```

**Mensajes que recibe:**
```json
{ "type": "transcript", "text": "Hola, que es Biowel?" }
{ "type": "token", "token": "Biowel" }
{ "type": "audio_chunk", "format": "pcm16", "sample_rate": 16000, "data": "<base64>" }
{ "type": "status", "status": "transcribing|thinking|speaking|ready" }
{ "type": "response_text_done", "text": "Respuesta completa..." }
{ "type": "audio_done" }
```

**Swagger UI:** `http://tu-servidor:8000/docs`

---

## Ejemplo de uso desde el frontend

```javascript
// 1. Obtener token
const res = await fetch("https://avatar.biowel.com.co/api/token", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ roomName: "stand-biowel" }),
});
const { token, url, roomName, identity } = await res.json();

// 2. Conectar a LiveKit con el token
const room = new Room();
await room.connect(url, token);
```

---

## Variables de entorno

| Variable | Requerida | Descripcion |
|----------|-----------|-------------|
| `LIVEKIT_URL` | Si | URL del servidor LiveKit (`wss://...`) |
| `LIVEKIT_API_KEY` | Si | API Key de LiveKit |
| `LIVEKIT_API_SECRET` | Si | API Secret de LiveKit |
| `OPENAI_API_KEY` | Si | Key de OpenAI (Realtime + Whisper + GPT) |
| `SIMLI_API_KEY` | No | Key de Simli (avatar) |
| `SIMLI_FACE_ID` | No | Face ID de Simli |
| `ELEVENLABS_API_KEY` | No | Key de ElevenLabs (TTS en pipeline WebSocket) |
| `ELEVENLABS_VOICE_ID` | No | Voice ID de ElevenLabs |
| `AGENT_NAME` | No | Nombre del agente (default: `"Asistente Virtual"`) |
| `AGENT_LANGUAGE` | No | Idioma (default: `"es"`) |

---

## Setup local

```bash
# 1. Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables
cp .env.example .env
# Editar .env con tus keys reales

# 4. Ejecutar API
python main.py
# API en http://localhost:8000
# Docs en http://localhost:8000/docs

# 5. Ejecutar agente LiveKit (en otra terminal)
python agent.py start
```

---

## Despliegue

### Docker

```bash
docker build -t biowel-api .
docker run --env-file .env -p 8000:8000 -p 8081:8081 biowel-api
```

### Docker Compose

```bash
docker-compose up --build
```

Puertos expuestos:
- `8000` — API REST (FastAPI)
- `8081` — Health check del agente LiveKit

### AWS ECS/Fargate

```bash
# Build y push a ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin TU-ACCOUNT.dkr.ecr.us-east-1.amazonaws.com

docker build -t biowel-api .
docker tag biowel-api:latest TU-ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/biowel-api:latest
docker push TU-ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/biowel-api:latest
```

En la Task Definition de ECS agregar las variables de entorno y exponer puerto 8000.

### AWS EC2

```bash
ssh ubuntu@tu-ec2-ip
git clone https://github.com/TU-USUARIO/biowel-back.git && cd biowel-back
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && nano .env  # poner keys reales
python main.py
```

#### Systemd (corre 24/7 en EC2)

Crear `/etc/systemd/system/biowel-api.service`:

```ini
[Unit]
Description=Biowel API + Agent
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/biowel-back
EnvironmentFile=/home/ubuntu/biowel-back/.env
ExecStart=/home/ubuntu/biowel-back/venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable biowel-api
sudo systemctl start biowel-api
sudo journalctl -u biowel-api -f  # ver logs
```

### Nginx reverse proxy (SSL)

```nginx
server {
    listen 443 ssl;
    server_name avatar.biowel.com.co;

    ssl_certificate /etc/letsencrypt/live/avatar.biowel.com.co/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/avatar.biowel.com.co/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d avatar.biowel.com.co
```

### Caddy (SSL automatico)

```
avatar.biowel.com.co {
    reverse_proxy localhost:8000
}
```

### ngrok (pruebas temporales)

```bash
ngrok http 8000
```
