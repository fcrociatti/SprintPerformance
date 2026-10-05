import streamlit as st
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, timedelta, timezone
import pandas as pd
from sqlalchemy import text
import time

conn = st.connection("banco_dds", type="sql") 

JIRA_URL = st.secrets["JIRA_URL"]
JIRA_USER = st.secrets["JIRA_USER"]
JIRA_TOKEN = st.secrets["JIRA_TOKEN"]

CUSTOM_SISTEMA_FIELD = "customfield_10079"
CUSTOM_POINT_FIELD = "customfield_10069" 
CUSTOM_DATE_FIELD = "customfield_10231" 
CUSTOM_CLIENTE_FIELD = "customfield_10133"  
CUSTOM_DEV_INICIAL_FIELD = "customfield_10594"


TIPOS_SUSTENTACAO = ["erro", "atendimento","Retorno Negativo (RN)"]

ANALISTAS = ["Fernando", "Jonathan Ferreira", "Thiago", "Paulo Domingues", "Kaic de Castro", "Enzo"]
status_alvo = [
    "3.3 Revisão de Código","4.0 A TESTAR", "4.2 Mergear", "4.3 Pend. Versão",
    "4.4 A Testar (homologação)", "4.5 A testar (artefato)", "3.2 Reprovados",
    "5.3 Pendência de Homolog", "6.0 Concluído",
    "6.1 Pend. Gerar Artefatos", "6.2 Pend. Envio Homolog."
]

# Ciclo total do burndown (até 6.0 Concluído).
STATUS_FIM_CICLO_TOTAL = "6.0 Concluído"
# Entre 3.3 e 6.0, sem 5.0/5.1/5.2 e 7.0 (os demais status já são contados no backlog).
STATUS_POS_DESENVOLVIMENTO = [
    "3.3 Revisão de Código", "4.0 A TESTAR", "4.1 Testando", "4.2 Mergear", "4.3 Pend. Versão",
    "5.3 Pendência de Homolog", "6.0 Pend. Merge p/ Homol.", "6.1 Pend. Gerar Artefatos", "6.2 Pend. Envio Homolog."
]
# Preenchida por obter_dados_projeto: itens que entraram em 6.0 Concluído dentro do período da sprint.
conclusoes_ciclo_total = []

headers = {"Accept": "application/json", "Content-Type": "application/json"}
auth = HTTPBasicAuth(JIRA_USER, JIRA_TOKEN)

periodos = []

# Fuso da equipe (Brasília, sem horário de verão desde 2019). Os limites da sprint
# eram montados em UTC: a sprint terminava às 20:59 do último dia e começava às
# 21:00 da véspera, então issues movidas à noite caíam na sprint errada ou em
# nenhuma (ex.: STAR-7827 e STAR-9014, movidas em 20/09 após as 22h).
FUSO_EQUIPE = timezone(timedelta(hours=-3))


def periodo_sprint(data_inicio, data_fim):
    """Início e fim da sprint como datetimes com fuso, do 00:00 ao 23:59:59 de Brasília."""
    inicio = datetime.combine(data_inicio, datetime.min.time()).replace(tzinfo=FUSO_EQUIPE)
    fim = datetime.combine(data_fim, datetime.max.time()).replace(tzinfo=FUSO_EQUIPE)
    return inicio, fim

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

def extrair_sistema(issue_fields):
    sistema_raw = issue_fields.get(CUSTOM_SISTEMA_FIELD)
    if sistema_raw:
        if isinstance(sistema_raw, dict) and "value" in sistema_raw:
            return sistema_raw["value"]
        elif isinstance(sistema_raw, str):
            return sistema_raw
        else:
            return str(sistema_raw)
    return "Sem Sistema"

def extrair_dev_inicial(issue_fields):
    """
    Campo "Dev Inicial" do Jira: usado na Gestão de RN's pra saber quem
    originalmente trabalhou no item pai, independente de quem é o RESPONSAVEL
    atual. Se o campo estiver vazio no Jira (ou o ID do campo ainda não tiver
    sido configurado em CUSTOM_DEV_INICIAL_FIELD), retorna None -> a info fica
    em branco na tela, em vez de mostrar um valor incorreto/adivinhado.
    """
    raw = issue_fields.get(CUSTOM_DEV_INICIAL_FIELD)
    if not raw:
        return None
    if isinstance(raw, dict):
        # Campo de usuário do Jira normalmente vem como {"displayName": "...", ...}
        return raw.get("displayName") or raw.get("value") or None
    if isinstance(raw, str):
        return raw
    return str(raw)

def obter_dados_projeto(projeto):
    dados = []
    conclusoes_ciclo_total.clear()
    next_token = ""
    while True:
        jql = f'project = "{projeto}" AND TYPE != Bug ORDER BY created DESC'
        
        params = {"jql": jql, "fields": f"{CUSTOM_SISTEMA_FIELD},{CUSTOM_POINT_FIELD},{CUSTOM_DATE_FIELD},{CUSTOM_DEV_INICIAL_FIELD},assignee,status,issuetype,summary,{CUSTOM_CLIENTE_FIELD},duedate,created", "expand": "changelog", "maxResults": 25}
        
        if next_token: params["nextPageToken"] = next_token
        resp = requests.get(f"{JIRA_URL}/rest/api/3/search/jql", headers=headers, auth=auth, params=params, timeout=60)
        
        try: resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            return dados
            
        data_json = resp.json()

        for issue in data_json["issues"]:
            key = issue["key"]
            changelog = issue.get("changelog", {}).get("histories", [])
            
            status_alvo_lower = [s.lower() for s in status_alvo]
            datas_entrada_alvo = []

            for hist in sorted(changelog, key=lambda x: x["created"], reverse=True):
                for item in hist.get("items", []):
                    if item["field"] == "status":
                        status_str = item.get("toString", "").lower()
                        if status_str in status_alvo_lower:
                            dt = datetime.fromisoformat(hist["created"].replace("Z", "+00:00"))
                            datas_entrada_alvo.append(dt)

            # Ciclo total: última entrada em 6.0 no período. Antes dos "continue": o item pode ter entrado em 3.3 em outra sprint.
            datas_fim_ciclo = [
                datetime.fromisoformat(hist["created"].replace("Z", "+00:00"))
                for hist in changelog
                for item in hist.get("items", [])
                if item["field"] == "status" and item.get("toString", "").lower() == STATUS_FIM_CICLO_TOTAL.lower()
            ]
            datas_fim_no_periodo = [dt for dt in datas_fim_ciclo if any(ini <= dt <= f for (ini, f) in periodos)]
            if datas_fim_no_periodo:
                tipo_ct = issue["fields"].get("issuetype")
                conclusoes_ciclo_total.append({
                    "ISSUE_KEY": key,
                    "TIPO_ITEM": tipo_ct["name"].lower() if tipo_ct else "sem tipo",
                    # Gravado no horário de Brasília (mesmo fuso que define os limites da sprint).
                    "DATA_CONCLUSAO_TOTAL": max(datas_fim_no_periodo).astimezone(FUSO_EQUIPE).strftime("%Y-%m-%d %H:%M:%S"),
                })

            if datas_entrada_alvo:
                data_transicao = min(datas_entrada_alvo) 
            else:
                continue 

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
            try:
                if isinstance(pontos_raw, dict) and "value" in pontos_raw:
                    pontos = int(float(pontos_raw["value"]))
                elif pontos_raw is not None:
                    pontos = int(float(pontos_raw))
                else:
                    pontos = 0
            except (ValueError, TypeError):
                pontos = 0
            
            typeIssue = issue["fields"].get("issuetype") 
            tipo_item_nome = typeIssue["name"].lower() if typeIssue else "sem tipo"
            
            pontos_sustentacao = pontos if tipo_item_nome in TIPOS_SUSTENTACAO else 0
            pontos_desenvolvimento = pontos if tipo_item_nome not in TIPOS_SUSTENTACAO else 0
            
            resumo = issue["fields"].get("summary", "Sem resumo")
            cliente_nome = extrair_cliente(issue["fields"])
                
            status_info = issue["fields"].get("status")
            status_nome = status_info["name"] if status_info else "Desconhecido"

            sistema_nome = extrair_sistema(issue["fields"]) 

            data_limite_raw = issue["fields"].get("duedate")
            data_limite = data_limite_raw[:10] if data_limite_raw else None           

            data_criacao_raw = issue["fields"].get("created", "")
            data_criacao = data_criacao_raw[:10] if data_criacao_raw else "2000-01-01"

            campo_data_existente = issue["fields"].get(CUSTOM_DATE_FIELD)
            precisa_atualizar = False

            if campo_data_existente:
                data_existente_str = campo_data_existente.split("T")[0]
                data_esperada_str = periodo_inicio.strftime("%Y-%m-%d")
                
                if data_existente_str != data_esperada_str:
                    continue 
            else:
                precisa_atualizar = True

            dados.append({
                "Key": key, 
                "Data_Transicao": data_transicao.strftime("%Y-%m-%d %H:%M:%S"), 
                "Responsável": dev,
                "Tipo": tipo_item_nome, 
                "Pontos_Sustentacao": pontos_sustentacao, 
                "Pontos_Desenvolvimento": pontos_desenvolvimento,
                "Resumo": resumo, 
                "Cliente": cliente_nome,
                "Status" : status_nome,
                "Sistema" : sistema_nome,
                "data_limite": data_limite,
                "data_criacao": data_criacao,
                "Dev_Inicial": extrair_dev_inicial(issue["fields"])
            })

            data_iso = periodo_inicio.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0000"

            if precisa_atualizar:
                payload = {
                    "fields": {
                        CUSTOM_DATE_FIELD: data_iso
                    }
                }
                update_resp = requests.put(
                    f"{JIRA_URL}/rest/api/3/issue/{key}",
                    headers=headers,
                    auth=auth,
                    json=payload
                )

                if 'logs_jira' not in st.session_state:
                    st.session_state['logs_jira'] = []

                if update_resp.status_code == 204:
                    msg = (f"✅ Jira Atualizado: Issue {key} recebeu a data {data_iso}")
                    print(msg)
                    st.session_state['logs_jira'].append(msg)
                else:
                    msg = (f"❌ Falha ao atualizar Jira ({key}): {update_resp.text}")
                    print(msg)
                    st.session_state['logs_jira'].append(msg)

        if data_json.get("isLast") or not data_json.get("issues", []): break
        next_token = data_json.get("nextPageToken")
        if not next_token: break

    return dados

def limpar_snapshot_sprint(id_sprint, fase):
    try:

        conn.reset()
        with conn.session as s:
            if fase == "TODAS":
                s.execute(text("DELETE FROM TB_SPRINT_SNAPSHOT WHERE ID_SPRINT=:id"), {"id": id_sprint})
            else:
                s.execute(text("DELETE FROM TB_SPRINT_SNAPSHOT WHERE ID_SPRINT=:id AND FASE=:fase"), {"id": id_sprint, "fase": fase})
            
            s.execute(text("UPDATE TB_SPRINT SET ULTIMA_ATUALIZACAO = NOW() WHERE ID_SPRINT=:id"), {"id": id_sprint})
            s.commit()
            
        return True, f"✅ Snapshot de {fase} apagado com sucesso!"
    except Exception as e:
        return False, f"❌ Erro ao limpar o banco de dados: {e}"


def extrair_e_salvar_backlog(projeto, sprint_id):
    # Declarada diretamente no escopo local para garantir a leitura na instância
    ANALISTAS = ["Fernando", "Jonathan Ferreira", "Thiago", "Paulo Domingues", "Kaic de Castro", "Enzo"]
    
    dados_backlog = []
    
    status_ignorados = '"6.0 Concluído", "6.0 Pend. Merge p/ Homol.", "6.1 Pend. Gerar Artefatos", "6.2 Pend. Envio Homolog.", "7.0 Dispensado", "5.0 Pendência do Usuário", "5.1 Esperando por Aprovação", "5.2 Comercial - Aprovado", "5.3 Pendência de Homolog", "3.3 Revisão de Código", "4.0 A TESTAR", "4.1 Testando", "4.2 Mergear", "4.3 Pend. Versão"'
    
    # SIM = item já está na sprint de desenvolvimento ativa (planejado para dev).
    # NAO = item ainda está parado na sprint-backlog (1218), com analistas/gestão, sem dev planejado.
    # Importante: não incluir "EMPTY" na busca SIM -> item sem sprint nenhuma não é "planejado",
    # senão ele é contado como desenvolvimento indevidamente e nunca aparece em nenhuma das duas buscas.
    buscas = [
        {
            "sprint_nativa": "SIM",
            "jql": f'type not in( bug ) AND project in ("{projeto}") AND Sprint in (openSprints()) AND status NOT IN ({status_ignorados}) ORDER BY created DESC'
        },
        {
            "sprint_nativa": "NAO",
            "jql": f'type not in( bug ) AND project in ("{projeto}") AND Sprint = 1218 AND status NOT IN ({status_ignorados}) ORDER BY created DESC'
        }
    ]

    if 'logs_jira' not in st.session_state:
        st.session_state['logs_jira'] = []

    for busca in buscas:
        next_token = ""
        while True:
            params = {
                "jql": busca["jql"],
                "fields": f"assignee,issuetype,summary,{CUSTOM_CLIENTE_FIELD},{CUSTOM_SISTEMA_FIELD},duedate,created,status,{CUSTOM_POINT_FIELD},{CUSTOM_DEV_INICIAL_FIELD}",
                "maxResults": 25
            }
            
            if next_token: params["nextPageToken"] = next_token
            resp = requests.get(f"{JIRA_URL}/rest/api/3/search/jql", headers=headers, auth=auth, params=params, timeout=60)
            
            try: resp.raise_for_status()
            except requests.exceptions.HTTPError as e:
                # Antes esse erro só ia pro console (print) e sumia -> por isso "não achava nada"
                # sem explicação nenhuma. Agora ele fica visível no dashboard/log de sincronização.
                msg = (f"❌ Falha na busca de backlog [{projeto} / sprint_nativa={busca['sprint_nativa']}]: "
                       f"HTTP {resp.status_code} - {resp.text[:500]}")
                print(msg)
                st.session_state['logs_jira'].append(msg)
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

                status_info = issue["fields"].get("status")
                status_nome = status_info["name"] if status_info else "Desconhecido"

                sistema_nome = extrair_sistema(issue["fields"])

                data_limite_raw = issue["fields"].get("duedate")
                data_limite = data_limite_raw[:10] if data_limite_raw else None  

                pontos_raw = issue["fields"].get(CUSTOM_POINT_FIELD)
                try:
                    if isinstance(pontos_raw, dict) and "value" in pontos_raw:
                        pontos = str(pontos_raw["value"]) 
                    elif pontos_raw is not None:
                        pontos = str(pontos_raw)
                    else:
                        pontos = "0"
                except Exception:
                    pontos = "0"

                dados_backlog.append({
                    "ID_SPRINT": sprint_id, 
                    "ISSUE_KEY": key,
                    "PROJETO": projeto,
                    "RESPONSAVEL": dev_nome,
                    "PAPEL": papel,
                    "TIPO_ITEM": tipo_item_nome,
                    "RESUMO": resumo,
                    "CLIENTE": cliente_nome, 
                    "DATA_CRIACAO" : data_criacao,
                    "STATUS": status_nome, 
                    "SISTEMA" :  sistema_nome,
                    "DATA_LIMITE": data_limite,
                    "PONTOS": pontos,
                    "SPRINT_NATIVA": busca["sprint_nativa"],
                    "DEV_INICIAL": extrair_dev_inicial(issue["fields"])
                })

            if data_json.get("isLast") or not data_json.get("issues", []): break
            next_token = data_json.get("nextPageToken")
            if not next_token: break

    if dados_backlog:
        try:
            with conn.session as s:
                # Filtra por PROJETO também: sem isso, ao chamar essa função duas vezes
                # (uma por STAR, outra por ELFA) a segunda chamada apaga o resultado da primeira,
                # pois o DELETE limpava a sprint inteira em vez de só os itens daquele projeto.
                s.execute(text("DELETE FROM TB_SPRINT_BACKLOG WHERE ID_SPRINT = :id AND PROJETO = :projeto"), {"id": sprint_id, "projeto": projeto})
                s.commit()
            
            query = text("""
                INSERT INTO TB_SPRINT_BACKLOG 
                (ID_SPRINT, ISSUE_KEY, PROJETO, RESPONSAVEL, PAPEL, TIPO_ITEM, RESUMO, CLIENTE, DATA_CRIACAO, STATUS, SISTEMA, DATA_LIMITE, PONTOS, SPRINT_NATIVA, DEV_INICIAL)
                VALUES 
                (:ID_SPRINT, :ISSUE_KEY, :PROJETO, :RESPONSAVEL, :PAPEL, :TIPO_ITEM, :RESUMO, :CLIENTE, :DATA_CRIACAO, :STATUS, :SISTEMA, :DATA_LIMITE, :PONTOS, :SPRINT_NATIVA, :DEV_INICIAL)
            """)
            with conn.session as s:
                s.execute(query, dados_backlog)
                s.commit()
                        
            print(f"✅ Backlog da Sprint ({len(dados_backlog)} itens) salvo no MySQL!")
            
        except Exception as e:
            print(f"❌ Erro ao salvar backlog no MySQL: {e}")
            raise e

def salvar_conclusoes_ciclo_total(projeto, sprint_id):
    """Grava em TB_SPRINT_CONCLUSAO_TOTAL o que obter_dados_projeto coletou para o projeto.

    Isolada em try/except: se a tabela não existir ou der erro, a sincronização segue normal
    (só a visão de ciclo total do burndown fica sem dados).
    """
    try:
        with conn.session as s:
            s.execute(text("DELETE FROM TB_SPRINT_CONCLUSAO_TOTAL WHERE ID_SPRINT = :id AND PROJETO = :projeto"),
                      {"id": sprint_id, "projeto": projeto})
            if conclusoes_ciclo_total:
                s.execute(text("""
                    INSERT INTO TB_SPRINT_CONCLUSAO_TOTAL (ID_SPRINT, ISSUE_KEY, PROJETO, TIPO_ITEM, DATA_CONCLUSAO_TOTAL)
                    VALUES (:ID_SPRINT, :ISSUE_KEY, :PROJETO, :TIPO_ITEM, :DATA_CONCLUSAO_TOTAL)
                """), [{**c, "ID_SPRINT": sprint_id, "PROJETO": projeto} for c in conclusoes_ciclo_total])
            s.commit()
    except Exception as e:
        msg = f"⚠️ Ciclo total: falha ao salvar conclusões ({projeto}): {e}"
        print(msg)
        st.session_state.setdefault('logs_jira', []).append(msg)


def contar_pos_desenvolvimento(projeto):
    """Conta os itens entre 3.3 e 6.0 (STATUS_POS_DESENVOLVIMENTO), com o mesmo escopo das buscas
    do backlog: sprint em andamento (nativa) e sprint-backlog 1218.

    Retorna {"total", "sust", "desv", "total_nat", "sust_nat", "desv_nat"} ou None se alguma busca falhar
    (melhor ficar sem o número do que gravar uma contagem pela metade).
    """
    tipos_sust = ['erro', 'atendimento', 'retorno negativo (rn)']
    status_pos = ", ".join(f'"{s}"' for s in STATUS_POS_DESENVOLVIMENTO)
    buscas = {
        "SIM": f'type not in( bug ) AND project in ("{projeto}") AND Sprint in (openSprints()) AND status IN ({status_pos})',
        "NAO": f'type not in( bug ) AND project in ("{projeto}") AND Sprint = 1218 AND status IN ({status_pos})',
    }
    tipos_por_escopo = {"SIM": [], "NAO": []}

    for escopo, jql in buscas.items():
        next_token = ""
        while True:
            params = {"jql": jql, "fields": "issuetype", "maxResults": 100}
            if next_token: params["nextPageToken"] = next_token
            try:
                resp = requests.get(f"{JIRA_URL}/rest/api/3/search/jql", headers=headers, auth=auth, params=params, timeout=60)
                resp.raise_for_status()
            except requests.exceptions.RequestException as e:
                msg = f"⚠️ Ciclo total: falha ao contar itens pós-desenvolvimento [{projeto} / {escopo}]: {e}"
                print(msg)
                st.session_state.setdefault('logs_jira', []).append(msg)
                return None

            data_json = resp.json()
            for issue in data_json.get("issues", []):
                tipo = issue["fields"].get("issuetype")
                tipos_por_escopo[escopo].append(tipo["name"].lower() if tipo else "")

            if data_json.get("isLast") or not data_json.get("issues", []): break
            next_token = data_json.get("nextPageToken")
            if not next_token: break

    todos = tipos_por_escopo["SIM"] + tipos_por_escopo["NAO"]
    nativos = tipos_por_escopo["SIM"]
    sust = sum(1 for t in todos if t in tipos_sust)
    sust_nat = sum(1 for t in nativos if t in tipos_sust)
    return {
        "total": len(todos), "sust": sust, "desv": len(todos) - sust,
        "total_nat": len(nativos), "sust_nat": sust_nat, "desv_nat": len(nativos) - sust_nat,
    }


# Fila real da sprint: estado de cada item ao longo do tempo (sprint, status, tipo, responsável),
# reconstruído pelo histórico do Jira e gravado em TB_SPRINT_FILA_ESTADO.
CUSTOM_SPRINT_FIELD = "customfield_10020"
SPRINT_BACKLOG2_ID = "1218"
BOARDS_SPRINT = [6, 18]  # 6 = sprints STAR ("Sprint 58 - ..."), 18 = sprints ELFA ("Sprint Elfa 63")


def _dt_jira(valor):
    return datetime.fromisoformat(valor.replace("Z", "+00:00")) if valor else None


def _get_jira(url, params=None, tentativas=3):
    """GET no Jira com novas tentativas: a reconstrução faz dezenas de chamadas e uma queda de
    conexão no meio não pode derrubar o cálculo inteiro."""
    for n in range(tentativas):
        try:
            r = requests.get(url, headers=headers, auth=auth, params=params, timeout=90)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException:
            if n == tentativas - 1:
                raise
            time.sleep(5 * (n + 1))


def _sprints_dos_boards():
    """Todas as sprints dos boards (só leitura, API Agile): id -> (início, conclusão)."""
    sprints = {}
    for board in BOARDS_SPRINT:
        start = 0
        while True:
            js = _get_jira(f"{JIRA_URL}/rest/agile/1.0/board/{board}/sprint", {"startAt": start, "maxResults": 50})
            for sp in js.get("values", []):
                sprints[str(sp["id"])] = (_dt_jira(sp.get("startDate")), _dt_jira(sp.get("completeDate")))
            start += len(js.get("values", []))
            if js.get("isLast", True) or not js.get("values"): break
    return sprints


def calcular_fila_sprint(id_sprint, data_inicio, data_fim):
    """Reconstrói, pelo histórico do Jira, o estado de cada item durante a sprint.
    Só LÊ do Jira e não grava nada: devolve as linhas para TB_SPRINT_FILA_ESTADO."""
    inicio, fim = periodo_sprint(data_inicio, data_fim)
    agora = datetime.now(timezone.utc)
    fim_janela = min(fim, agora)
    em_andamento = fim > agora

    sprints = _sprints_dos_boards()
    fim_aberto = datetime.max.replace(tzinfo=timezone.utc)

    def ativas_em(t):
        # Mesma definição de openSprints(): iniciada e ainda não concluída.
        return {sid for sid, (ini, conc) in sprints.items() if ini and ini <= t and (conc or fim_aberto) > t}

    ids_na_janela = sorted(sid for sid, (ini, conc) in sprints.items()
                           if ini and ini <= fim_janela and (conc or fim_aberto) > inicio)
    filtro_sprint = f"Sprint in ({', '.join(ids_na_janela)}) OR " if ids_na_janela else ""
    # "updated >=": item tirado da sprint antes de ela fechar perde a sprint do campo Sprint.
    jql = (f'project in (STAR, ELFA) AND type != Bug AND created <= "{fim:%Y-%m-%d %H:%M}" AND '
           f'({filtro_sprint}Sprint = {SPRINT_BACKLOG2_ID} OR updated >= "{inicio:%Y-%m-%d}")')

    issues, token = [], ""
    while True:
        params = {"jql": jql, "fields": f"status,issuetype,project,assignee,created,{CUSTOM_SPRINT_FIELD}",
                  "expand": "changelog", "maxResults": 50}
        if token: params["nextPageToken"] = token
        js = _get_jira(f"{JIRA_URL}/rest/api/3/search/jql", params)
        issues += js.get("issues", [])
        token = js.get("nextPageToken")
        if js.get("isLast") or not token: break

    # A busca pode truncar o histórico de itens muito alterados -> completa pelo endpoint próprio.
    for it in issues:
        cl = it.get("changelog", {})
        if cl.get("total", 0) > len(cl.get("histories", [])):
            hs, start = [], 0
            while True:
                rr = _get_jira(f"{JIRA_URL}/rest/api/3/issue/{it['key']}/changelog", {"startAt": start, "maxResults": 100})
                hs += rr.get("values", []); start += len(rr.get("values", []))
                if rr.get("isLast", True) or not rr.get("values"): break
            it["changelog"] = {"histories": hs, "total": len(hs)}

    # Momentos em que a lista de sprints ativas muda (abertura/fechamento) também cortam os períodos.
    cortes_sprint = sorted({t for ini, conc in sprints.values() for t in (ini, conc) if t and inicio < t < fim_janela})

    linhas = []
    for it in issues:
        f = it["fields"]
        atual = {
            "status": f["status"]["name"], "tipo": f["issuetype"]["name"],
            "resp": (f.get("assignee") or {}).get("displayName") or "Sem responsável",
            "sprints": {str(sp["id"]) for sp in (f.get(CUSTOM_SPRINT_FIELD) or [])},
        }
        mudancas = sorted(
            [(_dt_jira(h["created"]), x) for h in it["changelog"]["histories"] for x in h["items"]
             if x["field"] in ("status", "Sprint", "issuetype", "assignee")],
            key=lambda m: m[0], reverse=True)

        def estado_em(t):
            # Parte do estado atual e desfaz, da mais recente para a mais antiga, as mudanças posteriores a t.
            e = dict(atual, sprints=set(atual["sprints"]))
            for quando, x in mudancas:
                if quando <= t: break
                if x["field"] == "status": e["status"] = x.get("fromString") or e["status"]
                elif x["field"] == "issuetype": e["tipo"] = x.get("fromString") or e["tipo"]
                elif x["field"] == "assignee": e["resp"] = x.get("fromString") or "Sem responsável"
                else: e["sprints"] = {v.strip() for v in (x.get("from") or "").split(",") if v.strip()}
            ativas = ativas_em(t)
            return (e["status"], e["tipo"].lower(), e["resp"],
                    1 if e["sprints"] & ativas else 0, 1 if SPRINT_BACKLOG2_ID in e["sprints"] else 0)

        criado = _dt_jira(f["created"])
        comeco = max(inicio, criado)
        if comeco >= fim_janela: continue
        cortes = sorted({comeco} | {q for q, _ in mudancas if comeco < q < fim_janela}
                        | {t for t in cortes_sprint if comeco < t})

        periodos = []
        for i, t in enumerate(cortes):
            est = estado_em(t)
            ate = cortes[i + 1] if i + 1 < len(cortes) else (None if em_andamento else fim_janela)
            if periodos and periodos[-1][0] == est:
                periodos[-1][2] = ate  # mesmo estado do período anterior: só estende
            else:
                periodos.append([est, t, ate])

        # Só interessam itens que em algum momento estiveram na sprint ativa ou no Backlog 2.
        if not any(p[0][3] or p[0][4] for p in periodos): continue
        local = lambda d: d.astimezone(FUSO_EQUIPE).replace(tzinfo=None) if d else None
        for (status, tipo, resp, em_sprint, em_b2), de, ate in periodos:
            linhas.append({"ID_SPRINT": id_sprint, "ISSUE_KEY": it["key"], "PROJETO": f["project"]["key"],
                           "TIPO_ITEM": tipo, "RESPONSAVEL": resp, "STATUS": status,
                           "EM_SPRINT_ATIVA": em_sprint, "EM_BACKLOG2": em_b2,
                           "VALIDO_DE": local(de), "VALIDO_ATE": local(ate)})
    return linhas


def reconstruir_fila_sprint(id_sprint, data_inicio, data_fim):
    """Calcula a fila real da sprint (só leitura no Jira) e grava em TB_SPRINT_FILA_ESTADO."""
    linhas = calcular_fila_sprint(id_sprint, data_inicio, data_fim)
    with conn.session as s:
        s.execute(text("DELETE FROM TB_SPRINT_FILA_ESTADO WHERE ID_SPRINT = :id"), {"id": id_sprint})
        if linhas:
            s.execute(text("""
                INSERT INTO TB_SPRINT_FILA_ESTADO
                (ID_SPRINT, ISSUE_KEY, PROJETO, TIPO_ITEM, RESPONSAVEL, STATUS, EM_SPRINT_ATIVA, EM_BACKLOG2, VALIDO_DE, VALIDO_ATE)
                VALUES (:ID_SPRINT, :ISSUE_KEY, :PROJETO, :TIPO_ITEM, :RESPONSAVEL, :STATUS, :EM_SPRINT_ATIVA, :EM_BACKLOG2, :VALIDO_DE, :VALIDO_ATE)
            """), linhas)
        s.commit()
    return True, f"Fila reconstruída: {len({l['ISSUE_KEY'] for l in linhas})} itens, {len(linhas)} períodos."


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
            "CLIENTE": item["Cliente"],
            "STATUS": item.get("Status", "Desconhecido"),
            "SISTEMA": item["Sistema"],
            "DATA_LIMITE": item.get("data_limite"),
            "DATA_CRIACAO": item.get("data_criacao"),
            "DEV_INICIAL": item.get("Dev_Inicial")  # None -> fica NULL/branco se o campo não vier preenchido no Jira
        })
    
    try:
        query = text("""
            INSERT INTO TB_SPRINT_DETAILS 
            (ISSUE_KEY, PROJETO, RESPONSAVEL, TIPO_ITEM, CATEGORIA, PONTOS, DATA_CONCLUSAO, ID_SPRINT, RESUMO, CLIENTE, STATUS, SISTEMA, DATA_LIMITE, DATA_CRIACAO, DEV_INICIAL)
            VALUES 
            (:ISSUE_KEY, :PROJETO, :RESPONSAVEL, :TIPO_ITEM, :CATEGORIA, :PONTOS, :DATA_CONCLUSAO, :ID_SPRINT, :RESUMO, :CLIENTE, :STATUS, :SISTEMA, :DATA_LIMITE, :DATA_CRIACAO, :DEV_INICIAL)
            ON DUPLICATE KEY UPDATE 
            RESPONSAVEL = VALUES(RESPONSAVEL), TIPO_ITEM = VALUES(TIPO_ITEM), CATEGORIA = VALUES(CATEGORIA), 
            PONTOS = VALUES(PONTOS), DATA_CONCLUSAO = VALUES(DATA_CONCLUSAO), CLIENTE = VALUES(CLIENTE), RESUMO = VALUES(RESUMO), STATUS = VALUES(STATUS), SISTEMA = VALUES(SISTEMA), DATA_LIMITE = VALUES(DATA_LIMITE), DATA_CRIACAO = VALUES(DATA_CRIACAO), DEV_INICIAL = VALUES(DEV_INICIAL)
        """)
        with conn.session as s:
            s.execute(query, payload)
            s.commit()
    except Exception as e:
        print(f"Erro na sincronização de detalhes: {e}")

def obter_ou_criar_sprint(inicio, fim, descricao):
    dt_inicio = inicio.date() if isinstance(inicio, datetime) else inicio
    dt_fim = fim.date() if isinstance(fim, datetime) else fim
    
    if (dt_fim - dt_inicio).days != 13:
        return None, f"A sprint deve ter exatos 14 dias. A sua tem {(dt_fim - dt_inicio).days + 1} dias."

    inicio_str = dt_inicio.strftime("%Y-%m-%d")
    fim_str = dt_fim.strftime("%Y-%m-%d")
    nome_sprint = f"Sprint {dt_inicio.strftime('%d/%m')} a {dt_fim.strftime('%d/%m')}"

    df_sprints = conn.query("SELECT ID_SPRINT, DATA_INICIO, DATA_FIM, DESCRICAO FROM TB_SPRINT ORDER BY DATA_FIM DESC", ttl=0)
    sprints_existentes = df_sprints.to_dict('records')

    for sp in sprints_existentes:
        sp_inicio_str = sp['DATA_INICIO'].strftime("%Y-%m-%d") if not isinstance(sp['DATA_INICIO'], str) else sp['DATA_INICIO']
        sp_fim_str = sp['DATA_FIM'].strftime("%Y-%m-%d") if not isinstance(sp['DATA_FIM'], str) else sp['DATA_FIM']

        if sp_inicio_str == inicio_str and sp_fim_str == fim_str:
            return sp['ID_SPRINT'], "Sprint existente encontrada e vinculada."

    for sp in sprints_existentes:
        sp_inicio = sp['DATA_INICIO'] if not isinstance(sp['DATA_INICIO'], str) else datetime.strptime(sp['DATA_INICIO'], "%Y-%m-%d").date()
        sp_fim = sp['DATA_FIM'] if not isinstance(sp['DATA_FIM'], str) else datetime.strptime(sp['DATA_FIM'], "%Y-%m-%d").date()
        
        if dt_inicio <= sp_fim and dt_fim >= sp_inicio:
            return None, f"Sobreposição detectada com a {sp['NOME_SPRINT']}."

    nova_sprint = {"nome": nome_sprint, "inicio": inicio_str, "fim": fim_str, "descricao": descricao}
    try:
        with conn.session as s:
            result = s.execute(text("""
                INSERT INTO TB_SPRINT (NOME_SPRINT, DATA_INICIO, DATA_FIM, DESCRICAO) 
                VALUES (:nome, :inicio, :fim, :descricao)
            """), nova_sprint)
            s.commit()
            novo_id = result.lastrowid 
        return novo_id, "Nova Sprint cadastrada com sucesso no banco!"
    except Exception as e:
        return None, f"Erro ao criar Sprint no banco: {e}"


def executar_extracao(data_inicio_input, data_fim_input, descricao_input, fase_snapshot="AVULSO", desc_snapshot=""):
    st.session_state['logs_jira'] = []
    
    global periodos
    
    inicio, fim = periodo_sprint(data_inicio_input, data_fim_input)
    periodos = [(inicio, fim)]
    
    conn.reset()

    id_sprint, msg_validacao = obter_ou_criar_sprint(inicio, fim, descricao_input)
    
    if not id_sprint:
        return False, msg_validacao 
        
    try:
        conn.reset()
        with conn.session as s:
            s.execute(text("DELETE FROM TB_SPRINT_DETAILS WHERE ID_SPRINT = :id"), {"id": id_sprint})
            s.commit()

        dados_star_pontos = obter_dados_projeto("STAR")
        sincronizar_com_banco(dados_star_pontos, "STAR", id_sprint)
        salvar_conclusoes_ciclo_total("STAR", id_sprint)

        dados_elfa_pontos = obter_dados_projeto("ELFA")
        sincronizar_com_banco(dados_elfa_pontos, "ELFA", id_sprint)
        salvar_conclusoes_ciclo_total("ELFA", id_sprint)


        hoje = datetime.now(timezone.utc)

        # Ciclo total: contagem dos itens entre 3.3 e 6.0 (só com sprint em andamento, como o backlog).
        contagem_pos = None
        if fim >= hoje:
            extrair_e_salvar_backlog("STAR", id_sprint)
            extrair_e_salvar_backlog("ELFA", id_sprint)
            status_backlog = "Pontos (STAR e ELFA) e Snapshot do Backlog (STAR e ELFA) atualizados."
            pos_star = contar_pos_desenvolvimento("STAR")
            pos_elfa = contar_pos_desenvolvimento("ELFA")
            if pos_star is not None and pos_elfa is not None:
                contagem_pos = {k: pos_star[k] + pos_elfa[k] for k in pos_star}
        else:
            status_backlog = "Apenas pontos (STAR e ELFA) atualizados (Snapshot do Backlog preservado, pois a sprint já foi encerrada)."
            print(f"🔒 Sprint encerrada em {fim.strftime('%d/%m/%Y')}. Snapshot do backlog preservado.")
        tipos_sust = ['erro', 'atendimento', 'retorno negativo (rn)']
        
        
        with conn.session as s:
            query_global = text("SELECT TIPO_ITEM FROM TB_SPRINT_BACKLOG WHERE ID_SPRINT = :id")
            itens_global = s.execute(query_global, {"id": id_sprint}).fetchall()
            todos_global = [item[0].lower() if item[0] else "" for item in itens_global]
            
            tot_sust_global = sum(1 for item in todos_global if item in tipos_sust)
            tot_desv_global = len(todos_global) - tot_sust_global
            tot_geral_global = len(todos_global)
            
            query_nativa = text("SELECT TIPO_ITEM FROM TB_SPRINT_BACKLOG WHERE ID_SPRINT = :id AND SPRINT_NATIVA = 'SIM'")
            itens_nativa = s.execute(query_nativa, {"id": id_sprint}).fetchall()
            todos_nativa = [item[0].lower() if item[0] else "" for item in itens_nativa]
            
            tot_sust_nativa = sum(1 for item in todos_nativa if item in tipos_sust)
            tot_desv_nativa = len(todos_nativa) - tot_sust_nativa
            tot_geral_nativa = len(todos_nativa)
            
            query_snap = text("""
                INSERT INTO TB_SPRINT_SNAPSHOT 
                (ID_SPRINT, FASE, DESCRICAO_CUSTOMIZADA, 
                 QTD_TOTAL, QTD_SUST, QTD_DESV,
                 QTD_TOTAL_NATIVA, QTD_SUST_NATIVA, QTD_DESV_NATIVA)
                VALUES 
                (:id, :fase, :descricao_snap, 
                 :total, :sust, :desv,
                 :tot_nat, :sust_nat, :desv_nat)
            """)
            resultado_snap = s.execute(query_snap, {
                "id": id_sprint, "fase": fase_snapshot, "descricao_snap": desc_snapshot,
                "total": tot_geral_global, "sust": tot_sust_global, "desv": tot_desv_global,
                "tot_nat": tot_geral_nativa, "sust_nat": tot_sust_nativa, "desv_nat": tot_desv_nativa
            })
            id_snapshot_novo = resultado_snap.lastrowid

            s.execute(text("UPDATE TB_SPRINT SET ULTIMA_ATUALIZACAO = NOW() WHERE ID_SPRINT=:id"), {"id": id_sprint})
            s.commit()

        # Colunas *_POS num passo separado: uma falha aqui não impede o snapshot.
        if contagem_pos is not None and id_snapshot_novo:
            try:
                with conn.session as s:
                    s.execute(text("""
                        UPDATE TB_SPRINT_SNAPSHOT SET
                            QTD_TOTAL_POS = :total, QTD_SUST_POS = :sust, QTD_DESV_POS = :desv,
                            QTD_TOTAL_POS_NATIVA = :total_nat, QTD_SUST_POS_NATIVA = :sust_nat, QTD_DESV_POS_NATIVA = :desv_nat
                        WHERE ID_SNAPSHOT = :id_snap
                    """), {**contagem_pos, "id_snap": id_snapshot_novo})
                    s.commit()
            except Exception as e:
                msg = f"⚠️ Ciclo total: falha ao gravar contagem pós-desenvolvimento no snapshot: {e}"
                print(msg)
                st.session_state.setdefault('logs_jira', []).append(msg)

        # Fila real: protegida, se falhar a sincronização segue normal.
        try:
            ok_fila, msg_fila = reconstruir_fila_sprint(id_sprint, data_inicio_input, data_fim_input)
            print(msg_fila)
        except Exception as e:
            msg = f"⚠️ Fila real: falha ao reconstruir pelo histórico do Jira: {e}"
            print(msg)
            st.session_state.setdefault('logs_jira', []).append(msg)

        return True, f"{msg_validacao} {status_backlog}"
        
    except Exception as e:
        return False, f"Erro na extração combinada: {e}"