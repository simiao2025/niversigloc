import json
import os
import threading
import time
import requests
import schedule
from fastapi import FastAPI, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import scraper_sigloc

app = FastAPI(title="SIGLOC Agent API")

CONFIG_FILE = "config.json"
LOG_BUFFER = []

class ConfigUpdate(BaseModel):
    hora_execucao: str
    destinatario: str
    usuario: str
    senha: str
    frequencia: str
    msg_vazio: str

def add_log(msg):
    global LOG_BUFFER
    timestamp = scraper_sigloc.datetime.now().strftime("%H:%M:%S")
    LOG_BUFFER.append(f"[{timestamp}] {msg}")
    if len(LOG_BUFFER) > 50:
        LOG_BUFFER.pop(0)

def run_scheduler():
    last_config_hash = None
    while True:
        try:
            config = scraper_sigloc.carregar_config()
            frequencia = config.get("frequencia", "diario")
            hora = config.get("hora_execucao", "08:00")
            
            # Geramos um hash simples para detectar mudanças na regra de agendamento
            current_hash = f"{frequencia}-{hora}"
            
            if current_hash != last_config_hash:
                schedule.clear()
                
                if frequencia == "mensal":
                    # Mensal: Dispara todo dia às 00:01, mas a job interna checa se é dia 01
                    def monthly_check():
                        if scraper_sigloc.datetime.now().day == 1:
                            scraper_sigloc.job()
                    
                    schedule.every().day.at("00:01").do(monthly_check)
                    add_log("Agendamento Mensal: Todo dia 01 às 00:01")
                else:
                    # Diário: Comportamento normal
                    schedule.every().day.at(hora).do(scraper_sigloc.job)
                    add_log(f"Agendamento Diário: Todos os dias às {hora}")
                
                last_config_hash = current_hash
            
            schedule.run_pending()
        except Exception as e:
            add_log(f"Erro no scheduler: {e}")
        time.sleep(10)

# Inicia o scheduler em uma thread separada
threading.Thread(target=run_scheduler, daemon=True).start()

@app.get("/api/config")
def get_config():
    return scraper_sigloc.carregar_config()

@app.post("/api/config")
def update_config(data: ConfigUpdate):
    config = scraper_sigloc.carregar_config()
    config["hora_execucao"] = data.hora_execucao
    config["destinatario"] = data.destinatario
    config["usuario"] = data.usuario
    config["senha"] = data.senha
    config["frequencia"] = data.frequencia
    config["msg_vazio"] = data.msg_vazio
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    add_log(f"Configuração atualizada! Frequência: {data.frequencia}")
    return {"status": "success"}

@app.get("/api/logs")
def get_logs():
    return {"logs": LOG_BUFFER}

@app.post("/api/run-now")
def run_now(background_tasks: BackgroundTasks):
    add_log("Disparando execução manual...")
    background_tasks.add_task(scraper_sigloc.job)
    return {"status": "started"}

@app.get("/api/whatsapp/status")
def get_whatsapp_status():
    config = scraper_sigloc.carregar_config()
    # No Evolution GO o status real de conexao fica em /instance/status
    url = f"{config['evo_url']}/instance/status?instance={config['evo_instance']}"
    headers = {"apikey": config['evo_apikey']}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            # Se Connected for True e LoggedIn for True, está tudo ok
            is_connected = data.get("data", {}).get("Connected", False)
            return {"status": "CONNECTED" if is_connected else "OFFLINE"}
        return {"status": "OFFLINE"}
    except:
        return {"status": "ERROR"}

@app.post("/api/whatsapp/connect")
def connect_whatsapp():
    config = scraper_sigloc.carregar_config()
    # Primeiro verifica o QR
    url = f"{config['evo_url']}/instance/qr?instance={config['evo_instance']}"
    headers = {"apikey": config['evo_apikey']}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        if r.status_code == 200 and "data" in data:
            # Algumas versoes do Go retornam o base64 direto em data
            return {"base64": data["data"] if isinstance(data["data"], str) else ""}
        return data
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
