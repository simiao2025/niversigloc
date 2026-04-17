import json
import os
import threading
import time
import requests
import schedule
from fastapi import FastAPI, BackgroundTasks, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import scraper_sigloc

app = FastAPI(title="Niarsigloc Cloud")

# CONFIGURAÇÕES SUPABASE
SUPABASE_URL = scraper_sigloc.SUPABASE_URL
SUPABASE_KEY = scraper_sigloc.SUPABASE_KEY

# CONFIGURAÇÕES EVOLUTION CENTRALIZADA
CENTRAL_EVO_URL = "https://evolution-api.brasilonthebox.shop"
CENTRAL_EVO_KEY = "0ec391ec-4732-4934-9ef3-d262a11cb933"

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
    congregacao: str
    grupo_sigloc: str
    sigloc_email: str
    sigloc_senha: str
    target_phone: str
    hora_execucao: str
    frequencia: str
    msg_vazio: str
    evo_url: str
    evo_instance: str
    evo_apikey: str

LOG_BUFFER = []

import re
import unicodedata

def slugify(text):
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    text = re.sub(r'[^\w\s-]', '', text).strip().lower()
    return re.sub(r'[-\s]+', '-', text)

def add_log(msg):
    global LOG_BUFFER
    timestamp = scraper_sigloc.datetime.now().strftime("%H:%M:%S")
    LOG_BUFFER.append(f"[{timestamp}] {msg}")
    if len(LOG_BUFFER) > 50:
        LOG_BUFFER.pop(0)

def run_scheduler_v2():
    add_log("☁️ Scheduler Multi-usuário iniciado.")
    while True:
        try:
            # Busca todos os perfis no Supabase
            headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
            res = requests.get(f"{SUPABASE_URL}/rest/v1/profiles", headers=headers)
            
            if res.status_code == 200:
                profiles = res.json()
                hoje = scraper_sigloc.datetime.now()
                agora_str = hoje.strftime("%H:%M")
                
                for p in profiles:
                    # Verifica se deve rodar a tarefa mensal (Dia 01 às 00:01)
                    if p['frequencia'] == 'mensal' and hoje.day == 1 and agora_str == '00:01':
                        add_log(f"Iniciando tarefa mensal para: {p['nome_completo']}")
                        threading.Thread(target=scraper_sigloc.job, args=(p,)).start()
                    
                    # Verifica se deve rodar a tarefa diária (No horário agendado)
                    elif agora_str == p.get('hora_execucao', '08:00'):
                        # Evita rodar várias vezes no mesmo minuto
                        # Aqui poderíamos adicionar um lock ou controle de 'last_run' no banco
                        add_log(f"Disparo agendado para: {p['nome_completo']}")
                        threading.Thread(target=scraper_sigloc.job, args=(p,)).start()
            
        except Exception as e:
            add_log(f"Erro no scheduler cloud: {e}")
        time.sleep(60) # Checa a cada minuto

# Inicia o scheduler em uma thread separada
threading.Thread(target=run_scheduler_v2, daemon=True).start()

# --- ROTAS DE AUTENTICAÇÃO ---
@app.post("/api/auth/register")
def register(data: UserRegister):
    auth_url = f"{SUPABASE_URL}/auth/v1/signup"
    headers = {"apikey": SUPABASE_KEY, "Content-Type": "application/json"}
    payload = {
        "email": data.email, 
        "password": data.password, 
        "data": {"full_name": data.full_name}
    }
    
    r = requests.post(auth_url, json=payload, headers=headers)
    if r.status_code == 200:
        res_auth = r.json()
        user_id = res_auth['id']
        # Criar/Atualizar perfil com dados adicionais
        db_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}"
        db_headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
        db_payload = {
            "congregacao": data.congregacao,
            "grupo_sigloc": data.grupo_sigloc
        }
        requests.patch(db_url, json=db_payload, headers=db_headers)
        return {"status": "success", "user": res_auth}
    return HTTPException(status_code=r.status_code, detail=r.text)

@app.post("/api/auth/login")
def login(data: UserLogin):
    auth_url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
    headers = {"apikey": SUPABASE_KEY, "Content-Type": "application/json"}
    r = requests.post(auth_url, json=data.model_dump(), headers=headers)
    if r.status_code == 200:
        return r.json()
    raise HTTPException(status_code=401, detail="Credenciais inválidas")

# --- ROTAS DE PROTEGIDAS (VIA HEADER AUTHORIZATION) ---
def get_user_id(authorization: Optional[str] = Header(None)):
    if not authorization: raise HTTPException(status_code=401)
    token = authorization.replace("Bearer ", "")
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {token}"}
    r = requests.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers)
    if r.status_code == 200:
        return r.json()['id']
    raise HTTPException(status_code=401)

@app.get("/api/profile")
def get_profile(user_id: str = scraper_sigloc.depends(get_user_id) if hasattr(scraper_sigloc, 'depends') else None):
    # Fallback simples para o user_id se o depends falhar na sintaxe (ajustando abaixo)
    pass

@app.get("/api/profile")
def get_profile(authorization: Optional[str] = Header(None)):
    uid = get_user_id(authorization)
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    r = requests.get(f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{uid}&select=*", headers=headers)
    return r.json()[0] if r.json() else {}

@app.post("/api/profile")
def update_profile(data: ProfileUpdate, authorization: Optional[str] = Header(None)):
    uid = get_user_id(authorization)
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
    r = requests.patch(f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{uid}", json=data.model_dump(), headers=headers)
    add_log(f"Perfil de {uid} atualizado.")
    return {"status": "success"}

@app.get("/api/logs")
def get_logs():
    return {"logs": LOG_BUFFER}

@app.post("/api/run-now")
def run_now(background_tasks: BackgroundTasks, authorization: Optional[str] = Header(None)):
    uid = get_user_id(authorization)
    # Busca o perfil completo para rodar a job
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    r = requests.get(f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{uid}&select=*", headers=headers)
    if r.status_code == 200 and r.json():
        p = r.json()[0]
        add_log(f"Execução manual disparada por {p['nome_completo']}")
        background_tasks.add_task(scraper_sigloc.job, p)
        return {"status": "started"}
    return {"status": "error"}

@app.get("/api/whatsapp/status")
def get_whatsapp_status(authorization: Optional[str] = Header(None)):
    uid = get_user_id(authorization)
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    r = requests.get(f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{uid}&select=*", headers=headers)
    p = r.json()[0]
    
    if not p.get('evo_url'): return {"status": "NOT_CONFIGURED"}

    url = f"{p['evo_url']}/instance/status?instance={p['evo_instance']}"
    h = {"apikey": p['evo_apikey']}
    try:
        req = requests.get(url, headers=h, timeout=5)
        if req.status_code == 200:
            is_connected = req.json().get("data", {}).get("Connected", False)
            return {"status": "CONNECTED" if is_connected else "OFFLINE"}
        return {"status": "OFFLINE"}
    except:
        return {"status": "ERROR"}

@app.post("/api/whatsapp/connect")
def connect_whatsapp(authorization: Optional[str] = Header(None)):
    uid = get_user_id(authorization)
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    r = requests.get(f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{uid}&select=*", headers=headers)
    p = r.json()[0]

    instance_name = p.get('evo_instance')
    
    # 1. Se não tem instância, cria agora
    if not instance_name:
        add_log(f"Criando nova instância para {p['congregacao']}...")
        instance_name = slugify(p['congregacao'])
        
        create_url = f"{CENTRAL_EVO_URL}/instance/create"
        payload = {
            "instanceName": instance_name,
            "token": uid[:12], # Token opcional da instancia
            "qrcode": True
        }
        res_create = requests.post(create_url, json=payload, headers={"apikey": CENTRAL_EVO_KEY})
        
        # Salva o nome da instância no perfil do Supabase
        requests.patch(f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{uid}", 
                       json={"evo_instance": instance_name, "evo_url": CENTRAL_EVO_URL, "evo_apikey": CENTRAL_EVO_KEY}, 
                       headers=headers)
        
    # 2. Busca o QR Code
    qr_url = f"{CENTRAL_EVO_URL}/instance/qr?instance={instance_name}"
    try:
        req = requests.get(qr_url, headers={"apikey": CENTRAL_EVO_KEY}, timeout=10)
        data = req.json()
        return {"base64": data.get("data", "")}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/whatsapp/disconnect")
def disconnect_whatsapp():
    config = scraper_sigloc.carregar_config()
    # No Evolution GO, usa-se POST /instance/disconnect ou DELETE /instance/logout
    url = f"{config['evo_url']}/instance/logout?instance={config['evo_instance']}"
    headers = {"apikey": config['evo_apikey']}
    try:
        r = requests.delete(url, headers=headers, timeout=10)
        add_log("WhatsApp desconectado via painel.")
        return r.json()
    except Exception as e:
        return {"error": str(e)}

# Sirva os arquivos estáticos (Frontend)
@app.get("/")
def read_index():
    return FileResponse("index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
