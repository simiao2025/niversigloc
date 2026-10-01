html = open('index.html', encoding='utf-8').read()
idx = html.find('Erro: Não foi possível obter o QR Code')
print(html[idx-300:idx+300].encode('utf-8', 'ignore').decode('utf-8', 'ignore'))
