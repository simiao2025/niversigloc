import os
from bs4 import BeautifulSoup
import datetime

html = '''<div class="widget-title" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 10px 10px 0 0;">
    <span class="icon"><i class="fa fa-birthday-cake"></i></span>
    <h5 style="color: white; margin: 0; padding: 5px 0;">Aniversariantes do Mês</h5>
</div>
<div class="widget-box">
<div class="widget-content" style="overflow:auto;height:350px; border-radius: 0 0 10px 10px;">
    <div class="row-fluid">
        <div class="col-md-12 table-responsive">
              <table class="table table-hover" style="margin-bottom: 0;">
                    <tbody>
                        <tr ><td width="8%"></td><td width="22%" style="font-weight: 500; vertical-align: middle;"><i class="fa fa-calendar-o" style="margin-right: 5px; color: #95a5a6;"></i>10/06/1972</td><td width="50%" style="vertical-align: middle;"><span style="font-size: 14px;">WANDERLÚCIA MARQUES DA SILVA</span></td><td width="20%" style="text-align: center; vertical-align: middle;"><span style="color: #7f8c8d; font-weight: 500;">54 Anos</span></td></tr>
'''

resultados = []
soup = BeautifulSoup(html, 'html.parser')
widgets = soup.find_all(class_='widget-box')
alvo = None
for w in widgets:
    if 'Aniversariantes do Mês'.lower() in w.text.lower():
        alvo = w
        break
if not alvo: 
    print('[!] Widget não apareceu.')
linhas = alvo.select('table tbody tr')
for tr in linhas:
    colunas = tr.find_all('td')
    if len(colunas) >= 4:
        d_raw = colunas[1].text.strip()
        n = colunas[2].text.strip()
        t = colunas[3].text.strip()
        print(f'Extracted: {d_raw}, {n}, {t}')
