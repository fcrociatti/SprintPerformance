"""Aba "Projeto ELFA": lida direto do Jira, só leitura, no mesmo modelo de carregar_carga_devs_jira.

Não usa banco nem sincronização: cada consulta vai ao Jira e fica 5 minutos em cache.
"""
from datetime import datetime, timedelta, timezone

import altair as alt
import pandas as pd
import requests
import streamlit as st
from requests.auth import HTTPBasicAuth

BOARD_ELFA = 18
SPRINT_BACKLOG = 1289
CAMPO_SPRINT = "customfield_10020"
SPRINTS_NAO_DESENVOLVIMENTO = {SPRINT_BACKLOG, 1218}  # Sprint Backlog e Backlog 2 do STAR

STATUS_HOMOLOGACAO = "5.3 Pendência de Homolog"
STATUS_PRODUCAO = "6.0 Concluído"
STATUS_DISPENSADO = "7.0 Dispensado"
STATUS_COM_ELFA = "1.5 TRIAGEM EM REVISÃO (ELFA)"
STATUS_PENDENCIA_USUARIO = "5.0 Pendência do Usuário"
TIPO_RETORNO = "Retorno Negativo (RN)"
BASE_JQL = "project = ELFA AND issuetype not in subTaskIssueTypes()"
QTD_SPRINTS_EVOLUCAO = 4
CLIENTE_ELFA_NA_STAR = "Grupo Elfa (TLS)"  # campo Cliente (customfield_10133) dos itens no projeto STAR

# Entregas informadas pela gestão, valem no lugar da data do Jira: {sprint: {status: [itens]}}.
# ELFA-970 (inventário cíclico) passou para 5.3 só em 02/11, feriado, mas conta na Sprint Elfa 65.
ENTREGAS_MANUAIS = {1290: {STATUS_HOMOLOGACAO: ["ELFA-970"]}}

COR_HOMOLOGACAO, COR_PRODUCAO, COR_RETORNO = "#4CA6FF", "#2ECC71", "#E74C3C"


def _get_jira(caminho, params=None):
    auth = HTTPBasicAuth(st.secrets["JIRA_USER"], st.secrets["JIRA_TOKEN"])
    resp = requests.get(f'{st.secrets["JIRA_URL"]}{caminho}', auth=auth, headers={"Accept": "application/json"},
                        params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def _buscar_issues(jql, campos, expand=None):
    issues, token = [], ""
    while True:
        params = {"jql": jql, "fields": campos, "maxResults": 100}
        if expand:
            params["expand"] = expand
        if token:
            params["nextPageToken"] = token
        js = _get_jira("/rest/api/3/search/jql", params)
        issues += js.get("issues", [])
        token = js.get("nextPageToken")
        if js.get("isLast", True) or not token:
            return issues


def _linha(issue):
    campos = issue["fields"]
    return {
        "issue_key": issue["key"],
        "resumo": campos.get("summary", ""),
        "status": (campos.get("status") or {}).get("name", ""),
        "tipo_item": (campos.get("issuetype") or {}).get("name", ""),
        "responsavel": (campos.get("assignee") or {}).get("displayName", "Sem responsável"),
    }


def _data_brasilia(valor):
    return (pd.Timestamp(valor) - pd.Timedelta(hours=3)).date()


def _hoje():
    return datetime.now(timezone(timedelta(hours=-3))).date()


@st.cache_data(ttl=300, show_spinner=False)
def carregar_sprints_elfa():
    """Sprints de desenvolvimento do board, da mais nova para a mais antiga. O período de cada uma vai do
    início até a véspera da seguinte, porque no Jira as sprints fecham com atraso e se sobrepõem."""
    sprints, inicio = [], 0
    while True:
        js = _get_jira(f"/rest/agile/1.0/board/{BOARD_ELFA}/sprint", {"startAt": inicio, "maxResults": 50})
        sprints += [s for s in js.get("values", []) if s["id"] != SPRINT_BACKLOG and s.get("startDate")]
        inicio += len(js.get("values", []))
        if js.get("isLast", True) or not js.get("values"):
            break
    sprints.sort(key=lambda s: s["startDate"])
    lista = []
    for i, s in enumerate(sprints):
        ini = _data_brasilia(s["startDate"])
        fim = _data_brasilia(sprints[i + 1]["startDate"]) - timedelta(days=1) if i + 1 < len(sprints) else _hoje()
        lista.append({"id": s["id"], "nome": s["name"], "estado": s["state"], "ini": ini, "fim": fim,
                      "fim_jira": _data_brasilia(s["endDate"]) if s.get("endDate") else fim})
    return lista[::-1]


def _mudancas_de_status_e_sprint(issue):
    """Histórico de status e de sprint do item, em ordem de data (completa quando o Jira corta o changelog)."""
    historico = issue.get("changelog") or {}
    linhas = historico.get("histories", [])
    if historico.get("total", 0) > len(linhas):
        linhas, inicio = [], 0
        while True:
            js = _get_jira(f"/rest/api/3/issue/{issue['key']}/changelog", {"startAt": inicio, "maxResults": 100})
            linhas += js.get("values", [])
            inicio += len(js.get("values", []))
            if js.get("isLast", True) or not js.get("values"):
                break
    return [(h["created"], x) for h in sorted(linhas, key=lambda h: h["created"]) for x in h["items"]]


def _status_no_fim(mudancas, status_atual, fim):
    """Status do item no último dia do período (sprint já encerrada não usa o status de hoje)."""
    status = [(quando, x) for quando, x in mudancas if x["field"] == "status"]
    ate_o_fim = [x["toString"] for quando, x in status if _data_brasilia(quando) <= fim]
    if ate_o_fim:
        return ate_o_fim[-1]
    return status[0][1]["fromString"] if status else status_atual


def _veio_de_sprint_anterior(mudancas, id_sprint):
    """O campo Sprint do item perde sprints antigas: o histórico de mudança é que guarda por onde ele passou."""
    ids = set()
    for _, x in mudancas:
        if x["field"] == "Sprint":
            ids |= {int(v) for v in f"{x.get('from') or ''},{x.get('to') or ''}".split(",") if v.strip().isdigit()}
    return any(i < id_sprint and i not in SPRINTS_NAO_DESENVOLVIMENTO for i in ids)


def _sprints_no_fim(mudancas, sprints_atuais, fim):
    """Sprints do item no último dia do período, pelo histórico do campo Sprint."""
    sprint = [(quando, x) for quando, x in mudancas if x["field"] == "Sprint"]
    ate_o_fim = [x.get("to") for quando, x in sprint if _data_brasilia(quando) <= fim]
    if not sprint:
        return sprints_atuais
    valor = ate_o_fim[-1] if ate_o_fim else sprint[0][1].get("from")
    return {int(v) for v in (valor or "").split(",") if v.strip().isdigit()}


@st.cache_data(ttl=300, show_spinner=False)
def carregar_itens_sprint(id_sprint, ini, fim, encerrada):
    """Itens da sprint que ainda estavam com a DDS: fora de homologação, produção e dispensado.

    Ao fechar a sprint, o Jira leva os pendentes para a seguinte e tira esta do campo Sprint: numa sprint
    encerrada, os itens vêm do histórico (todo item alterado desde o início dela é conferido)."""
    filtro = f'(sprint = {id_sprint} OR updated >= "{ini}")' if encerrada else f"sprint = {id_sprint}"
    linhas = []
    for issue in _buscar_issues(f"{BASE_JQL} AND {filtro}", f"summary,status,issuetype,assignee,{CAMPO_SPRINT}", "changelog"):
        mudancas = _mudancas_de_status_e_sprint(issue)
        atuais = {s["id"] for s in (issue["fields"].get(CAMPO_SPRINT) or [])}
        if id_sprint not in _sprints_no_fim(mudancas, atuais, fim):
            continue
        linha = _linha(issue)
        linha["status"] = _status_no_fim(mudancas, linha["status"], fim)
        linha["sprint_anterior"] = _veio_de_sprint_anterior(mudancas, id_sprint)
        linhas.append(linha)
    df = pd.DataFrame(linhas, columns=["issue_key", "resumo", "status", "tipo_item", "responsavel", "sprint_anterior"])
    return df[~df["status"].isin([STATUS_HOMOLOGACAO, STATUS_PRODUCAO, STATUS_DISPENSADO])]


@st.cache_data(ttl=300, show_spinner=False)
def carregar_backlog_elfa():
    issues = _buscar_issues(f"{BASE_JQL} AND sprint = {SPRINT_BACKLOG}", "summary,status,issuetype,assignee")
    return pd.DataFrame([_linha(i) for i in issues], columns=["issue_key", "resumo", "status", "tipo_item", "responsavel"])


@st.cache_data(ttl=300, show_spinner=False)
def carregar_entregas(status, ini, fim):
    """Itens que entraram em 'status' no período (registro da transição no Jira)."""
    jql = f'{BASE_JQL} AND status CHANGED TO "{status}" DURING ("{ini} 00:00", "{fim} 23:59")'
    issues = _buscar_issues(jql, "summary,status,issuetype,assignee")
    return pd.DataFrame([_linha(i) for i in issues], columns=["issue_key", "resumo", "status", "tipo_item", "responsavel"])


@st.cache_data(ttl=300, show_spinner=False)
def carregar_por_chave(chaves):
    issues = _buscar_issues(f"key in ({', '.join(chaves)})", "summary,status,issuetype,assignee")
    return pd.DataFrame([_linha(i) for i in issues], columns=["issue_key", "resumo", "status", "tipo_item", "responsavel"])


def _entregas_da_sprint(sprint, status):
    """Entradas no status registradas no Jira, com os acertos de ENTREGAS_MANUAIS (cada item conta numa sprint só)."""
    df = carregar_entregas(status, sprint["ini"], sprint["fim"])
    de_outras = {k for id_sprint, por_status in ENTREGAS_MANUAIS.items() if id_sprint != sprint["id"]
                 for k in por_status.get(status, [])}
    df = df[~df["issue_key"].isin(de_outras)]
    faltando = [k for k in ENTREGAS_MANUAIS.get(sprint["id"], {}).get(status, []) if k not in set(df["issue_key"])]
    return pd.concat([df, carregar_por_chave(tuple(faltando))], ignore_index=True) if faltando else df


@st.cache_data(ttl=300, show_spinner=False)
def carregar_erros_abertos():
    """Erros do cliente Grupo Elfa no projeto STAR (única consulta que olha a STAR), sem os que aguardam
    homologação ou o usuário."""
    jql = (f'project = STAR AND issuetype = Erro AND cf[10133] = "{CLIENTE_ELFA_NA_STAR}" AND statusCategory != Done '
           f'AND status not in ("{STATUS_HOMOLOGACAO}", "{STATUS_PENDENCIA_USUARIO}")')
    issues = _buscar_issues(jql, "summary,status,issuetype,assignee")
    return pd.DataFrame([_linha(i) for i in issues], columns=["issue_key", "resumo", "status", "tipo_item", "responsavel"])


@st.cache_data(ttl=300, show_spinner=False)
def contar_retornos(ini, fim):
    jql = f'project = ELFA AND issuetype = "{TIPO_RETORNO}" AND created >= "{ini} 00:00" AND created <= "{fim} 23:59"'
    return len(_buscar_issues(jql, "issuetype"))


def _tabela_itens(df, colunas):
    if df.empty:
        st.caption("Nenhum item.")
        return
    tabela = df.copy()
    tabela["link"] = st.secrets["JIRA_URL"] + "/browse/" + tabela["issue_key"]
    st.dataframe(tabela[["issue_key", *colunas, "link"]], hide_index=True, use_container_width=True,
                 column_config={"issue_key": "Chave", "resumo": "Resumo", "status": "Status", "tipo_item": "Tipo",
                                "responsavel": "Responsável", "sprint_anterior": "Sprint anterior",
                                "link": st.column_config.LinkColumn("Jira")})


def _barras(df, categoria, valor, cor):
    if df.empty or df[valor].sum() == 0:
        st.caption("Nenhum item.")
        return
    maximo = int(df[valor].max())
    barras = alt.Chart(df).mark_bar(cornerRadiusEnd=3).encode(
        x=alt.X(f"{valor}:Q", title="Qtd de Itens", scale=alt.Scale(domain=[0, maximo * 1.15]),
                axis=alt.Axis(grid=False, format="d", values=list(range(0, maximo + 1, max(1, maximo // 8))))),
        y=alt.Y(f"{categoria}:N", sort=list(df[categoria]), title="", axis=alt.Axis(labelLimit=260, labelOverlap=False)),
        color=cor, tooltip=[categoria, valor])
    texto = barras.mark_text(align="left", baseline="middle", dx=5, color="white").encode(text=f"{valor}:Q")
    st.altair_chart((barras + texto).properties(height=alt.Step(34)), use_container_width=True, theme="streamlit")


def _grafico_evolucao(anteriores):
    linhas = []
    for s in anteriores[::-1]:
        linhas += [
            {"Sprint": s["nome"].replace("Sprint ", ""), "Indicador": "Para homologação",
             "Itens": len(_entregas_da_sprint(s, STATUS_HOMOLOGACAO))},
            {"Sprint": s["nome"].replace("Sprint ", ""), "Indicador": "Para produção",
             "Itens": len(_entregas_da_sprint(s, STATUS_PRODUCAO))},
            {"Sprint": s["nome"].replace("Sprint ", ""), "Indicador": "Retornos (RN) abertos",
             "Itens": contar_retornos(s["ini"], s["fim"])},
        ]
    df = pd.DataFrame(linhas)
    cores = {"Para homologação": COR_HOMOLOGACAO, "Para produção": COR_PRODUCAO, "Retornos (RN) abertos": COR_RETORNO}
    barras = alt.Chart(df).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
        x=alt.X("Sprint:N", sort=[s["nome"].replace("Sprint ", "") for s in anteriores[::-1]], title=None,
                axis=alt.Axis(labelAngle=0)),
        xOffset=alt.XOffset("Indicador:N", sort=list(cores)),
        y=alt.Y("Itens:Q", title="Itens", axis=alt.Axis(grid=False, format="d", tickMinStep=1)),
        color=alt.Color("Indicador:N", sort=list(cores), legend=alt.Legend(orient="bottom", title=None),
                        scale=alt.Scale(domain=list(cores), range=list(cores.values()))),
        tooltip=["Sprint", "Indicador", "Itens"])
    texto = barras.mark_text(dy=-6, color="white").encode(text="Itens:Q")
    st.altair_chart((barras + texto).properties(height=320), use_container_width=True, theme="streamlit")


def _conteudo():
    sprints = carregar_sprints_elfa()
    if not sprints:
        st.warning("Nenhuma sprint encontrada no board do ELFA.")
        return

    rotulos = [f"{s['nome']} ({s['ini']:%d/%m} a {s['fim_jira']:%d/%m})" for s in sprints]
    c_tit, c_sel = st.columns([3, 2])
    indice = c_sel.selectbox("Sprint ELFA", range(len(rotulos)), format_func=lambda i: rotulos[i], key="elfa_sprint")
    sprint = sprints[indice]
    c_tit.subheader(f"Visão Geral da {sprint['nome']}")

    itens = carregar_itens_sprint(sprint["id"], sprint["ini"], sprint["fim"], sprint["estado"] != "active")
    backlog = carregar_backlog_elfa()
    homologacao = _entregas_da_sprint(sprint, STATUS_HOMOLOGACAO)
    producao = _entregas_da_sprint(sprint, STATUS_PRODUCAO)
    erros = carregar_erros_abertos()

    with st.container(border=True):
        st.markdown("#### Marcadores Principais")
        a, b, c, d = st.columns(4)
        a.metric("Itens na sprint", len(itens))
        b.metric("Entregues p/ homologação", len(homologacao))
        c.metric("Entregues p/ produção", len(producao))
        d.metric("Na Sprint Backlog", len(backlog))

    st.divider()
    col_dev, col_backlog = st.columns(2)

    with col_dev:
        with st.container(border=True):
            st.markdown("#### Sprint de Desenvolvimento")
            st.metric("Itens na sprint", len(itens))
            st.divider()
            retornos = int((itens["tipo_item"] == TIPO_RETORNO).sum())
            c1, c2, c3 = st.columns(3)
            c1.metric("Itens novos", len(itens) - retornos)
            c2.metric("Retornos (RN)", retornos)
            c3.metric("Sprint anterior", int(itens["sprint_anterior"].sum()))
            st.markdown("**Itens da sprint por status**")
            por_status = itens.groupby("status").size().reset_index(name="Itens").sort_values("status")
            _barras(por_status, "status", "Itens", alt.value(COR_HOMOLOGACAO))
            with st.expander(" Detalhes de itens da sprint"):
                _tabela_itens(itens.sort_values("status"), ["resumo", "status", "tipo_item", "responsavel", "sprint_anterior"])

    with col_backlog:
        with st.container(border=True):
            st.markdown("#### Sprint Backlog (Lapidação)")
            st.metric("Itens na Sprint Backlog", len(backlog))
            st.divider()
            com_elfa = int((backlog["status"] == STATUS_COM_ELFA).sum())
            c1, c2 = st.columns(2)
            c1.metric("Com a DDS", len(backlog) - com_elfa)
            c2.metric("Com a ELFA", com_elfa)
            with st.expander(" Detalhes de itens da Sprint Backlog"):
                _tabela_itens(backlog.sort_values("status"), ["resumo", "status", "tipo_item", "responsavel"])

    st.divider()

    with st.container(border=True):
        st.markdown("#### Entregas da Sprint")
        a, b = st.columns(2)
        a.metric("Entregues para homologação", len(homologacao))
        b.metric("Entregues para produção", len(producao))
        entregas = pd.DataFrame({"Entrega": ["Para homologação", "Para produção"],
                                 "Itens": [len(homologacao), len(producao)]})
        cor_entrega = alt.Color("Entrega:N", legend=None, scale=alt.Scale(domain=["Para homologação", "Para produção"],
                                                                         range=[COR_HOMOLOGACAO, COR_PRODUCAO]))
        _barras(entregas, "Entrega", "Itens", cor_entrega)
        with st.expander(" Detalhes das entregas"):
            st.markdown("**Entregues para homologação**")
            _tabela_itens(homologacao, ["resumo", "status", "tipo_item", "responsavel"])
            st.markdown("**Entregues para produção**")
            _tabela_itens(producao, ["resumo", "status", "tipo_item", "responsavel"])

    st.divider()

    with st.container(border=True):
        st.markdown("#### Erros em Aberto")
        st.metric("Total de erros", len(erros))
        por_status = erros.groupby("status").size().reset_index(name="Itens").sort_values("status")
        _barras(por_status, "status", "Itens", alt.value(COR_RETORNO))
        with st.expander(" Itens de erro em aberto", expanded=True):
            _tabela_itens(erros.sort_values("status"), ["resumo", "status", "responsavel"])

    anteriores = sprints[indice + 1:indice + 1 + QTD_SPRINTS_EVOLUCAO]
    if anteriores:
        st.divider()
        with st.container(border=True):
            st.markdown("#### Evolução por Sprint")
            _grafico_evolucao(anteriores)


@st.fragment
def renderizar_aba_elfa():
    # Fragmento: trocar a sprint aqui não recarrega as outras abas. Erro de leitura do Jira fica só nesta aba.
    try:
        with st.spinner("Lendo o projeto ELFA no Jira..."):
            _conteudo()
    except requests.RequestException as e:
        st.warning(f"Não foi possível ler o Jira agora: {e}")
