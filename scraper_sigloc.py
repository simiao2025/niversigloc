"""
Automação SIGLOC — Versão Integrada com Interface Web
"""

import json
import time
import requests
import os
import schedule
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

def carregar_config():
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def criar_driver(headless=True):
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-translate")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--disable-infobars")
    opts.add_argument("--window-size=1440,1080")
    opts.add_argument("--ignore-certificate-errors")
    opts.add_argument("--allow-running-insecure-content")
    opts.add_argument("--disable-web-security")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)

def enviar_whatsapp(mensagem: str, config):
    print(f"\n[->] Enviando para {config['destinatario']}...")
    url = f"{config['evo_url']}/send/text"
    headers = {
        "Content-Type": "application/json",
        "apikey": config['evo_apikey']
    }
    payload = {
        "instance": config['evo_instance'],
        "number": config['destinatario'],
        "text": mensagem
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code in [200, 201]:
            return True
        else:
            print(f"[ERR] Erro na API do WhatsApp: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"[ERR] Falha ao conectar na Evolution API: {e}")
        return False

def formatar_mensagem(aniv_vivos, aniv_casam, frequencia="mensal", msg_vazio=""):
    hoje_obj = datetime.now()
    hoje_str = hoje_obj.strftime("%d/%m/%Y")
    hoje_dm = hoje_obj.strftime("%d/%m")
    
    is_diario = (frequencia == "diario")
    
    # Se for diário, filtra a lista para pegar apenas o dia atual
    if is_diario:
        aniv_vivos = [a for a in aniv_vivos if a['data'][:5] == hoje_dm]
        aniv_casam = [c for c in aniv_casam if c['data'][:5] == hoje_dm]

    # SE ESTIVER VAZIO (E TIVER MENSAGEM PERSONALIZADA), RETORNA ELA
    if not aniv_vivos and not aniv_casam and msg_vazio:
        return msg_vazio

    msg = f"*🔔 ANIVERSARIANTES DE HOJE - {hoje_str}*\n\n" if is_diario else f"*RESUMO DE ANIVERSARIANTES - {hoje_str}*\n\n"

    msg += "🎂 *Aniversariantes do Dia:*" if is_diario else "🎂 *Aniversariantes do Mês:*"
    msg += "\n"
    
    if not aniv_vivos:
        msg += "_Nenhum registro hoje._\n" if is_diario else "_Nenhum registro encontrado._\n"
    for a in aniv_vivos:
        msg += f"• {a['data']} - {a['nome']} ({a['tempo']})\n"
    
    msg += "\n💍 *Bodas de Hoje:*" if is_diario else "\n💍 *Aniversários de Casamento:*"
    msg += "\n"
    
    if not aniv_casam:
        msg += "_Nenhum registro hoje._\n" if is_diario else "_Nenhum registro encontrado._\n"
    for c in aniv_casam:
        msg += f"• {c['data']} - {c['nome']} ({c['tempo']})\n"
    
    msg += "\n_Robô SIGLOC Automático_"
    return msg

def extrair_lista(driver, titulo_texto: str):
    print(f"[->] Extraindo: '{titulo_texto}'...")
    resultados = []
    try:
        # Encontra todos os blocos de widget na página (estratégia mais robusta)
        widgets = driver.find_elements(By.CSS_SELECTOR, ".widget-box")
        alvo = None
        for w in widgets:
            if titulo_texto.lower() in w.text.lower():
                alvo = w
                break
        
        if not alvo:
            print(f"[!] Erro: Widget '{titulo_texto}' não encontrado na página.")
            # Salva screenshot para debug se não achar o widget
            driver.save_screenshot(f"erro_widget_{titulo_texto.replace(' ', '_')}.png")
            return []

        # Localiza todas as linhas (tr) da tabela dentro do widget
        linhas = alvo.find_elements(By.CSS_SELECTOR, "table tbody tr")
        
        for tr in linhas:
            colunas = tr.find_elements(By.TAG_NAME, "td")
            # Conforme o HTML: td[1]=ícone, td[2]=data, td[3]=nome, td[4]=idade/tempo
            if len(colunas) >= 4:
                data = colunas[1].text.strip()
                nome = colunas[2].text.strip()
                tempo = colunas[3].text.strip()
                
                # Ignora linhas vazias ou placeholders (como "Nenhum registro")
                if nome and len(nome) > 3 and "Nenhum" not in nome:
                    resultados.append({
                        "data": data,
                        "nome": nome,
                        "tempo": tempo
                    })
        
        # Caso a tabela falhe, tenta varrer divs internas (fallback)
        if not resultados:
            elementos = alvo.find_elements(By.CSS_SELECTOR, ".item, li, a")
            for el in elementos:
                t = el.text.strip()
                if t and len(t.split("\n")) >= 2:
                    p = [i.strip() for i in t.split("\n")]
                    resultados.append({"data": p[0], "nome": p[1], "tempo": p[2] if len(p)>2 else ""})

        return resultados

    except Exception as e:
        print(f"[ERR] Erro na extração de {titulo_texto}: {e}")
        driver.save_screenshot(f"erro_fatal_{titulo_texto.replace(' ', '_')}.png")
        return []

def job():
    config = carregar_config()
    print(f"\n[EXEC] Iniciando tarefa: {datetime.now().strftime('%H:%M:%S')}")
    
    driver = None
    try:
        driver = criar_driver(headless=config['headless'])
        driver.get("https://www.sigloc.com.br/login/")
        
        WebDriverWait(driver, config['timeout']).until(EC.presence_of_element_located((By.NAME, "grupo")))
        driver.find_element(By.NAME, "grupo").send_keys(config['grupo'])
        driver.find_element(By.NAME, "email").send_keys(config['usuario'])
        driver.find_element(By.NAME, "senha").send_keys(config['senha'])
        driver.find_element(By.CSS_SELECTOR, "input.btn-success").click()
        
        WebDriverWait(driver, config['timeout']).until(lambda d: "index.php" in d.current_url or "sigloc" in d.current_url)
        
        # Vai direto para o dashboard de aniversariantes
        driver.get("https://www.sigloc.com.br/sigloc/index.php/siglocig")
        time.sleep(10) # Tempo extra para carregar widgets dinâmicos
        
        aniv_mes = extrair_lista(driver, "Aniversariantes do Mês")
        aniv_casam = extrair_lista(driver, "Aniversariantes de Casamento")
        
        msg = formatar_mensagem(aniv_mes, aniv_casam, config.get('frequencia', 'diario'), config.get('msg_vazio', ''))
        sucesso = enviar_whatsapp(msg, config)
        print(f"[OK] Tarefa concluída. WhatsApp enviado: {sucesso}")
    except Exception as e:
        erro = f"⚠️ *FALHA:* {str(e)}"
        print(erro)
        enviar_whatsapp(erro, config)
    finally:
        if driver: driver.quit()

if __name__ == "__main__":
    job()
