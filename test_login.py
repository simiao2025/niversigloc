import requests
import re

html = requests.get('https://www.sigloc.com.br/login/').text
print('Action:', re.findall(r'action=[\"\'](.*?)[\"\']', html))
print('Inputs:', re.findall(r'name=[\"\'](.*?)[\"\']', html))
