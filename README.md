# Biowel Back - Agente Avatar LiveKit

Agente de voz con avatar digital para Biowel. Corre como worker de LiveKit Agents en AWS.

## Arquitectura

```
[Frontend Vercel] → [LiveKit Server AWS] ← [Este Agente AWS]
                         ↕ WebRTC
                    [Usuario Browser]
```

El agente se registra como worker en LiveKit. Cuando un usuario se une a un room desde el frontend, LiveKit asigna automáticamente un job al agente.

## Estructura

```
biowel-back/
├── agent.py            ← Agente LiveKit (OpenAI Realtime + Simli Avatar)
├── docs/
│   └── producto.txt    ← Contexto del producto (lo lee el agente)
├── requirements.txt    ← Dependencias Python
├── Dockerfile          ← Para deploy en AWS ECS/EC2
├── .env.example        ← Template de variables de entorno
└── .gitignore
```

## Requisitos

- Python 3.11+
- Servidor LiveKit corriendo (self-host o cloud)
- API keys: OpenAI, Simli

## Setup Local

```bash
# 1. Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# o en Windows:
venv\Scripts\activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus keys reales

# 4. Ejecutar el agente
python agent.py start
```

### Logs esperados al arrancar

```
INFO: registered worker
INFO: waiting for job request...
```

Cuando un usuario abre el frontend:
```
INFO: received job request for room stand-biowel
INFO: job accepted, joining room...
INFO: Agente Bio iniciado - Facocaribe 2026
```

## Deploy en AWS

### Opción 1: EC2 (más simple)

```bash
# 1. Conectar a la instancia
ssh ubuntu@tu-ec2-ip

# 2. Clonar el repo
git clone https://github.com/TU-USUARIO/biowel-back.git
cd biowel-back

# 3. Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Crear .env
cp .env.example .env
nano .env  # Editar con keys reales

# 5. Ejecutar con systemd (para que corra 24/7)
# Ver sección "Systemd Service" abajo
```

#### Systemd Service (para EC2)

Crear `/etc/systemd/system/biowel-agent.service`:

```ini
[Unit]
Description=Biowel Avatar Agent
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/biowel-back
EnvironmentFile=/home/ubuntu/biowel-back/.env
ExecStart=/home/ubuntu/biowel-back/venv/bin/python agent.py start
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable biowel-agent
sudo systemctl start biowel-agent

# Ver logs
sudo journalctl -u biowel-agent -f
```

### Opción 2: ECS Fargate (más robusto)

```bash
# 1. Build Docker image
docker build -t biowel-agent .

# 2. Push a ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin TU-ACCOUNT-ID.dkr.ecr.us-east-1.amazonaws.com
docker tag biowel-agent:latest TU-ACCOUNT-ID.dkr.ecr.us-east-1.amazonaws.com/biowel-agent:latest
docker push TU-ACCOUNT-ID.dkr.ecr.us-east-1.amazonaws.com/biowel-agent:latest

# 3. Crear Task Definition en ECS con las variables de entorno
# 4. Crear Service en ECS Fargate (desired count: 1)
```

Variables de entorno en la Task Definition:
- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `OPENAI_API_KEY`
- `SIMLI_API_KEY`
- `SIMLI_FACE_ID`

## Variables de Entorno

| Variable | Descripción |
|---|---|
| `LIVEKIT_URL` | URL del servidor LiveKit (wss://livekit.tu-dominio.com) |
| `LIVEKIT_API_KEY` | API Key de LiveKit (generada por el server) |
| `LIVEKIT_API_SECRET` | API Secret de LiveKit (generada por el server) |
| `OPENAI_API_KEY` | Key de OpenAI (para Realtime voice-to-voice) |
| `SIMLI_API_KEY` | Key de Simli (para avatar lip-sync) |
| `SIMLI_FACE_ID` | Face ID de Simli (tu avatar configurado) |

## LiveKit Server (Self-Host en AWS)

El agente necesita un servidor LiveKit corriendo. Instrucciones rápidas:

### Instalar LiveKit Server en EC2

```bash
curl -sSL https://get.livekit.io | bash
livekit-server generate-keys
# Guardar API Key y Secret generados
```

### Puertos a abrir (Security Group)

- **443 TCP** — WebSocket señalización (wss://)
- **7880 TCP** — HTTP API de LiveKit
- **7881 TCP** — WebRTC TCP fallback
- **3478 TCP/UDP** — TURN server
- **50000-60000 UDP** — ICE candidates (WebRTC media)

### Config: /etc/livekit.yaml

```yaml
port: 7880
rtc:
  port_range_start: 50000
  port_range_end: 60000
  tcp_port: 7881
  use_external_ip: true
keys:
  APIxxxxxxxx: secretxxxxxxxx
turn:
  enabled: true
  domain: livekit.tu-dominio.com
  tls_port: 5349
  udp_port: 3478
  external_tls: true
```

### SSL con Caddy

```bash
sudo apt install caddy
```

Caddyfile (`/etc/caddy/Caddyfile`):
```
livekit.tu-dominio.com {
    reverse_proxy localhost:7880
}
```

## Checklist de Pruebas

1. `python agent.py start` → logs: "registered worker"
2. Abrir frontend en Vercel → logs: "received job request"
3. Hablar por micrófono → el agente responde con voz
4. Video del avatar aparece en el frontend
5. Reconexión: cerrar y reabrir el frontend → nuevo job asignado
