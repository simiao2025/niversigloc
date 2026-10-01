import os, requests
from dotenv import load_dotenv
load_dotenv()
headers = {'apikey': os.getenv('SUPABASE_SERVICE_ROLE_KEY'), 'Authorization': 'Bearer ' + os.getenv('SUPABASE_SERVICE_ROLE_KEY')}
res = requests.get(f'{os.getenv("SUPABASE_URL")}/rest/v1/profiles?select=*', headers=headers)
if res.status_code == 200:
    print('Profiles:', len(res.json()))
else:
    print(res.text)
