import requests
from requests.auth import HTTPBasicAuth

# As suas credenciais

JIRA_URL = st.secrets["JIRA_URL"]
JIRA_USER = st.secrets["JIRA_USER"]
JIRA_TOKEN = st.secrets["JIRA_TOKEN" ] 

auth = HTTPBasicAuth(JIRA_USER, JIRA_TOKEN)
headers = {"Accept": "application/json"}

print("A procurar o campo Cliente no Jira...")
resposta = requests.get(f"{JIRA_URL}/rest/api/3/field", auth=auth, headers=headers)

if resposta.status_code == 200:
    campos = resposta.json()
    encontrados = 0
    for campo in campos:
        nome_campo = campo.get("name", "").lower()
        if "cliente" in nome_campo:
            print(f"✅ ENCONTREI! Nome: '{campo['name']}' -> ID: {campo['id']}")
            encontrados += 1
            
    if encontrados == 0:
        print("❌ Não encontrei nenhum campo com a palavra 'cliente'. Pode ter outro nome?")
else:
    print(f"Erro na requisição: {resposta.status_code}")