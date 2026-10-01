html = open('index.html', encoding='utf-8').read()
idx = html.find('O servidor pode estar processando')
print(html[idx-300:idx+300])
