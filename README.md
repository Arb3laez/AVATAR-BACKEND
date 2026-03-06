# Biowel Back - Agente Avatar LiveKit + API REST

Agente de voz con avatar digital para Biowel. Incluye API REST (FastAPI) para generacion de tokens y configuracion, mas el worker de LiveKit Agents.

## Arquitectura

```
[Frontend] --POST /api/token--> [Este Backend (FastAPI)] --genera JWT-->
[Frontend] --WebRTC con token--> [LiveKit Server] <-- [Agent Worker]
```

## Estructura

```
biowel-back/
├── main.py             <- API REST (FastAPI) - Token + Config
├── agent.py            <- Agente LiveKit (OpenAI Realtime + Simli Avatar)
├── docs/
│   └── producto.txt    <- Contexto del producto
├── static/
│   └── index.html      <- UI basica
├── requirements.txt
├── Dockerfile
├── .env.example
└── .gitignore
```

---

## API REST - Endpoints

### GET /api/config

Retorna configuracion publica del agente.

**Request:**
```
GET http://tu-servidor:8000/api/config
```

**Response (200):**
```json
{
  "agent_name": "Asistente Virtual",
  "agent_language": "es",
  "has_openai": true,
  "has_elevenlabs": false,
  "has_simli": true,
  "simli_api_key": "...",
  "simli_face_id": "...",
  "livekit_url": "wss://diego-tc43cwwh.livekit.cloud"
}
```

---

### POST /api/token

Genera un token JWT de LiveKit para que el frontend se conecte a una sala.

**Request:**
```
POST http://tu-servidor:8000/api/token
Content-Type: application/json
```

**Body (acepta ambos formatos):**
```json
{ "roomName": "stand-biowel" }
```
```json
{ "room_name": "stand-biowel" }
```
Si no envias body, usa `"stand-biowel"` por defecto.

**Response (200):**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "url": "wss://diego-tc43cwwh.livekit.cloud",
  "roomName": "stand-biowel",
  "identity": "stand-user-c9a52e01"
}
```

**Errores:**
| Codigo | Descripcion |
|--------|-------------|
| 500 | `{"error": "LiveKit not configured"}` — Faltan LIVEKIT_API_KEY o LIVEKIT_API_SECRET |
| 422 | Validation Error — roomName invalido (solo alfanumerico, guiones, max 50 chars) |

---

### WebSocket /ws/agent

Pipeline de voz en tiempo real: STT (Whisper) -> LLM (GPT-4o-mini) -> TTS (ElevenLabs).

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

---

### Swagger UI

FastAPI genera documentacion interactiva automaticamente:
```
http://tu-servidor:8000/docs
```

---

## Como exponer la API

### 1. Local (desarrollo)

```bash
python main.py
# API disponible en http://localhost:8000
# Docs en http://localhost:8000/docs
```

### 2. Red local (otros dispositivos en tu WiFi)

Ya funciona con `host="0.0.0.0"`. Busca tu IP local:
```bash
# Windows
ipconfig
# Linux/Mac
ifconfig
```
Accede desde otro dispositivo: `http://192.168.x.x:8000/api/token`

### 3. Docker (local o servidor)

```bash
docker build -t biowel-api .
docker run --env-file .env -p 8000:8000 -p 8081:8081 biowel-api
```

### 4. AWS ECS/Fargate

```bash
# Build y push a ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin TU-ACCOUNT.dkr.ecr.us-east-1.amazonaws.com

docker build -t biowel-api .
docker tag biowel-api:latest TU-ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/biowel-api:latest
docker push TU-ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/biowel-api:latest
```

En la Task Definition de ECS agregar las variables de entorno y exponer puerto 8000.

### 5. AWS EC2 directo

```bash
ssh ubuntu@tu-ec2-ip
git clone https://github.com/TU-USUARIO/biowel-back.git && cd biowel-back
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && nano .env  # poner keys reales

# Ejecutar
python main.py  # o con systemd para que corra 24/7
```

#### Systemd Service (EC2, corre 24/7)

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

### 6. Nginx reverse proxy (SSL/dominio)

```nginx
server {
    listen 443 ssl;
    server_name api.biowel.com;

    ssl_certificate /etc/letsencrypt/live/api.biowel.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.biowel.com/privkey.pem;

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
sudo certbot --nginx -d api.biowel.com
```

### 7. Caddy reverse proxy (SSL automatico)

```
api.biowel.com {
    reverse_proxy localhost:8000
}
```

### 8. ngrok (exponer temporal para pruebas)

```bash
ngrok http 8000
# Te da una URL publica tipo https://xxxx.ngrok-free.app
```

---

## Ejemplo de uso desde el frontend

```javascript
// Obtener token
const res = await fetch("https://api.biowel.com/api/token", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ roomName: "stand-biowel" }),
});
const { token, url, roomName, identity } = await res.json();

// Conectar a LiveKit con el token
const room = new Room();
await room.connect(url, token);
```

---

## Variables de Entorno

| Variable | Requerida | Descripcion |
|----------|-----------|-------------|
| `LIVEKIT_URL` | Si | URL del servidor LiveKit (wss://...) |
| `LIVEKIT_API_KEY` | Si | API Key de LiveKit |
| `LIVEKIT_API_SECRET` | Si | API Secret de LiveKit |
| `OPENAI_API_KEY` | Si | Key de OpenAI (Realtime + Whisper) |
| `SIMLI_API_KEY` | No | Key de Simli (avatar) |
| `SIMLI_FACE_ID` | No | Face ID de Simli |
| `ELEVENLABS_API_KEY` | No | Key de ElevenLabs (TTS en main.py) |
| `ELEVENLABS_VOICE_ID` | No | Voice ID de ElevenLabs |
| `AGENT_NAME` | No | Nombre del agente (default: "Asistente Virtual") |
| `AGENT_LANGUAGE` | No | Idioma (default: "es") |

## Setup Local

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
