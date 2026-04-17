import requests

base_url = "https://evolution-api.brasilonthebox.shop"
apikey = "0ec391ec-4732-4934-9ef3-d262a11cb933"
instance_name = "aniversariantesigloc"
instance_id = "0b1d95ca-c8ea-4631-8a73-bdfd3681ac07"

# Variações de caminhos comuns no Evolution Go e versões anteriores
paths = [
    f"/message/sendText/{instance_name}",
    f"/message/sendText/{instance_id}",
    f"/{instance_name}/message/text",
    f"/{instance_id}/message/text",
    f"/instance/{instance_name}/message/text",
    f"/instance/{instance_id}/message/text",
    f"/instances/{instance_name}/message/text",
    f"/instances/{instance_id}/message/text",
    f"/api/message/sendText/{instance_name}",
    f"/api/v1/message/sendText/{instance_name}",
    f"/v2/message/sendText/{instance_name}",
    "/message/text",
    "/message/sendText"
]

header_variants = [
    {"apikey": apikey},
    {"apiKey": apikey},
    {"Authorization": f"Bearer {apikey}"},
    {"instance": instance_name}
]

print(f"Diagnosticando Evolution GO em {base_url}...")

# Testando um endpoint de sanidade primeiro
try:
    r_root = requests.get(base_url, timeout=5)
    print(f"Raiz: {r_root.status_code}")
except: pass

for p in paths:
    url = f"{base_url}{p if p.startswith('/') else '/' + p}"
    for h in header_variants:
        try:
            # Tenta POST para envio de mensagem
            data = {"number": "5563981142553", "text": "ping test", "instance": instance_name}
            r = requests.post(url, headers=h, json=data, timeout=3)
            if r.status_code != 404:
                print(f"[FOUND] {url} | Header: {list(h.keys())[0]} | Status: {r.status_code} | Body: {r.text[:50]}")
        except:
            pass

print("Fim do diagnóstico.")
