from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import time
import requests  # type: ignore
import json
import os
from threading import Lock

app = FastAPI()

LOG_FILE = "uses.json"
REQUEST_LIMIT = 10
TIME_WINDOW = 60
BLOCK_TIME = 300
LOCK = Lock()


# ---- Funções do Log ----
def load_log():
    if not os.path.exists(LOG_FILE):
        return {}
    try:
        with open(LOG_FILE, "r") as f:
            content = f.read().strip()
            if not content:
                return {}
            return json.loads(content)
    except json.JSONDecodeError:
        return {}

def save_log(log):
    with open(LOG_FILE, "w") as f:
        json.dump(log, f)


# ---- Config do middleware ----
@app.middleware("http")
async def rate_limiter(request: Request, call_next):
    client_ip = request.headers.get("X-Forwarded-For")
    if client_ip:
        client_ip = client_ip.split(",")[0]
    else:
        client_ip = request.client.host

    now = time.time()

    with LOCK:
        log = load_log()
        entry = log.get(client_ip, {"requests": [], "blocked_until": 0})

        # Verificação se está bloqueado
        if entry.get("blocked_until", 0) > now:
            return JSONResponse(
                status_code=429,
                content={"detail": "IP bloqueado por uso excessivo. Tente novamente mais tarde."}
            )

        # Remove requisições fora do intervalo de tempo
        entry["requests"] = [ts for ts in entry["requests"] if now - ts <= TIME_WINDOW]

        # Adiciona a requisição atual
        entry["requests"].append(now)

        # Verifica se ultrapassou o limite
        if len(entry["requests"]) > REQUEST_LIMIT:
            entry["blocked_until"] = now + BLOCK_TIME
            log[client_ip] = entry
            save_log(log)
            return JSONResponse(
                status_code=429,
                content={"detail": "Limite de requisições excedido. IP temporariamente bloqueado."}
            )

        # Atualiza o log
        log[client_ip] = entry
        save_log(log)

    response = await call_next(request)
    return response


@app.get("/busca-cep/{cep}")
def get_cep(cep: int):
    url = f"https://viacep.com.br/ws/{cep}/json/"
    response = requests.get(url)
    return response.json()
