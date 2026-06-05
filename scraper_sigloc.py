import json
import time
import requests
import os
import schedule
import re
import unicodedata
import traceback
from datetime import datetime
from dotenv import load_dotenv
from cryptography.fernet import Fernet

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

from bs4 import BeautifulSoup

# CONFIGURAÇÕES GLOBAIS
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
# v3.14: Usa Service Role Key se disponível para ignorar RLS nas automações
DB_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or SUPABASE_KEY
CENTRAL_EVO_URL = os.getenv("CENTRAL_EVO_URL")
CENTRAL_EVO_KEY = os.getenv("CENTRAL_EVO_KEY")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

def decrypt_pwd(pwd):
    if not ENCRYPTION_KEY or not pwd: return pwd
    try:
        cipher = Fernet(ENCRYPTION_KEY.encode())
        return cipher.decrypt(pwd.encode()).decode()
    except:
        return pwd # Fallback se não estiver criptografado

def log_debug(msg):
    with open("scraper_debug.log", "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    print(msg)

def db_save_aniversariantes(user_id, lista, tipo):
    """Salva a lista no Supabase usando UPSERT"""
    safe_lista = list(lista or [])
    if not safe_lista: return
    
    url = f"{SUPABASE_URL}/rest/v1/aniversariantes"
    headers = {"apikey": DB_KEY, "Authorization": f"Bearer {DB_KEY}", "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"}
    payload = []
    for item in safe_lista:
        if not isinstance(item, dict): continue
        
        # v3.15: Prioriza dia/mes já calculados na extração
        dia = item.get('dia')
        mes = item.get('mes')
        
        if not dia or not mes:
            partes = str(item.get('data', '')).split('/')
            if len(partes) >= 2:
                dia = int(partes[0])
                mes = int(partes[1])
        
        if dia and mes:
            payload.append({
                "user_id": user_id,
                "nome": item.get('nome', 'Sem Nome'),
                "dia": dia,
                "mes": mes,
                "tipo": tipo,
                "tempo": item.get('tempo', ''),
                "data_full": item.get('data', '')
            })
    if not payload: return
    log_debug(f"[DB SAVE] Tentando salvar {len(payload)} itens do tipo {tipo}")
    try:
        r = requests.post(f"{url}?on_conflict=user_id,nome,dia,mes,tipo", json=payload, headers=headers)
        log_debug(f"[DB SAVE] Status: {r.status_code}")
        if r.status_code not in [200, 201]:
            log_debug(f"[DB SAVE ERR] {r.text}")
    except Exception as e:
        log_debug(f"[DB SAVE EX] {e}")

def db_get_aniversariantes_hoje(user_id):
    """Busca no banco os aniversariantes do dia atual"""
    hoje = datetime.now()
    url = f"{SUPABASE_URL}/rest/v1/aniversariantes"
    headers = {"apikey": DB_KEY, "Authorization": f"Bearer {DB_KEY}"}
    params = {"user_id": f"eq.{user_id}", "dia": f"eq.{hoje.day}", "mes": f"eq.{hoje.month}", "select": "*"}
    try:
        res = requests.get(url, headers=headers, params=params)
        if res.status_code == 200:
            dados = res.json()
            if not isinstance(dados, list): return [], []
            vivos = [{"nome": d.get('nome'), "data": d.get('data_full'), "tempo": d.get('tempo'), "dia": d.get('dia'), "mes": d.get('mes')} for d in dados if d.get('tipo') == 'aniversario']
            casam = [{"nome": d.get('nome'), "data": d.get('data_full'), "tempo": d.get('tempo'), "dia": d.get('dia'), "mes": d.get('mes')} for d in dados if d.get('tipo') == 'bodas']
            return vivos, casam
    except Exception as e:
        print(f"[ERR DB TODAY] {e}")
    return [], []

def db_has_month_data(user_id):
    """Verifica se existe QUALQUER registro para o mês atual no banco"""
    mes_atual = datetime.now().month
    url = f"{SUPABASE_URL}/rest/v1/aniversariantes"
    headers = {"apikey": DB_KEY, "Authorization": f"Bearer {DB_KEY}"}
    # Basta saber se existe pelo menos 1 registro (limit=1)
    params = {"user_id": f"eq.{user_id}", "mes": f"eq.{mes_atual}", "limit": 1, "select": "id"}
    try:
        res = requests.get(url, headers=headers, params=params)
        if res.status_code == 200:
            return len(res.json()) > 0
    except Exception as e:
        print(f"[ERR DB MONTH CHECK] {e}")
    return False

# Driver Removido. Extração nativa via HTTP.
# v3.9: Hardening de Conexão
DEFAULT_TIMEOUT = 12
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "apikey": CENTRAL_EVO_KEY
}

def db_update_evo_token(user_id, new_token):
    """Atualiza o token da instância no banco de dados"""
    url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}"
    headers = {"apikey": DB_KEY, "Authorization": f"Bearer {DB_KEY}", "Content-Type": "application/json"}
    try:
        requests.patch(url, json={"evo_apikey": new_token}, headers=headers, timeout=10)
    except: pass

def enviar_whatsapp(mensagem: str, config):
    if not mensagem or not config: return False
    
    dest = config.get('target_phone', config.get('destinatario'))
    instance_name = config.get('evo_instance', 'default')
    # v3.11: Prioriza o token real da instância (apikey específica)
    instance_token = config.get('evo_apikey') or CENTRAL_EVO_KEY

    # v3.16: Auto-conferência antes de enviar (Auto-Repair Silencioso)
    try:
        if instance_name != 'default':
            check = requests.get(f"{CENTRAL_EVO_URL}/instance/all", headers=DEFAULT_HEADERS, timeout=8)
            if check.status_code == 200:
                data = check.json().get("data", [])
                match = next((i for i in data if i.get("name") == instance_name), None)
                if not match:
                    print(f"[AUTO-ROBOT] Instância {instance_name} não existe. Recriando...")
                    # v3.18: Adicionado 'token' (obrigatório em algumas versões da Evolution)
                    r_create = requests.post(f"{CENTRAL_EVO_URL}/instance/create", 
                                          json={"name": instance_name, "qrcode": True, "token": instance_token}, 
                                          headers=DEFAULT_HEADERS, timeout=10)
                    if r_create.status_code in [200, 201] and config.get('id'):
                        time.sleep(1.5)
                        r_all = requests.get(f"{CENTRAL_EVO_URL}/instance/all", headers=DEFAULT_HEADERS, timeout=8)
                        new_data = r_all.json().get("data", [])
                        new_match = next((i for i in new_data if i.get("name") == instance_name), None)
                        if new_match:
                            instance_token = new_match.get('token') # Atualiza para o envio atual
                            db_update_evo_token(config.get('id'), instance_token) # Salva para os próximos
    except Exception as e:
        print(f"[ERR AUTO-REPAIR] {e}")

    print(f"\n[->] Enviando para {dest} via Instância {instance_name}...")
    
    url = f"{CENTRAL_EVO_URL}/send/text"
    headers = DEFAULT_HEADERS.copy()
    headers["apikey"] = instance_token
    headers["instance"] = instance_name # v3.12: Necessário para Evolution GO v1.0
    
    payload = {
        "number": str(dest),
        "text": str(mensagem)
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=DEFAULT_TIMEOUT)
        if response.status_code in [200, 201]:
            print("[OK] Envio bem-sucedido.")
            return True
        else:
            print(f"[ERR] Evolution: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"[ERR] Falha de conexão WhatsApp: {e}")
        return False

def formatar_mensagem(aniv_vivos, aniv_casam, frequencia="mensal", msg_vazio=""):
    vivos = list(aniv_vivos or [])
    casam = list(aniv_casam or [])
    
    hoje_obj = datetime.now()
    hoje_str = hoje_obj.strftime("%d/%m/%Y")
    is_diario = (str(frequencia).lower() == "diario")
    
    if is_diario:
        # v3.15: Compara usando dia e mes numéricos para evitar erros de formatação de string
        vivos = [a for a in vivos if isinstance(a, dict) and int(a.get('dia', 0)) == hoje_obj.day and int(a.get('mes', 0)) == hoje_obj.month]
        casam = [c for c in casam if isinstance(c, dict) and int(c.get('dia', 0)) == hoje_obj.day and int(c.get('mes', 0)) == hoje_obj.month]
        
    if not vivos and not casam:
        return str(msg_vazio) if msg_vazio else "Olá! Não temos aniversariantes hoje. Tenha um ótimo dia! 🌟"

    msg = f"*🔔 ANIVERSARIANTES DE HOJE - {hoje_str}*\n\n" if is_diario else f"*RESUMO DE ANIVERSARIANTES - {hoje_str}*\n\n"
    msg += "🎂 *Aniversariantes do Dia:*" if is_diario else "🎂 *Aniversariantes do Mês:*"
    msg += "\n"
    if not vivos: 
        msg += "_Nenhum registro hoje._\n" if is_diario else "_Nenhum registro encontrado._\n"
    else:
        for a in vivos:
            if isinstance(a, dict):
                msg += f"• {a.get('data', '??/??')} - {a.get('nome', 'Sem Nome')} ({a.get('tempo', '')})\n"
    
    msg += "\n💍 *Bodas de Hoje:*" if is_diario else "\n💍 *Aniversários de Casamento:*"
    msg += "\n"
    if not casam: 
        msg += "_Nenhum registro hoje._\n" if is_diario else "_Nenhum registro encontrado._\n"
    else:
        for c in casam:
            if isinstance(c, dict):
                msg += f"• {c.get('data', '??/??')} - {c.get('nome', 'Sem Nome')} ({c.get('tempo', '')})\n"
    
    msg += "\n_Robô SIGLOC Automático_"
    return msg

def extrair_lista(html, titulo_texto: str):
    print(f"[->] Extraindo: '{titulo_texto}'...")
    resultados = []
    try:
        soup = BeautifulSoup(html, 'html.parser')
        widgets = soup.find_all(class_="widget-box")
        alvo = None
        for w in widgets:
            if titulo_texto.lower() in w.text.lower():
                alvo = w
                break
        
        if not alvo: 
            print(f"[!] Widget '{titulo_texto}' não apareceu.")
            return []
        
        linhas = alvo.select("table tbody tr")
        for tr in linhas:
            colunas = tr.find_all("td")
            if len(colunas) >= 4:
                d_raw = colunas[1].text.strip()
                n = colunas[2].text.strip()
                t = colunas[3].text.strip()
                
                if n and len(n) > 3 and "Nenhum" not in n:
                    dia_final = 0
                    mes_final = datetime.now().month
                    
                    if "/" in d_raw:
                        partes = d_raw.split('/')
                        dia_final = int(partes[0])
                        mes_final = int(partes[1])
                    elif d_raw.isdigit():
                        dia_final = int(d_raw)
                    
                    if dia_final == 0 and "/" in t:
                        partes = t.split('/')
                        if len(partes) >= 2:
                            dia_final = int(partes[0])
                            mes_final = int(partes[1])

                    if dia_final > 0:
                        resultados.append({
                            "data": d_raw if "/" in d_raw else f"{dia_final:02d}/{mes_final:02d}", 
                            "nome": n, 
                            "tempo": t,
                            "dia": dia_final,
                            "mes": mes_final
                        })
        return resultados
    except Exception as e:
        print(f"[ERR EXTRAÇÃO] {e}")
        return []

def job(profile=None, log_func=None):
    if not profile or not isinstance(profile, dict):
        print("[!] Job ignorado: Perfil inválido.")
        return
    
    def report(m):
        if log_func: log_func(m)
        print(m)

    config = profile
    user_id = config.get('id')
    frequencia = config.get('frequencia', 'diario')
    congregacao = config.get('congregacao', 'Instância')
    report(f"🤖 Robô acionado para {congregacao}...")
    
    aniv_v = []
    aniv_c = []

    try:
        if str(frequencia).lower() == "diario" and user_id:
            report(f"🔍 Consultando banco de dados para {congregacao}...")
            aniv_v, aniv_c = db_get_aniversariantes_hoje(user_id)
            
            if aniv_v or aniv_c:
                report(f"📦 Dados encontrados no banco: {len(aniv_v)} aniversariantes e {len(aniv_c)} casamentos identificados.")
                report(f"✉️ Criando lista e enviando mensagens para {congregacao}...")
                msg = formatar_mensagem(aniv_v, aniv_c, "diario", config.get('msg_vazio', ''))
                enviar_whatsapp(msg, config)
                report(f"✅ Disparo diário concluído para {congregacao}.")
                return
            
            report(f"⚠️ Dados de hoje não encontrados no banco. Iniciando robô SIGLOC...")
            if db_has_month_data(user_id):
                if config.get('msg_vazio'):
                    msg = formatar_mensagem([], [], "diario", config.get('msg_vazio', ''))
                    enviar_whatsapp(msg, config)
                report(f"ℹ️ Mês já processado anteriormente. Sem envio extra hoje.")
                return
            
        report(f"🔑 Acessando portal SIGLOC via HTTP para {congregacao}...")
        try:
            session = requests.Session()
            session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"})
            
            pwd = decrypt_pwd(config.get('sigloc_senha', ''))
            
            login_payload = {
                "grupo": config.get('grupo_sigloc', ''),
                "email": config.get('sigloc_email', ''),
                "senha": pwd
            }
            
            session.post("https://www.sigloc.com.br/sigloc/index.php/siglocig/verificarLogin", data=login_payload, timeout=20)
            
            report(f"📄 Extraindo lista de aniversários do Portal...")
            res_dash = session.get("https://www.sigloc.com.br/sigloc/index.php/siglocig", timeout=20)
            html_content = res_dash.text
            
            aniv_v = extrair_lista(html_content, "Aniversariantes do Mês") or []
            aniv_c = extrair_lista(html_content, "Aniversariantes de Casamento") or []
            
            if user_id:
                report(f"💾 Salvando dados extraídos no banco de dados...")
                db_save_aniversariantes(user_id, aniv_v, "aniversario")
                db_save_aniversariantes(user_id, aniv_c, "bodas")
            
            report(f"✉️ Preparando e enviando mensagens via WhatsApp...")
            msg = formatar_mensagem(aniv_v, aniv_c, frequencia, config.get('msg_vazio', ''))
            enviar_whatsapp(msg, config)
            report(f"✅ Robô HTTP finalizado para {congregacao}.")
            
        except Exception as inner_e:
            print(f"[BUG INTERNO] {inner_e}")
            traceback.print_exc()
            enviar_whatsapp(f"⚠️ Erro interno na raspagem: {inner_e}", config)
        finally:
            if driver: driver.quit()

    except Exception as e:
        print(f"[BUG CRÍTICO] {e}")
        traceback.print_exc()
        try: enviar_whatsapp(f"❌ Falha crítica no robô: {e}", config)
        except: pass

if __name__ == "__main__":
    pass
