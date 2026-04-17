import requests

base_url = "https://evolution-api.brasilonthebox.shop"
apikey = "0ec391ec-4732-4934-9ef3-d262a11cb933"
instance = "aniversariantesigloc"

prefixes = ["", "v1", "v2", "api", "evolution", "evolution-api"]
endpoints = [
    "instance/fetchInstances",
    f"message/sendText/{instance}"
]

headers_list = [
    {"apikey": apikey},
    {"apiKey": apikey},
    {"Authorization": f"Bearer {apikey}"}
]

print(f"Diagnóstico de {base_url}...")

for pref in prefixes:
    for endp in endpoints:
        for headers in headers_list:
            path = f"{pref}/{endp}" if pref else endp
            url = f"{base_url}/{path}"
            try:
                # Usando GET para check de instâncias e POST para mensagem
                if "sendText" in endp:
                    r = requests.post(url, headers=headers, json={"number": "5563981142553", "text": "ping"}, timeout=5)
                else:
                    r = requests.get(url, headers=headers, timeout=5)
                
                if r.status_code != 404:
                    print(f"[ACHOU!] {url} | Headers: {list(headers.keys())[0]} | Status: {r.status_code}")
                # else:
                #    print(f"[404] {url}")
            except Exception as e:
                print(f"[ERRO] {url}: {e}")

print("Diagnóstico finalizado.")
