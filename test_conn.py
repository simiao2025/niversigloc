import re
html = open('index.html', encoding='utf-8').read()
idx = html.find('handleConnection')
print(html[idx-50:idx+800].encode('utf-8', 'ignore').decode('utf-8', 'ignore'))
