app = open('app.py', encoding='utf-8').read()
idx = app.find('Não foi')
print(app[idx-300:idx+300].encode('ascii', 'ignore').decode('ascii'))
