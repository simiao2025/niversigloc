import json
import os
import threading
import time
import requests
from fastapi import FastAPI, BackgroundTasks, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import scraper_sigloc
from datetime import datetime
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

app = FastAPI(title="Gerenciar Aniversariantes")

# CONFIGURAÇÕES SUPABASE
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or SUPABASE_KEY

# CONFIGURAÇÕES EVOLUTION CENTRALIZADA
CENTRAL_EVO_URL = os.getenv("CENTRAL_EVO_URL")
CENTRAL_EVO_KEY = os.getenv("CENTRAL_EVO_KEY")

# v3.9: Hardening de Conexão
DEFAULT_TIMEOUT = 12
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "apikey": CENTRAL_EVO_KEY
}

# MODELOS
class UserRegister(BaseModel):
    email: str
    password: str
    full_name: str
    congregacao: str
    grupo_sigloc: str

class UserLogin(BaseModel):
    email: str
    password: str

class ProfileUpdate(BaseModel):
    target_phone: str
    hora_execucao: str
    frequencia: str
    msg_vazio: str

LOG_BUFFER = []

import re
import unicodedata

def slugify(text):
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    text = re.sub(r'[^\w\s]', '', text).strip().lower()
    return re.sub(r'\s+', '', text)

def add_log(msg):
    global LOG_BUFFER
    timestamp = datetime.now().strftime("%H:%M:%S")
    LOG_BUFFER.append(f"[{timestamp}] {msg}")
    if len(LOG_BUFFER) > 50:
        LOG_BUFFER.pop(0)

# HELPER: Mapeamento de Status Evolution Go (v1.0)
def map_evo_status(raw_state):
    state = str(raw_state or "OFFLINE").lower()
    # v1.0 retorna booleano 'connected' em alguns endpoints, tratamos aqui
    if raw_state is True or state in ["open", "connected", "true"]: return "CONNECTED"
    if state in ["connecting"]: return "CONNECTING"
    return "OFFLINE"

# v3.12: Helper para Sincronizar Token e URL da Evolution Central
def sync_evo_data(user_id, instance_name, auth_token=None):
    """Buscamos a instância no servidor central e salvamos o token real no Supabase."""
    print(f"[SYNC] Sincronizando instância: {instance_name}")
    try:
        r = requests.get(f"{CENTRAL_EVO_URL}/instance/all", headers=DEFAULT_HEADERS, timeout=DEFAULT_TIMEOUT)
        if r.status_code == 200:
            data = r.json().get("data", [])
            # Encontra a instância na lista do servidor
            match = next((i for i in data if i.get("name") == instance_name), None)
            if match:
                token = match.get("token")
                is_connected = match.get("connected", False)
                print(f"[SYNC] Encontrado: {instance_name} | Token: {token[:8]}... | Status: {is_connected}")
                
                # Atualiza no Supabase
                db_headers = {
                    "apikey": SUPABASE_KEY, 
                    "Authorization": f"Bearer {auth_token or SUPABASE_KEY}",
                    "Content-Type": "application/json"
                }
                requests.patch(
                    f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}",
                    json={"evo_apikey": token, "evo_url": CENTRAL_EVO_URL},
                    headers=db_headers,
                    timeout=10
                )
                print(f"[SYNC OK] Token salvo para {instance_name}")
                add_log(f"✅ Token sincronizado: {instance_name}")
                return {"token": token, "connected": is_connected}
            else:
                print(f"[SYNC AVISO] Instância '{instance_name}' não retornou na lista global.")
    except Exception as e:
        add_log(f"❌ Erro na sincronia: {str(e)}")
        print(f"[SYNC ERRO] {e}")
    return None

def run_scheduler_v2():
    add_log("☁️ Scheduler v2.9 iniciado.")
    while True:
        try:
            headers = {"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"}
            res = requests.get(f"{SUPABASE_URL}/rest/v1/profiles", headers=headers)
            if res.status_code == 200:
                profiles = res.json()
                # v3.23: Ajuste de Fuso Horário para Brasília (GMT-3)
                import datetime as dt_module
                # UTC -> Brasil (Simplificado para evitar dependências extras como pytz)
                hoje = dt_module.datetime.utcnow() - dt_module.timedelta(hours=3)
                agora_str = hoje.strftime("%H:%M")
                
                # Log de debug a cada hora redonda para não poluir
                if hoje.minute == 0:
                    print(f"[RELOGIO] Hora Brasil: {agora_str}")

                for p in profiles:
                    hora_alvo = p.get('hora_execucao', '08:00')
                    if p['frequencia'] == 'mensal' and hoje.day == 1 and agora_str == '00:01':
                        add_log(f"📅 Mensal Iniciado: {p.get('nome_completo')}")
                        threading.Thread(target=scraper_sigloc.job, args=(p, add_log)).start()
                    elif agora_str == hora_alvo:
                        add_log(f"⏰ Horário atingido ({hora_alvo}): {p.get('nome_completo')}")
                        threading.Thread(target=scraper_sigloc.job, args=(p, add_log)).start()
        except Exception as e:
            print(f"[ERR SCHED] {e}")
        time.sleep(60)

# v3.24: Garantindo que o agendador rode apenas UMA vez (Singleton)
if not os.environ.get("SCHEDULER_RUNNING"):
    os.environ["SCHEDULER_RUNNING"] = "true"
    threading.Thread(target=run_scheduler_v2, daemon=True).start()

def get_profile(uid, token=None):
    try:
        auth_header = f"Bearer {token}" if token else f"Bearer {SUPABASE_KEY}"
        headers = {"apikey": SUPABASE_KEY, "Authorization": auth_header}
        url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{uid}&select=*"
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                return data[0]
        return None
    except:
        return None

@app.post("/api/auth/register")
def register(data: UserRegister):
    auth_url = f"{SUPABASE_URL}/auth/v1/signup"
    headers = {"apikey": SUPABASE_KEY, "Content-Type": "application/json"}
    payload = {"email": data.email, "password": data.password, "data": {"full_name": data.full_name}}
    try:
        r = requests.post(auth_url, json=payload, headers=headers)
        res_auth = r.json() if r.status_code in [200, 201] else {}
        if r.status_code in [200, 201]:
            user_id = res_auth.get('id') or res_auth.get('user', {}).get('id')
            user_token = res_auth.get('access_token')
            db_headers = {
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {user_token or SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates"
            }
            # v3.20: Nome da instância compartilhado pela congregação
            instance_name = slugify(data.congregacao or data.full_name or "instancia")
            
            db_payload = {
                "id": user_id,
                "congregacao": data.congregacao,
                "grupo_sigloc": data.grupo_sigloc,
                "nome_completo": data.full_name,
                "sigloc_email": data.email,
                "sigloc_senha": data.password,
                "frequencia": "diario",
                "hora_execucao": "08:00",
                "evo_instance": instance_name  # ✅ Salva o nome da instância
            }
            print(f"[DEBUG v3.10] Enviando perfil para Supabase: {user_id}")
            r_db = requests.post(f"{SUPABASE_URL}/rest/v1/profiles", json=db_payload, headers=db_headers)
            
            if r_db.status_code not in [200, 201]:
                print(f"[ERRO CRÍTICO DB] STATUS: {r_db.status_code} - RES: {r_db.text}")
            else:
                print(f"[OK] Perfil criado. Garantindo instância Evolution: {instance_name}")
                # v3.12: Tenta criar, se já existir (403/409), o sync resolve
                # v3.18: Adicionado 'token' (obrigatório em algumas versões da Evolution)
                requests.post(
                    f"{CENTRAL_EVO_URL}/instance/create", 
                    json={"name": instance_name, "qrcode": True, "token": CENTRAL_EVO_KEY}, 
                    headers=DEFAULT_HEADERS, 
                    timeout=DEFAULT_TIMEOUT
                )
                # Sincroniza o token de volta para o banco (Auto-Repair)
                sync_evo_data(user_id, instance_name, user_token)
                
            return {"status": "success", "user": res_auth}
        raise HTTPException(status_code=r.status_code, detail=res_auth.get("msg") or r.text)
    except Exception as e:
        print(f"[ERRO REGISTRO] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/auth/login")
def login(data: UserLogin):
    auth_url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
    headers = {"apikey": SUPABASE_KEY, "Content-Type": "application/json"}
    r = requests.post(auth_url, json=data.model_dump(), headers=headers)
    if r.status_code == 200:
        return r.json()
    raise HTTPException(status_code=401, detail="Logon falhou")

def get_user_id(authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401)
    token = authorization.replace("Bearer ", "")
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {token}"}
    r = requests.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers)
    if r.status_code == 200:
        return r.json()['id']
    raise HTTPException(status_code=401)

@app.get("/api/profile")
def profile(authorization: Optional[str] = Header(None)):
    uid = get_user_id(authorization)
    p = get_profile(uid, token=authorization.replace("Bearer ", ""))
    return p or {}

@app.post("/api/profile")
def update_profile(data: ProfileUpdate, authorization: Optional[str] = Header(None)):
    uid = get_user_id(authorization)
    headers = {"apikey": SUPABASE_KEY, "Authorization": authorization, "Content-Type": "application/json"}
    payload = data.model_dump()
    url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{uid}"
    requests.patch(url, json=payload, headers=headers)
    add_log("Configurações atualizadas via PATCH.")
    return {"status": "success"}

@app.post("/api/run-now")
def run_now(authorization: Optional[str] = Header(None)):
    uid = get_user_id(authorization)
    p = get_profile(uid, token=authorization.replace("Bearer ", ""))
    if p:
        add_log(f"🚀 Gatilho manual: {p.get('nome_completo')}")
        threading.Thread(target=scraper_sigloc.job, args=(p, add_log)).start()
        return {"status": "success"}
    raise HTTPException(status_code=404)

@app.get("/api/logs")
def get_logs():
    return {"logs": LOG_BUFFER}

# ─────────────────────────────────────────────────────────────
#  WHATSAPP — Funções corrigidas para Evolution GO
# ─────────────────────────────────────────────────────────────

@app.get("/api/whatsapp/status")
def get_whatsapp_status(authorization: Optional[str] = Header(None)):
    uid = get_user_id(authorization)
    token = authorization.replace("Bearer ", "") if authorization else None
    try:
        p = get_profile(uid, token=token)
        if not p or not p.get("evo_instance"):
            return {"status": "disconnected"}

        # v3.25: Sempre limpa o nome da instância (ex: 'Arno 31' -> 'arno31')
        instance_name = slugify(p.get("evo_instance") or p.get("congregacao") or p.get("nome_completo") or "instancia")
        
        # v3.12: Evolution GO v1.0 - Usamos /instance/all para um check rápido de todos
        r = requests.get(f"{CENTRAL_EVO_URL}/instance/all", headers=DEFAULT_HEADERS, timeout=DEFAULT_TIMEOUT)
        if r.status_code == 200:
            data = r.json().get("data", [])
            match = next((i for i in data if i.get("name") == instance_name), None)
            
            # v3.16: Lógica de Auto-Reparar: Se a instância não existir no servidor Go, recriamos.
            if not match:
                print(f"[AUTO-REPAIR] Instância '{instance_name}' sumiu do Evolution. Recriando...")
                add_log(f"🛠️ Auto-Reparo: Recriando instância {instance_name}...")
                
                # Recria a instância
                # v3.18: Adicionado 'token' reutilizando o do banco se possível
                current_token = p.get("evo_apikey") or CENTRAL_EVO_KEY
                r_create = requests.post(
                    f"{CENTRAL_EVO_URL}/instance/create",
                    json={"name": instance_name, "qrcode": True, "token": current_token},
                    headers=DEFAULT_HEADERS,
                    timeout=DEFAULT_TIMEOUT
                )
                print(f"[AUTO-REPAIR] POST create: {r_create.status_code} - {r_create.text}")
                
                # Aguarda e sincroniza o novo Token (Aumentado para 3s)
                time.sleep(3)
                sync_evo_data(uid, instance_name, token)
                return {"status": "disconnected"} # Status inicial de uma nova instância

            if match and match.get("connected"):
                return {"status": "open"}

        return {"status": "disconnected"}

    except Exception as e:
        print(f"[ERRO status] {e}")
        return {"status": "disconnected"}


@app.post("/api/whatsapp/connect")
def connect_whatsapp(authorization: Optional[str] = Header(None)):
    uid = get_user_id(authorization)
    token = authorization.replace("Bearer ", "") if authorization else None
    try:
        p = get_profile(uid, token=token)
        if not p: raise HTTPException(status_code=404)

        # v3.20: Nome da instância compartilhado
        # v3.25: Sempre limpa o nome da instância (ex: 'Arno 31' -> 'arno31')
        instance_name = slugify(p.get("evo_instance") or p.get("congregacao") or p.get("nome_completo") or "instancia")
        
        # v3.12: Sincronia Automática (Auto-Repair)
        sync = sync_evo_data(uid, instance_name, token)
        
        if sync and sync.get("connected"):
            return {"message": "Já conectado"}

        # v3.18: Adicionado 'token' reutilizando o do banco
        if not sync:
            print(f"[DEBUG v3.12] Criando instância inexistente: {instance_name}")
            current_token = p.get("evo_apikey") or CENTRAL_EVO_KEY
            requests.post(
                f"{CENTRAL_EVO_URL}/instance/create",
                json={"name": instance_name, "qrcode": True, "token": current_token},
                headers=DEFAULT_HEADERS,
                timeout=DEFAULT_TIMEOUT
            )
            time.sleep(1)
            sync = sync_evo_data(uid, instance_name, token)

        # ETAPA 3: Buscar QR Code (v1.0 requer Instance Token e header 'instance')
        headers_qr = DEFAULT_HEADERS.copy()
        headers_qr["instance"] = instance_name
        # v3.13: QR endpoint na v1.0 exige o Token da Instância, não a Master Key
        if sync and sync.get("token"):
            headers_qr["apikey"] = sync["token"]
        
        for attempt in range(8):
            print(f"[DEBUG connect] Tentativa QR {attempt + 1}")
            try:
                r_qr = requests.get(f"{CENTRAL_EVO_URL}/instance/qr", headers=headers_qr, timeout=DEFAULT_TIMEOUT)
                if r_qr.status_code == 200:
                    qr_data = r_qr.json()
                    # Mapeia os diversos formatos possíveis (v1.0 usa data.Qrcode)
                    base64_data = (
                        qr_data.get("data", {}).get("Qrcode") or 
                        qr_data.get("qrcode", {}).get("base64") or 
                        qr_data.get("base64")
                    )
                    if base64_data:
                        add_log(f"📱 QR Code gerado para {instance_name}")
                        print("[SUCESSO] QR Code capturado!")
                        return {"base64": base64_data}
            except Exception as e:
                print(f"[ERRO QR] {e}")
            time.sleep(2.5)

        add_log(f"❗ Falha ao obter QR Code após 8 tentativas.")
        return {"status": "error", "msg": "Não foi possível obter o QR Code. O servidor pode estar processando a instância. Tente novamente em 1 minuto."}

    except Exception as e:
        print(f"[ERRO connect] {e}")
        return {"status": "error", "msg": str(e)}


@app.post("/api/whatsapp/disconnect")
def disconnect_whatsapp(authorization: Optional[str] = Header(None)):
    uid = get_user_id(authorization)
    token = authorization.replace("Bearer ", "") if authorization else None
    try:
        p = get_profile(uid, token=token)
        if not p:
            raise HTTPException(status_code=404, detail="Perfil não encontrado")

        # v3.20: Nome da instância compartilhado
        # v3.25: Sempre limpa o nome da instância (ex: 'Arno 31' -> 'arno31')
        instance_name = slugify(p.get("evo_instance") or p.get("congregacao") or p.get("nome_completo") or "instancia")

        headers = DEFAULT_HEADERS.copy()
        headers["apikey"] = CENTRAL_EVO_KEY  # ✅ sempre a chave global

        print(f"[DEBUG disconnect] Deletando: {instance_name}")

        r = requests.delete(
            f"{CENTRAL_EVO_URL}/instance/{instance_name}",  # ✅ sem /delete/ na URL
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
        )
        print(f"[DEBUG disconnect] Status: {r.status_code}")

        # ✅ Limpa o evo_instance do perfil no Supabase
        db_headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": authorization,
            "Content-Type": "application/json",
        }
        requests.patch(
            f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{uid}",
            json={"evo_instance": None},
            headers=db_headers,
            timeout=10,
        )

        return {"status": "success"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERRO disconnect] {e}")
        return {"status": "error", "msg": str(e)}

# ─────────────────────────────────────────────────────────────

@app.get("/")
def read_index():
    return FileResponse("index.html")

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)