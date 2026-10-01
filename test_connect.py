import re
html = open('index.html', encoding='utf-8').read()
idx = html.find('/api/whatsapp/connect')
print(html[idx-100:idx+200])
