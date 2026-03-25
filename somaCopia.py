import streamlit as st
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, timezone
import pandas as pd
from supabase import create_client, Client

# --- Configurações ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ... (resto do seu código)
JIRA_URL = st.secrets["JIRA_URL"]
JIRA_USER = st.secrets["JIRA_USER"]
JIRA_TOKEN = st.secrets["JIRA_TOKEN"]

CUSTOM_POINT_FIELD = "customfield_10069" 
CUSTOM_DATE_FIELD = "customfield_10231" 
CUSTOM_CLIENTE_FIELD = "customfield_10133" # <--- NOVO: Campo de Cliente

TIPOS_SUSTENTACAO = ["erro", "atendimento","Retorno Negativo (RN)"]
status_alvo = [
    "3.3 Revisão de Código","4.0 A testar", "4.2 Mergear", "4.3 Pend. Versão",
    "4.4 A Testar (homologação)", "4.5 A testar (artefato)",
    "5.3 Pendência de Homolog", "6.0 Concluído",
    "6.1 Pend. Gerar Artefatos", "6.2 Pend. Envio Homolog."
]

headers = {"Accept": "application/json", "Content-Type": "application/json"}
auth = HTTPBasicAuth(JIRA_USER, JIRA_TOKEN)

# Variável global que será preenchida pelo Streamlit
periodos = []

def extrair_cliente(issue_fields):
    """Função de segurança para extrair o nome do cliente não importando o formato do JSON"""
    cliente_raw = issue_fields.get(CUSTOM_CLIENTE_FIELD)
    if cliente_raw:
        if isinstance(cliente_raw, dict) and "value" in cliente_raw:
            return cliente_raw["value"]
        elif isinstance(cliente_raw, str):
            return cliente_raw
        else:
            return str(cliente_raw)
    return "Sem Cliente"


def obter_dados_projeto(projeto):
    dados = []
    next_token = ""
    while True:
        jql = f'project = "{projeto}" AND TYPE != Bug ORDER BY created DESC'
        
        params = {"jql": jql, "fields": f"{CUSTOM_POINT_FIELD},{CUSTOM_DATE_FIELD},assignee,status,issuetype,summary,{CUSTOM_CLIENTE_FIELD},created", "expand": "changelog", "maxResults": 50}
        
        if next_token: params["nextPageToken"] = next_token
        resp = requests.get(f"{JIRA_URL}/rest/api/3/search/jql", headers=headers, auth=auth, params=params)
        
        try: resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            return dados
            
        data_json = resp.json()

        for issue in data_json["issues"]:
            key = issue["key"]
            changelog = issue.get("changelog", {}).get("histories", [])
            data_transicao = None

            for hist in sorted(changelog, key=lambda x: x["created"]):
                for item in hist.get("items", []):
                    if item["field"] == "status" and item["toString"] in status_alvo:
                        data_transicao = datetime.fromisoformat(hist["created"].replace("Z", "+00:00"))
                        break
                if data_transicao: break

            if not data_transicao: continue

            periodo_sprint = None
            periodo_inicio = None
            for (ini, f) in periodos:
                if ini <= data_transicao <= f:
                    periodo_sprint = ini.strftime("%Y-%m-%d")
                    periodo_inicio = ini
                    break

            if not periodo_sprint: continue

            assignee = issue["fields"].get("assignee")
            dev = assignee["displayName"] if assignee else "Sem responsável"
            pontos_raw = issue["fields"].get(CUSTOM_POINT_FIELD)
            try: pontos = int(pontos_raw["value"]) if pontos_raw and "value" in pontos_raw else 0
            except (ValueError, TypeError): pontos = 0
            
            typeIssue = issue["fields"].get("issuetype") 
            tipo_item_nome = typeIssue["name"].lower() if typeIssue else "sem tipo"
            
            pontos_sustentacao = pontos if tipo_item_nome in TIPOS_SUSTENTACAO else 0
            pontos_desenvolvimento = pontos if tipo_item_nome not in TIPOS_SUSTENTACAO else 0
            
            # --- NOVOS CAMPOS ---
            resumo = issue["fields"].get("summary", "Sem resumo")
            cliente_nome = extrair_cliente(issue["fields"])
                
            dados.append({
                "Key": key, "Data_Transicao": data_transicao.isoformat(), "Responsável": dev,
                "Tipo": tipo_item_nome, "Pontos_Sustentacao": pontos_sustentacao, "Pontos_Desenvolvimento": pontos_desenvolvimento,
                "Resumo": resumo, "Cliente": cliente_nome
            })

        if data_json.get("isLast") or not data_json.get("issues", []): break
        next_token = data_json.get("nextPageToken")
        if not next_token: break

    return dados

# Hardcode inicial (conforme alinhado)
ANALISTAS = ["Fernando", "Anderson", "Gustavo", "Nathan"]

def extrair_e_salvar_backlog(projeto, sprint_id):
    """
    Roda o JQL de itens pendentes na sprint e salva um "snapshot" na tabela sprint_backlog.
    """
    dados_backlog = []
    next_token = ""
    
    # O JQL exato que você forneceu
    jql_backlog = (
        f'type != bug AND project = "{projeto}" '
        f'AND Sprint in (openSprints(),EMPTY) '
        f'AND status NOT IN ("6.0 Concluído", "6.0 Pend. Merge p/ Homol.", "6.1 Pend. Gerar Artefatos", "6.2 Pend. Envio Homolog.", "7.0 Dispensado", "5.0 Pendência do Usuário", "5.1 Esperando por Aprovação", "5.2 Comercial - Aprovado", "5.3 Pendência de Homolog", "3.3 Revisão de Código", "4.0 A testar", "4.1 Testando", "4.2 Mergear", "4.3 Pend. Versão") '
        f'ORDER BY created DESC'
    )

    while True:
        # --- Modificado para incluir summary e customfield_10133 ---
        params = {
            "jql": jql_backlog,
            "fields": f"assignee,issuetype,summary,{CUSTOM_CLIENTE_FIELD},created",
            "maxResults": 50
        }
        
        if next_token: params["nextPageToken"] = next_token
        resp = requests.get(f"{JIRA_URL}/rest/api/3/search/jql", headers=headers, auth=auth, params=params)
        
        try: resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print(f"Erro ao buscar backlog: {e}")
            break

        data_json = resp.json()

        for issue in data_json.get("issues", []):
            key = issue["key"]
            
            # Obtém responsável
            assignee = issue["fields"].get("assignee")
            dev_nome = assignee["displayName"] if assignee else "Sem responsável"
            
            # Obtém tipo do item
            typeIssue = issue["fields"].get("issuetype") 
            tipo_item_nome = typeIssue["name"].lower() if typeIssue else "sem tipo"

            # Define o papel baseado no Hardcode que você pediu
            papel = "Analista" if any(analista in dev_nome for analista in ANALISTAS) else "Desenvolvedor"
            
            # --- NOVOS CAMPOS ---
            resumo = issue["fields"].get("summary", "Sem resumo")
            cliente_nome = extrair_cliente(issue["fields"])

            data_criacao_raw = issue["fields"].get("created", "")
            data_criacao = data_criacao_raw[:10] if data_criacao_raw else "2000-01-01"


            dados_backlog.append({
                "sprint_id": sprint_id,
                "issue_key": key,
                "projeto": projeto,
                "responsavel": dev_nome,
                "papel": papel,
                "tipo_item": tipo_item_nome,
                "resumo": resumo,
                "cliente": cliente_nome, 
                "data_criacao" : data_criacao
            })

        if data_json.get("isLast") or not data_json.get("issues", []): break
        next_token = data_json.get("nextPageToken")
        if not next_token: break

    # Salva no banco de dados
    if dados_backlog:
        try:
            # upsert garante que se rodar hoje e amanhã, ele atualiza a mesma issue na mesma sprint
            supabase.table("sprint_backlog").upsert(dados_backlog, on_conflict="sprint_id, issue_key").execute()
            print(f"✅ Backlog da Sprint ({len(dados_backlog)} itens) salvo com sucesso!")
        except Exception as e:
            print(f"❌ Erro ao salvar backlog no Supabase: {e}")

def sincronizar_com_supabase(dados_extracao, projeto_nome, sprint_id):
    if not dados_extracao: return
    payload = []
    for item in dados_extracao:
        payload.append({
            "issue_key": item["Key"], "projeto": projeto_nome, "responsavel": item["Responsável"],
            "tipo_item": item["Tipo"], "categoria": "Sustentação" if item["Pontos_Sustentacao"] > 0 else "Desenvolvimento",
            "pontos": item["Pontos_Sustentacao"] + item["Pontos_Desenvolvimento"],
            "data_conclusao": item["Data_Transicao"], "sprint_id": sprint_id,
            "resumo": item["Resumo"], "cliente": item["Cliente"] # <--- ENVIANDO PARA O BANCO
        })
    supabase.table("sprint_details").upsert(payload, on_conflict="issue_key").execute()


def obter_ou_criar_sprint(inicio, fim, descricao):
    dt_inicio = inicio.date() if isinstance(inicio, datetime) else inicio
    dt_fim = fim.date() if isinstance(fim, datetime) else fim
    
    if (dt_fim - dt_inicio).days != 13:
        return None, f"A sprint deve ter exatos 14 dias. A sua tem {(dt_fim - dt_inicio).days + 1} dias."

    inicio_str = dt_inicio.strftime("%Y-%m-%d")
    fim_str = dt_fim.strftime("%Y-%m-%d")
    nome_sprint = f"Sprint {dt_inicio.strftime('%d/%m')} a {dt_fim.strftime('%d/%m')}"

    resposta = supabase.table("sprints_master").select("*").order("data_fim", desc=True).execute()
    sprints_existentes = resposta.data

    for sp in sprints_existentes:
        if sp['data_inicio'] == inicio_str and sp['data_fim'] == fim_str:
            # Opcional: Atualizar a descrição se já existir, mas por enquanto apenas retornamos
            return sp['id'], "Sprint existente encontrada e vinculada."

    for sp in sprints_existentes:
        sp_inicio = datetime.strptime(sp['data_inicio'], "%Y-%m-%d").date()
        sp_fim = datetime.strptime(sp['data_fim'], "%Y-%m-%d").date()
        if dt_inicio <= sp_fim and dt_fim >= sp_inicio:
            return None, f"Sobreposição detectada com a {sp['nome_sprint']}."

    # Aqui incluímos a descrição que vem da tela
    nova_sprint = {"nome_sprint": nome_sprint, "data_inicio": inicio_str, "data_fim": fim_str, "descricao": descricao}
    insercao = supabase.table("sprints_master").insert(nova_sprint).execute()
    return insercao.data[0]['id'], "Nova Sprint cadastrada com sucesso!"

def executar_extracao(data_inicio_input, data_fim_input, descricao_input):
    global periodos
    
    inicio = datetime.combine(data_inicio_input, datetime.min.time()).replace(tzinfo=timezone.utc)
    # Colocamos o fim para as 23:59:59 do último dia para garantir a cobertura completa
    fim = datetime.combine(data_fim_input, datetime.max.time()).replace(tzinfo=timezone.utc)
    periodos = [(inicio, fim)]
    
    id_sprint, msg_validacao = obter_ou_criar_sprint(inicio, fim, descricao_input)
    
    if not id_sprint:
        return False, msg_validacao 
        
    try:
        # 1. Busca os pontos entregues (Sempre roda para garantir correções de pontuação tardias)
        dados_star_pontos = obter_dados_projeto("STAR")
        sincronizar_com_supabase(dados_star_pontos, "STAR", id_sprint)
        
        # --- A NOVA TRAVA DE SEGURANÇA AQUI ---
        hoje = datetime.now(timezone.utc)
        
        # 2. Busca a "Fotografia" do Backlog apenas se a sprint ainda estiver ativa ou no futuro
        if fim >= hoje:
            extrair_e_salvar_backlog("STAR", id_sprint)
            status_backlog = "Pontos e Snapshot do Backlog atualizados."
        else:
            status_backlog = "Apenas pontos atualizados (Snapshot do Backlog preservado, pois a sprint já foi encerrada)."
            print(f"🔒 Sprint encerrada em {fim.strftime('%d/%m/%Y')}. Snapshot do backlog preservado.")
        
        return True, f"{msg_validacao} {status_backlog}"
        
    except Exception as e:
        return False, f"Erro na extração combinada: {e}"
