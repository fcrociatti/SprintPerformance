import streamlit as st
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, timezone
import pandas as pd
from sqlalchemy import text 

conn = st.connection("banco_dds", type="sql") 

JIRA_URL = st.secrets["JIRA_URL"]
JIRA_USER = st.secrets["JIRA_USER"]
JIRA_TOKEN = st.secrets["JIRA_TOKEN"]

CUSTOM_POINT_FIELD = "customfield_10069" 
CUSTOM_DATE_FIELD = "customfield_10231" 
CUSTOM_CLIENTE_FIELD = "customfield_10133" 

TIPOS_SUSTENTACAO = ["erro", "atendimento","Retorno Negativo (RN)"]
status_alvo = [
    "3.3 Revisão de Código","4.0 A testar", "4.2 Mergear", "4.3 Pend. Versão",
    "4.4 A Testar (homologação)", "4.5 A testar (artefato)",
    "5.3 Pendência de Homolog", "6.0 Concluído",
    "6.1 Pend. Gerar Artefatos", "6.2 Pend. Envio Homolog."
]

headers = {"Accept": "application/json", "Content-Type": "application/json"}
auth = HTTPBasicAuth(JIRA_USER, JIRA_TOKEN)

periodos = []

def extrair_cliente(issue_fields):
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
            
            resumo = issue["fields"].get("summary", "Sem resumo")
            cliente_nome = extrair_cliente(issue["fields"])
                
            dados.append({
                "Key": key, 
                "Data_Transicao": data_transicao.strftime("%Y-%m-%d %H:%M:%S"), # (ALTERADO AGORA) Formato MySQL
                "Responsável": dev,
                "Tipo": tipo_item_nome, 
                "Pontos_Sustentacao": pontos_sustentacao, 
                "Pontos_Desenvolvimento": pontos_desenvolvimento,
                "Resumo": resumo, 
                "Cliente": cliente_nome
            })

        if data_json.get("isLast") or not data_json.get("issues", []): break
        next_token = data_json.get("nextPageToken")
        if not next_token: break

    return dados

# Hardcode de analistas mantido para a v1 (ALTERADO AGORA)
ANALISTAS = ["Fernando", "Anderson", "Gustavo", "Nathan"]

def extrair_e_salvar_backlog(projeto, sprint_id):
    dados_backlog = []
    next_token = ""
    
    jql_backlog = (
        f'type != bug AND project = "{projeto}" '
        f'AND Sprint in (openSprints(),EMPTY) '
        f'AND status NOT IN ("6.0 Concluído", "6.0 Pend. Merge p/ Homol.", "6.1 Pend. Gerar Artefatos", "6.2 Pend. Envio Homolog.", "7.0 Dispensado", "5.0 Pendência do Usuário", "5.1 Esperando por Aprovação", "5.2 Comercial - Aprovado", "5.3 Pendência de Homolog", "3.3 Revisão de Código", "4.0 A testar", "4.1 Testando", "4.2 Mergear", "4.3 Pend. Versão") '
        f'ORDER BY created DESC'
    )

    while True:
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
            
            assignee = issue["fields"].get("assignee")
            dev_nome = assignee["displayName"] if assignee else "Sem responsável"
            
            typeIssue = issue["fields"].get("issuetype") 
            tipo_item_nome = typeIssue["name"].lower() if typeIssue else "sem tipo"

            papel = "Analista" if any(analista in dev_nome for analista in ANALISTAS) else "Desenvolvedor"
            
            resumo = issue["fields"].get("summary", "Sem resumo")
            cliente_nome = extrair_cliente(issue["fields"])

            data_criacao_raw = issue["fields"].get("created", "")
            data_criacao = data_criacao_raw[:10] if data_criacao_raw else "2000-01-01"

            dados_backlog.append({
                "ID_SPRINT": sprint_id, # (ALTERADO AGORA) Nomenclatura DDS
                "ISSUE_KEY": key,
                "PROJETO": projeto,
                "RESPONSAVEL": dev_nome,
                "PAPEL": papel,
                "TIPO_ITEM": tipo_item_nome,
                "RESUMO": resumo,
                "CLIENTE": cliente_nome, 
                "DATA_CRIACAO" : data_criacao
            })

        if data_json.get("isLast") or not data_json.get("issues", []): break
        next_token = data_json.get("nextPageToken")
        if not next_token: break

    # Gravação no MySQL usando ON DUPLICATE KEY UPDATE (ALTERADO AGORA)
    if dados_backlog:
        try:
            query = text("""
                INSERT INTO TB_SPRINT_BACKLOG 
                (ID_SPRINT, ISSUE_KEY, PROJETO, RESPONSAVEL, PAPEL, TIPO_ITEM, RESUMO, CLIENTE, DATA_CRIACAO)
                VALUES 
                (:ID_SPRINT, :ISSUE_KEY, :PROJETO, :RESPONSAVEL, :PAPEL, :TIPO_ITEM, :RESUMO, :CLIENTE, :DATA_CRIACAO)
                ON DUPLICATE KEY UPDATE 
                RESPONSAVEL = VALUES(RESPONSAVEL), PAPEL = VALUES(PAPEL), 
                TIPO_ITEM = VALUES(TIPO_ITEM), RESUMO = VALUES(RESUMO), CLIENTE = VALUES(CLIENTE)
            """)
            with conn.session as s:
                s.execute(query, dados_backlog)
                s.commit()
            print(f"✅ Backlog da Sprint ({len(dados_backlog)} itens) salvo no MySQL!")
        except Exception as e:
            print(f"❌ Erro ao salvar backlog no MySQL: {e}")

# Função renomeada e adaptada para MySQL (ALTERADO AGORA)
def sincronizar_com_banco(dados_extracao, projeto_nome, sprint_id):
    if not dados_extracao: return
    payload = []
    for item in dados_extracao:
        payload.append({
            "ISSUE_KEY": item["Key"], 
            "PROJETO": projeto_nome, 
            "RESPONSAVEL": item["Responsável"],
            "TIPO_ITEM": item["Tipo"], 
            "CATEGORIA": "Sustentação" if item["Pontos_Sustentacao"] > 0 else "Desenvolvimento",
            "PONTOS": item["Pontos_Sustentacao"] + item["Pontos_Desenvolvimento"],
            "DATA_CONCLUSAO": item["Data_Transicao"], 
            "ID_SPRINT": sprint_id,
            "RESUMO": item["Resumo"], 
            "CLIENTE": item["Cliente"] 
        })
    
    try:
        query = text("""
            INSERT INTO TB_SPRINT_DETAILS 
            (ISSUE_KEY, PROJETO, RESPONSAVEL, TIPO_ITEM, CATEGORIA, PONTOS, DATA_CONCLUSAO, ID_SPRINT, RESUMO, CLIENTE)
            VALUES 
            (:ISSUE_KEY, :PROJETO, :RESPONSAVEL, :TIPO_ITEM, :CATEGORIA, :PONTOS, :DATA_CONCLUSAO, :ID_SPRINT, :RESUMO, :CLIENTE)
            ON DUPLICATE KEY UPDATE 
            RESPONSAVEL = VALUES(RESPONSAVEL), TIPO_ITEM = VALUES(TIPO_ITEM), CATEGORIA = VALUES(CATEGORIA), 
            PONTOS = VALUES(PONTOS), DATA_CONCLUSAO = VALUES(DATA_CONCLUSAO), CLIENTE = VALUES(CLIENTE), RESUMO = VALUES(RESUMO)
        """)
        with conn.session as s:
            s.execute(query, payload)
            s.commit()
    except Exception as e:
        print(f"Erro na sincronização de detalhes: {e}")

# Função adaptada para ler e gravar no MySQL (ALTERADO AGORA)
def obter_ou_criar_sprint(inicio, fim, descricao):
    dt_inicio = inicio.date() if isinstance(inicio, datetime) else inicio
    dt_fim = fim.date() if isinstance(fim, datetime) else fim
    
    if (dt_fim - dt_inicio).days != 13:
        return None, f"A sprint deve ter exatos 14 dias. A sua tem {(dt_fim - dt_inicio).days + 1} dias."

    inicio_str = dt_inicio.strftime("%Y-%m-%d")
    fim_str = dt_fim.strftime("%Y-%m-%d")
    nome_sprint = f"Sprint {dt_inicio.strftime('%d/%m')} a {dt_fim.strftime('%d/%m')}"

    # Busca no MySQL e transforma em lista de dicts para manter a lógica original (ALTERADO AGORA)
    df_sprints = conn.query("SELECT * FROM TB_SPRINT ORDER BY DATA_FIM DESC")
    sprints_existentes = df_sprints.to_dict('records')

    for sp in sprints_existentes:
        # Tratamento de data caso o pandas converta para objeto Date (ALTERADO AGORA)
        sp_inicio_str = sp['DATA_INICIO'].strftime("%Y-%m-%d") if not isinstance(sp['DATA_INICIO'], str) else sp['DATA_INICIO']
        sp_fim_str = sp['DATA_FIM'].strftime("%Y-%m-%d") if not isinstance(sp['DATA_FIM'], str) else sp['DATA_FIM']

        if sp_inicio_str == inicio_str and sp_fim_str == fim_str:
            return sp['ID_SPRINT'], "Sprint existente encontrada e vinculada."

    for sp in sprints_existentes:
        sp_inicio = sp['DATA_INICIO'] if not isinstance(sp['DATA_INICIO'], str) else datetime.strptime(sp['DATA_INICIO'], "%Y-%m-%d").date()
        sp_fim = sp['DATA_FIM'] if not isinstance(sp['DATA_FIM'], str) else datetime.strptime(sp['DATA_FIM'], "%Y-%m-%d").date()
        
        if dt_inicio <= sp_fim and dt_fim >= sp_inicio:
            return None, f"Sobreposição detectada com a {sp['NOME_SPRINT']}."

    # Grava a nova Sprint e captura o ID gerado pelo AUTO_INCREMENT (ALTERADO AGORA)
    nova_sprint = {"nome": nome_sprint, "inicio": inicio_str, "fim": fim_str, "descricao": descricao}
    try:
        with conn.session as s:
            result = s.execute(text("""
                INSERT INTO TB_SPRINT (NOME_SPRINT, DATA_INICIO, DATA_FIM, DESCRICAO) 
                VALUES (:nome, :inicio, :fim, :descricao)
            """), nova_sprint)
            s.commit()
            novo_id = result.lastrowid # Pega o ID_SPRINT que o MySQL acabou de criar
        return novo_id, "Nova Sprint cadastrada com sucesso no banco!"
    except Exception as e:
        return None, f"Erro ao criar Sprint no banco: {e}"

def executar_extracao(data_inicio_input, data_fim_input, descricao_input):
    global periodos
    
    inicio = datetime.combine(data_inicio_input, datetime.min.time()).replace(tzinfo=timezone.utc)
    fim = datetime.combine(data_fim_input, datetime.max.time()).replace(tzinfo=timezone.utc)
    periodos = [(inicio, fim)]
    
    id_sprint, msg_validacao = obter_ou_criar_sprint(inicio, fim, descricao_input)
    
    if not id_sprint:
        return False, msg_validacao 
        
    try:
        dados_star_pontos = obter_dados_projeto("STAR")
        sincronizar_com_banco(dados_star_pontos, "STAR", id_sprint) # (ALTERADO AGORA)
        
        hoje = datetime.now(timezone.utc)
        
        if fim >= hoje:
            extrair_e_salvar_backlog("STAR", id_sprint)
            status_backlog = "Pontos e Snapshot do Backlog atualizados."
        else:
            status_backlog = "Apenas pontos atualizados (Snapshot do Backlog preservado, pois a sprint já foi encerrada)."
            print(f"🔒 Sprint encerrada em {fim.strftime('%d/%m/%Y')}. Snapshot do backlog preservado.")
        
        return True, f"{msg_validacao} {status_backlog}"
        
    except Exception as e:
        return False, f"Erro na extração combinada: {e}"