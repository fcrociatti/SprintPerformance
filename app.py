import streamlit as st
import pandas as pd
import altair as alt
from datetime import timedelta, datetime
from somaCopia import executar_extracao
from somaCopia import limpar_snapshot_sprint 
import os
import re
import math

st.set_page_config(page_title="Sprint Performance - DDS", layout="wide")

conn = st.connection("banco_dds", type="sql")

col_titulo, col_logo = st.columns([5, 1])

with col_titulo:
    st.title("Sprint Performance - DDS")

with col_logo:
    
    caminho_logo = "assets/logo.png" 
    if os.path.exists(caminho_logo):
        st.write("") 
        st.image(caminho_logo, use_container_width=True)

status_alvo = [
    "3.3 Revisão de Código", "4.0 A TESTAR", "4.2 Mergear", "4.3 Pend. Versão",
    "4.4 A Testar (homologação)", "4.5 A testar (artefato)", "3.2 Reprovados",
    "5.3 Pendência de Homolog", "6.0 Concluído",
    "6.1 Pend. Gerar Artefatos", "6.2 Pend. Envio Homolog."
]
        


# ==========================================
# CARREGAMENTO DOS DADOS 
# ==========================================
def carregar_issues():
    conn.reset()
    query = """
        SELECT ID_SPRINT_DETAILS as id, ISSUE_KEY as issue_key, PROJETO as projeto, 
               RESPONSAVEL as responsavel, TIPO_ITEM as tipo_item, CATEGORIA as categoria, 
               PONTOS as pontos, DATA_CONCLUSAO as data_conclusao, ID_SPRINT as sprint_id, 
               CLIENTE as cliente, RESUMO as resumo, STATUS as status, SISTEMA as sistema,
               DATA_LIMITE as data_limite, DATA_CRIACAO as data_criacao, DEV_INICIAL as dev_inicial
        FROM TB_SPRINT_DETAILS
    """
    return conn.query(query)


def carregar_sprints():
    conn.reset()
    query = """
        SELECT ID_SPRINT as id, NOME_SPRINT as nome_sprint, DATA_INICIO as data_inicio, 
               DATA_FIM as data_fim, ITENS_INICIAIS as itens_iniciais, 
               TEMPO_REUNIAO_MIN as tempo_reuniao_min, DESCRICAO as descricao,
               ULTIMA_ATUALIZACAO as ultima_atualizacao
        FROM TB_SPRINT 
        ORDER BY DATA_INICIO DESC
    """
    return conn.query(query)


def carregar_snapshots():
    conn.reset()
    query = """
        SELECT ID_SNAPSHOT as id, ID_SPRINT as sprint_id, FASE as fase, 
               DESCRICAO_CUSTOMIZADA as descricao, QTD_TOTAL as qtd_total, 
               QTD_SUST as qtd_sust, QTD_DESV as qtd_desv, 
               QTD_TOTAL_NATIVA as qtd_total_nativa, QTD_SUST_NATIVA as qtd_sust_nativa, 
               QTD_DESV_NATIVA as qtd_desv_nativa, DATA_REGISTRO as data_registro,
               QTD_TOTAL_POS as qtd_total_pos, QTD_SUST_POS as qtd_sust_pos, QTD_DESV_POS as qtd_desv_pos,
               QTD_TOTAL_POS_NATIVA as qtd_total_pos_nativa, QTD_SUST_POS_NATIVA as qtd_sust_pos_nativa,
               QTD_DESV_POS_NATIVA as qtd_desv_pos_nativa
        FROM TB_SPRINT_SNAPSHOT
        ORDER BY DATA_REGISTRO ASC
    """
    return conn.query(query)

def carregar_conclusao_total():
    # Ciclo total do burndown: entrada em "6.0 Concluído". Se a tabela não existir, a visão só fica vazia.
    conn.reset()
    query = """
        SELECT ID_SPRINT as sprint_id, ISSUE_KEY as issue_key, PROJETO as projeto,
               TIPO_ITEM as tipo_item, DATA_CONCLUSAO_TOTAL as data_conclusao
        FROM TB_SPRINT_CONCLUSAO_TOTAL
    """
    try:
        return conn.query(query)
    except Exception:
        return pd.DataFrame(columns=['sprint_id', 'issue_key', 'projeto', 'tipo_item', 'data_conclusao'])

def carregar_backlog():
    conn.reset()
    query = """
        SELECT ID_SPRINT_BACKLOG as id, ID_SPRINT as sprint_id, ISSUE_KEY as issue_key, 
               PROJETO as projeto, RESPONSAVEL as responsavel, PAPEL as papel, 
               TIPO_ITEM as tipo_item, CLIENTE as cliente, RESUMO as resumo, 
               DATA_CRIACAO as data_criacao, STATUS as status, SISTEMA as sistema,
               DATA_LIMITE as data_limite, PONTOS as pontos, SPRINT_NATIVA as sprint_nativa,
               DEV_INICIAL as dev_inicial
        FROM TB_SPRINT_BACKLOG
    """
    return conn.query(query)

df_issues = carregar_issues()
df_sprints = carregar_sprints()
df_snapshots = carregar_snapshots()
df_backlog = carregar_backlog()
df_conclusao_total = carregar_conclusao_total()


def carregar_fila_estado():
    # Sem a tabela (ou sem dados da sprint), o burndown usa o cálculo anterior.
    conn.reset()
    query = """
        SELECT ID_SPRINT as sprint_id, ISSUE_KEY as issue_key, PROJETO as projeto, TIPO_ITEM as tipo_item,
               RESPONSAVEL as responsavel, STATUS as status, EM_SPRINT_ATIVA as em_sprint_ativa,
               EM_BACKLOG2 as em_backlog2, VALIDO_DE as valido_de, VALIDO_ATE as valido_ate
        FROM TB_SPRINT_FILA_ESTADO
    """
    try:
        df = conn.query(query)
        df['valido_de'] = pd.to_datetime(df['valido_de'])
        df['valido_ate'] = pd.to_datetime(df['valido_ate'])
        return df
    except Exception:
        return pd.DataFrame(columns=['sprint_id', 'issue_key', 'projeto', 'tipo_item', 'responsavel', 'status',
                                     'em_sprint_ativa', 'em_backlog2', 'valido_de', 'valido_ate'])


df_fila_estado = carregar_fila_estado()


if not df_sprints.empty:
    if 'descricao' not in df_sprints.columns:
        df_sprints['descricao'] = "Sem Descrição"
    else:
        df_sprints['descricao'] = df_sprints['descricao'].fillna("Sem Descrição")
    
    df_sprints['nome_exibicao'] = df_sprints['descricao'] + " - " + df_sprints['nome_sprint']


aba_dashboard,  aba_sincronizacao, aba_historico = st.tabs([" Visão da Sprint",  " Gerenciar Sprints", " Histórico & Desempenho"])

# ==========================================
# ABA 2: HISTÓRICO E DESEMPENHO 
# ==========================================
with aba_historico:
    st.subheader(" Avaliação de Desempenho (Múltiplas Sprints)")
    st.write("Selecione um período para analisar a evolução e a consistência das entregas da equipe.")

    if not df_sprints.empty and not df_issues.empty:
        lista_sprints_hist = df_sprints['nome_exibicao'].tolist()
        sprints_padrao = lista_sprints_hist[:5] if len(lista_sprints_hist) >= 5 else lista_sprints_hist
        
        col_f1, col_f2 = st.columns(2)
        sprints_selecionadas_hist = col_f1.multiselect("1. Selecione as Sprints:", lista_sprints_hist, default=sprints_padrao)
        
        if sprints_selecionadas_hist:
                ids_sprints_hist = df_sprints[df_sprints['nome_exibicao'].isin(sprints_selecionadas_hist)]['id'].tolist()
                
                df_issues_completo = df_issues.merge(df_sprints[['id', 'descricao', 'data_inicio']], left_on='sprint_id', right_on='id')
                df_hist = df_issues_completo[df_issues_completo['sprint_id'].isin(ids_sprints_hist)]
                
                devs_disp_hist = sorted(df_hist['responsavel'].unique())
                devs_com_numero = [dev for dev in devs_disp_hist if str(dev)[0].isdigit()]
                
                devs_selecionados_hist = col_f2.multiselect("2. Filtrar Desenvolvedores:", devs_disp_hist, default=devs_com_numero)
                
                
                if devs_selecionados_hist:
                    df_hist = df_hist[df_hist['responsavel'].isin(devs_selecionados_hist)]
                else:
                    df_hist = pd.DataFrame()
            
        if not df_hist.empty:
                total_periodo = df_hist['pontos'].sum()
                
                qtd_sprints = len(ids_sprints_hist)
                media_por_sprint = (total_periodo / qtd_sprints) if qtd_sprints > 0 else 0
                
                sust_periodo = df_hist[df_hist['categoria'] == 'Sustentação']['pontos'].sum()
                desv_periodo = df_hist[df_hist['categoria'] == 'Desenvolvimento']['pontos'].sum()
                
                c_hist1, c_hist2, c_hist3, c_hist4 = st.columns(4)
                
                c_hist1.metric("Total Acumulado", f"{total_periodo:.1f} pts")
                c_hist2.metric("Média por Sprint", f"{media_por_sprint:.1f} pts")
                c_hist3.metric("Sustentação (Soma)", f"{sust_periodo:.1f} pts")
                c_hist4.metric("Desenvolvimento (Soma)", f"{desv_periodo:.1f} pts")
                
                st.markdown("---")
                
                
               
                st.write("**Evolução de Entregas por Desenvolvedor**")
                    
                df_agrupado_hist = df_hist.groupby(['descricao', 'data_inicio', 'responsavel'])['pontos'].sum().reset_index()
                    
                ordem_cronologica = df_agrupado_hist.sort_values('data_inicio')['descricao'].unique().tolist()
                    
                if not df_agrupado_hist.empty:
                        barras_desempenho = alt.Chart(df_agrupado_hist).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
                            x=alt.X('responsavel:N', title='Desenvolvedor', axis=alt.Axis(labelAngle=0)),
                            
                            y=alt.Y('pontos:Q', title='Pontos Entregues'),
                            
                            xOffset=alt.XOffset('descricao:N', sort=ordem_cronologica),
                            
                            color=alt.Color('descricao:N', title='Sprint', sort=ordem_cronologica, scale=alt.Scale(scheme='tableau10')),
                            
                            tooltip=[
                                alt.Tooltip('responsavel:N', title='Desenvolvedor'),
                                alt.Tooltip('descricao:N', title='Sprint'),
                                alt.Tooltip('pontos:Q', title='Pontos Entregues')
                            ]
                        ).properties(height=350)
                        
                        st.altair_chart(barras_desempenho, use_container_width=True, theme="streamlit")
                else:
                        st.info("Nenhum dado encontrado para gerar o gráfico histórico.")
                
                st.write("**Ranking Acumulado no Período**")
                df_rank_hist = df_hist.groupby('responsavel')['pontos'].sum().reset_index()
                df_rank_hist = df_rank_hist[df_rank_hist['pontos'] > 0].sort_values(by='pontos', ascending=False)
                    
                grafico_barras_hist = alt.Chart(df_rank_hist).mark_bar().encode(
                        x=alt.X('pontos:Q', title='Total de Pontos', axis=alt.Axis(grid=False)),
                        y=alt.Y('responsavel:N', sort='-x', title=''),
                        color=alt.Color('responsavel:N', legend=None, scale=alt.Scale(scheme='category20')),
                        tooltip=['responsavel', 'pontos']
                    )
                textos_hist = grafico_barras_hist.mark_text(align='left', baseline='middle', dx=5, color='white', fontWeight='bold').encode(text='pontos:Q')
                st.altair_chart((grafico_barras_hist + textos_hist).properties(height=350), use_container_width=True, theme="streamlit")
                    
            
                
                st.divider()
                st.write("**Tabela Detalhada: Esforço por Sprint**")
                
                df_pivot = df_agrupado_hist.pivot_table(
                    index='responsavel', 
                    columns='descricao', 
                    values='pontos', 
                    aggfunc='sum', 
                    fill_value=0
                )
                
                colunas_existentes = [s for s in ordem_cronologica if s in df_pivot.columns]
                df_pivot = df_pivot[colunas_existentes]
                
                df_pivot['Total Acumulado'] = df_pivot.sum(axis=1)
                
                df_pivot = df_pivot.reset_index().rename(columns={'responsavel': 'Desenvolvedor'})
                
                df_exibicao = df_pivot.copy()
                
                linha_total = df_exibicao.sum(numeric_only=True)
                
                linha_total = linha_total.reindex(df_exibicao.columns, fill_value="")
                
                linha_total.iloc[0] = " TOTAL"

                df_linha_total = pd.DataFrame([linha_total])
                df_exibicao = pd.concat([df_linha_total, df_exibicao], ignore_index=True)

                st.dataframe(df_exibicao, use_container_width=True, hide_index=True)

        else:
                st.info("Nenhum dado encontrado para os filtros selecionados.")
    else:
        st.warning("É necessário cadastrar sprints e realizar buscas para visualizar o histórico.")


# ==========================================
# ABA 3: GERENCIAMENTO E SINCRONIZAÇÃO
# ==========================================
with aba_sincronizacao:
    st.subheader("Gerenciar Sprints no Jira")
    acao = st.radio("O que deseja fazer?", ["Cadastrar Nova Sprint", "Atualizar Sprint Existente"], horizontal=True)
    st.divider()

    
    if acao == "Cadastrar Nova Sprint":
        st.write("Defina a identificação e o intervalo da nova Sprint.")
        with st.form("form_sync_nova"):
            descricao_input = st.text_input("Identificação da Sprint", placeholder="Ex: Sprint 44")
            col1, col2 = st.columns(2)
            dt_inicio = col1.date_input("Data de Início da Sprint")
            dt_fim = col2.date_input("Data de Fim da Sprint", value=dt_inicio + timedelta(days=13))
            
            desc_snapshot_nova = st.text_input("Observação para o Log (Opcional):", placeholder="Ex: Carga inicial após a Planning")
            
            btn_sincronizar = st.form_submit_button("🚀 Iniciar Busca no Jira")
            
            if btn_sincronizar:
                if not descricao_input: st.warning("⚠️ Por favor, preencha a identificação da Sprint.")
                elif (dt_fim - dt_inicio).days != 13: st.error(f"❌ Erro: A sprint deve ter exatos 14 dias.")
                else:
                    sobreposicao = False
                    sprint_conflito = ""
                    if not df_sprints.empty:
                        for _, row in df_sprints.iterrows():
                            sp_ini = row['data_inicio'] if not isinstance(row['data_inicio'], str) else datetime.strptime(row['data_inicio'], "%Y-%m-%d").date()
                            sp_fim = row['data_fim'] if not isinstance(row['data_fim'], str) else datetime.strptime(row['data_fim'], "%Y-%m-%d").date()
                            if dt_inicio <= sp_fim and dt_fim >= sp_ini:
                                sobreposicao = True
                                sprint_conflito = row['descricao']
                                break
                    if sobreposicao: 
                        st.error(f"❌ Sobreposição detetada com: **{sprint_conflito}**.")
                    else:
                        hoje_date = datetime.now().date()
                        
                        if hoje_date < dt_inicio:
                            fase_calc_nova = "AVULSO"
                            desc_padrao = "Quantidade no cadastro sprint"
                        else:
                            fase_calc_nova = "INICIO"
                            desc_padrao = "Abertura oficial da Sprint (Planning)"

                        desc_final_nova = desc_snapshot_nova.strip()
                        if not desc_final_nova:
                            desc_final_nova = desc_padrao

                        with st.spinner('A conectar ao Jira...'):
                            sucesso, mensagem = executar_extracao(dt_inicio, dt_fim, descricao_input, fase_calc_nova, desc_final_nova) 
                            if sucesso:
                                st.success(f"✅ Dados importados!")
                                st.cache_data.clear()
                                st.rerun()
                            else: 
                                st.error(f"❌ Falha: {mensagem}")

    # ---------------------------------------------------------
    # PARTE 2: ATUALIZAR SPRINT 
    # ---------------------------------------------------------
    else:
        st.write("Busque os dados mais recentes de uma Sprint que já está no banco.")
        if not df_sprints.empty:
            sprint_para_atualizar = st.selectbox("Selecione a Sprint para Atualizar", df_sprints['nome_exibicao'].tolist())
            
            row_sprint = df_sprints[df_sprints['nome_exibicao'] == sprint_para_atualizar].iloc[0]
            
            with st.form("form_sync_atualiza"):
                dt_ini_str = row_sprint['data_inicio'].strftime("%Y-%m-%d") if not isinstance(row_sprint['data_inicio'], str) else row_sprint['data_inicio']
                dt_fim_str = row_sprint['data_fim'].strftime("%Y-%m-%d") if not isinstance(row_sprint['data_fim'], str) else row_sprint['data_fim']
                
                st.info(f"O sistema irá consultar o Jira novamente para o período de **{dt_ini_str}** até **{dt_fim_str}**.")
                
                st.markdown("---")
                
                is_checkpoint = st.checkbox(" Registrar contagem como Checkpoint")
                desc_snapshot = st.text_input("Observação para o Log (Opcional):", placeholder="Ex: Antes do refinamento Checkpoint")
                
                st.markdown("---")

                btn_atualizar = st.form_submit_button("🔄 Atualizar Dados")
                
                if btn_atualizar:
                    dt_inicio_upd = row_sprint['data_inicio'] if not isinstance(row_sprint['data_inicio'], str) else datetime.strptime(row_sprint['data_inicio'], "%Y-%m-%d").date()
                    dt_fim_upd = row_sprint['data_fim'] if not isinstance(row_sprint['data_fim'], str) else datetime.strptime(row_sprint['data_fim'], "%Y-%m-%d").date()
                    desc_upd = row_sprint['descricao']
                    id_sprint_upd = int(row_sprint['id'])
                    
                    tem_inicio = False
                    if 'df_snapshots' in locals() and not df_snapshots.empty:
                        snaps_sprint_upd = df_snapshots[df_snapshots['sprint_id'] == id_sprint_upd]
                        if not snaps_sprint_upd[snaps_sprint_upd['fase'] == 'INICIO'].empty:
                            tem_inicio = True

                    desc_final = desc_snapshot.strip()
                    hoje_date = datetime.now().date()
                    
                    if is_checkpoint: 
                        fase_calc = "CHECKPOINT"
                        if not desc_final: desc_final = "Registro oficial de Checkpoint"
                        
                    elif hoje_date >= dt_fim_upd: 
                        fase_calc = "FINAL"
                        if not desc_final: desc_final = "Encerramento oficial da Sprint"
                        
                    elif hoje_date >= dt_inicio_upd and not tem_inicio:
                        fase_calc = "INICIO"
                        if not desc_final: desc_final = "Abertura oficial da Sprint (Planning)"
                        
                    else: 
                        fase_calc = "AVULSO"
                        if not desc_final: desc_final = "Atualização de rotina"

                    with st.spinner(f"Atualizando dados da {sprint_para_atualizar}..."):
                        sucesso, mensagem = executar_extracao(dt_inicio_upd, dt_fim_upd, desc_upd, fase_calc, desc_final)
                        if sucesso:
                            st.success(f"✅ Dados atualizados!")
                            st.cache_data.clear()
                            st.rerun()
                        else: st.error(f"❌ Falha: {mensagem}")
        else: st.warning("Nenhuma Sprint cadastrada para atualizar.")

       
        # ---------------------------------------------------------
        # PARTE 3: DETALHES DE ATUALIZAÇÃO E BORRACHA
        # ---------------------------------------------------------
        if 'logs_jira' in st.session_state and len(st.session_state['logs_jira']) > 0:
            st.markdown("<br>", unsafe_allow_html=True)
            with st.expander(" Ver detalhamento de tarefas atualizadas no Jira", expanded=True):
                st.info("O sistema preencheu automaticamente a 'Data de Contagem de Pontos' para as seguintes entregas:")
                for log in st.session_state['logs_jira']:
                    st.write(log)

        st.divider()
        st.markdown("### ⚠️ Correção de Dados")
        with st.expander("Apagar Snapshots (Em caso de erro)"):
            st.warning("Use esta área para apagar os grandes marcos da Sprint (Início, Checkpoint ou Final) caso tenham sido registrados na data errada.")
            
            sprint_para_limpar = st.selectbox("Selecione a Sprint para corrigir:", df_sprints['nome_sprint'], key="limpar_sprint")
            id_sprint_limpar = int(df_sprints[df_sprints['nome_sprint'] == sprint_para_limpar].iloc[0]['id'])
            
            fase_para_limpar = st.selectbox(
                "Qual momento você deseja apagar?",
                ["INICIO", "CHECKPOINT", "FINAL", "TODAS"],
                help="Escolha qual 'foto' principal da sprint será apagada."
            )
            
            if st.button(f"🗑️ Apagar dados de {fase_para_limpar} da {sprint_para_limpar}", type="primary"):
                with st.spinner("Apagando registros no banco de dados..."):
                    sucesso, msg_limpeza = limpar_snapshot_sprint(id_sprint_limpar, fase_para_limpar)
                    if sucesso:
                        st.success(msg_limpeza)
                        st.cache_data.clear()
                        st.rerun() 
                    else:
                        st.error(msg_limpeza)

# ==========================================
# ABA 1: O DASHBOARD (Visão da Sprint)
# ==========================================
with aba_dashboard:
    if not df_sprints.empty:
        lista_sprints = df_sprints['nome_exibicao'].tolist()
        sprint_selecionada = st.sidebar.selectbox("Selecione a Sprint Atual", lista_sprints)
        
        id_sprint_selecionada = int(df_sprints[df_sprints['nome_exibicao'] == sprint_selecionada]['id'].iloc[0])

        projetos_issues = df_issues['projeto'].astype(str).str.strip().unique().tolist() if not df_issues.empty else []
        projetos_backlog = df_backlog['projeto'].astype(str).str.strip().unique().tolist() if not df_backlog.empty else []
        projetos_disponiveis = list(set(projetos_issues + projetos_backlog))
        
        if not projetos_disponiveis: projetos_disponiveis = ["STAR"]
        projeto = st.sidebar.multiselect("Projeto", projetos_disponiveis, default=projetos_disponiveis)
        
        if not projeto: 
            projeto = projetos_disponiveis

        if not df_issues.empty: 
            df_issues['sprint_id'] = pd.to_numeric(df_issues['sprint_id'], errors='coerce').fillna(0).astype(int)
            df_issues['projeto'] = df_issues['projeto'].astype(str).str.strip()
            df_filtrado = df_issues[(df_issues['projeto'].isin(projeto)) & (df_issues['sprint_id'] == id_sprint_selecionada)].copy()
        else: 
            df_filtrado = pd.DataFrame()
            
        if not df_backlog.empty: 
            df_backlog['sprint_id'] = pd.to_numeric(df_backlog['sprint_id'], errors='coerce').fillna(0).astype(int)
            df_backlog['projeto'] = df_backlog['projeto'].astype(str).str.strip()
            df_backlog_filtrado = df_backlog[(df_backlog['projeto'].isin(projeto)) & (df_backlog['sprint_id'] == id_sprint_selecionada)].copy()
        else: 
            df_backlog_filtrado = pd.DataFrame()

        if df_backlog_filtrado.empty:
            if df_backlog.empty:
                st.error("⚠️ DIAGNÓSTICO 1: O Python não encontrou NENHUM dado na tabela TB_SPRINT_BACKLOG. Limpe o Cache no topo direito ou atualize a sprint na aba 'Gerenciar Sprints'.")
            else:
                st.error(f"⚠️ DIAGNÓSTICO 2: O Banco tem {len(df_backlog)} itens pendentes, mas o Pandas não achou nenhum para a {sprint_selecionada}!")
                st.write(f"ID esperado na Tela: **{id_sprint_selecionada}**")
                st.write(f"IDs que realmente vieram no Banco: **{df_backlog['sprint_id'].unique()}**")

        st.subheader(f" Visão Geral da {sprint_selecionada.split(' - ')[0]} (Itens pendentes)")
        
        if not df_backlog_filtrado.empty:
            tipos_sustentacao = ["erro", "atendimento", "retorno negativo (rn)"]
            df_backlog_filtrado['categoria'] = df_backlog_filtrado['tipo_item'].apply(lambda x: "Sustentação" if str(x).lower() in tipos_sustentacao else "Desenvolvimento")

            df_ambas_sprints = df_backlog_filtrado.copy()

            def obter_qtd(nome_busca):
                if df_ambas_sprints.empty:
                    return 0
                return len(df_ambas_sprints[df_ambas_sprints['responsavel'].str.contains(nome_busca, case=False, na=False)])

            if 'sprint_nativa' in df_backlog_filtrado.columns:
                df_sprint_desenvolvimento = df_backlog_filtrado[df_backlog_filtrado['sprint_nativa'] == 'SIM'].copy()
            else:
                df_sprint_desenvolvimento = df_backlog_filtrado.copy()

            total_itens = len(df_sprint_desenvolvimento)
            itens_sust = len(df_sprint_desenvolvimento[df_sprint_desenvolvimento['categoria'] == 'Sustentação'])
            itens_desv = len(df_sprint_desenvolvimento[df_sprint_desenvolvimento['categoria'] == 'Desenvolvimento'])

            fernando = obter_qtd("Fernando")
            jonathan = obter_qtd("Jonathan Ferreira")
            thiago = obter_qtd("Thiago")
            paulo = obter_qtd("Paulo Domingues")  # só "Paulo" pegava também o dev "9. João Paulo"
            kaic = obter_qtd("Kaic de Castro")
            eder = obter_qtd("Eder")
            sergio = obter_qtd("Sergio")
            daniel = obter_qtd("Daniel")
            enzo = obter_qtd("Enzo")


            with st.container(border=True):
               
                c_tit, c_lbl = st.columns([3, 1])
                c_tit.markdown("#### Marcadores Principais")
                
                row_sprint_atual = df_sprints[df_sprints['id'] == id_sprint_selecionada].iloc[0]
                dt_ult = row_sprint_atual.get('ultima_atualizacao')
                
                if pd.notnull(dt_ult):
                    dt_obj = pd.to_datetime(dt_ult)
                    
                  
                    dt_obj = dt_obj - pd.Timedelta(hours=3)
                    
                    dt_str = dt_obj.strftime("%d/%m/%Y às %H:%M")
                    c_lbl.markdown(f"<div style='text-align: right; color: #888; font-size: 0.85em; margin-top: 10px; font-weight: 500;'>🔄 Última Sincronização: {dt_str}</div>", unsafe_allow_html=True)
                else:
                    c_lbl.markdown("<div style='text-align: right; color: #888; font-size: 0.85em; margin-top: 10px; font-weight: 500;'>🔄 Sincronização pendente</div>", unsafe_allow_html=True)
                
                colA, colB, colC = st.columns(3)
                colA.metric("Total de Itens", total_itens)
                colB.metric("Sustentação", itens_sust, f"{(itens_sust/total_itens*100):.1f}%" if total_itens > 0 else "0%")
                colC.metric("Desenvolvimento", itens_desv, f"{(itens_desv/total_itens*100):.1f}%" if total_itens > 0 else "0%")
            
            with st.expander(" Histórico de itens da Sprint (Planning vs Checkpoint vs Final)", expanded=False):
                ini_tot, ini_sus, ini_des = 0, 0, 0
                chk_tot, chk_sus, chk_des = 0, 0, 0
                fin_tot, fin_sus, fin_des = 0, 0, 0
                
                dt_ini_str, dt_chk_str, dt_fin_str = "", "", ""

                if 'df_snapshots' in locals() and not df_snapshots.empty:
                    snaps_sprint = df_snapshots[df_snapshots['sprint_id'] == id_sprint_selecionada]

                    df_ini = snaps_sprint[snaps_sprint['fase'] == 'INICIO']
                    if not df_ini.empty:
                        last_ini = df_ini.iloc[-1]
                        ini_tot, ini_sus, ini_des = last_ini['qtd_total'], last_ini['qtd_sust'], last_ini['qtd_desv']
                        dt_ini_str = f" - {(pd.to_datetime(last_ini['data_registro']) - pd.Timedelta(hours=3)).strftime('%d/%m %H:%M')}"

                    df_chk = snaps_sprint[snaps_sprint['fase'] == 'CHECKPOINT']
                    if not df_chk.empty:
                        last_chk = df_chk.iloc[-1]
                        chk_tot, chk_sus, chk_des = last_chk['qtd_total'], last_chk['qtd_sust'], last_chk['qtd_desv']
                        dt_chk_str = f" - {(pd.to_datetime(last_chk['data_registro']) - pd.Timedelta(hours=3)).strftime('%d/%m %H:%M')}"

                    df_fin = snaps_sprint[snaps_sprint['fase'] == 'FINAL']
                    if not df_fin.empty:
                        last_fin = df_fin.iloc[-1]
                        fin_tot, fin_sus, fin_des = last_fin['qtd_total'], last_fin['qtd_sust'], last_fin['qtd_desv']
                        dt_fin_str = f" - {(pd.to_datetime(last_fin['data_registro']) - pd.Timedelta(hours=3)).strftime('%d/%m %H:%M')}"

                
                col_sn1, col_sn2, col_sn3 = st.columns(3)
                
                col_sn1.markdown(f"**Planning (Dia de Início){dt_ini_str}**")
                col_sn1.metric("Total de Itens", f"{ini_tot:.0f}")
                col_sn1.write(f"🔧 Sust: {ini_sus:.0f} | 💻 Desv: {ini_des:.0f}")
                
                col_sn2.markdown(f"**Checkpoint{dt_chk_str}**")
                delta_chk = chk_tot - ini_tot
                col_sn2.metric("Total de Itens", f"{chk_tot:.0f}", delta=f"{delta_chk:.0f} itens", delta_color="inverse")
                col_sn2.write(f"🔧 Sust: {chk_sus:.0f} | 💻 Desv: {chk_des:.0f}")
                
                col_sn3.markdown(f"**Final (Encerramento){dt_fin_str}**")
                delta_fin = fin_tot - chk_tot
                col_sn3.metric("Total de Itens", f"{fin_tot:.0f}", delta=f"{delta_fin:.0f} itens", delta_color="inverse")
                col_sn3.write(f"🔧 Sust: {fin_sus:.0f} | 💻 Desv: {fin_des:.0f}")

                st.divider()

                with st.expander("Detalhes das atualizações", expanded=False):
                    if 'df_snapshots' in locals() and not df_snapshots.empty and not snaps_sprint.empty:
                        snaps_exibicao = snaps_sprint.copy()
                        snaps_exibicao['Data e Hora'] = (pd.to_datetime(snaps_exibicao['data_registro']) - pd.Timedelta(hours=3)).dt.strftime('%d/%m às %H:%M')
                        snaps_exibicao = snaps_exibicao[['Data e Hora', 'fase', 'descricao', 'qtd_total', 'qtd_sust', 'qtd_desv']]
                        snaps_exibicao.columns = ['Data e Hora', 'Fase', 'Observação', 'Total', 'Sust', 'Desv']
                        st.dataframe(snaps_exibicao, use_container_width=True, hide_index=True)
                    else:
                        st.info("Nenhum log registrado.")

        
            st.divider()

            
            # Matriz Comparativa desativada a pedido da gestão (mantida comentada).
            # with st.expander(" Matriz Comparativa)", expanded=False):
            
            #     todas_sprints_nomes = df_sprints['nome_sprint'].tolist()
                
            #     sprints_selecionadas = st.multiselect(
                    
            #         "Selecione as Sprints para comparar (Colunas):",
            #         options=todas_sprints_nomes,
            #         default=todas_sprints_nomes[-4]
            #     )
                
            #     if sprints_selecionadas:
            #         linhas_apontadores = [
            #             "📦 Total de Itens",
            #             "🔧 Sustentação",
            #             "💻 Desenvolvimento",
            #             " Total Foco Sergio+Eder",
            #             " Sergio",
            #             " Eder",
            #             " Daniel",

            #             " Total Análise",
            #             " Fernando",
            #             "Jonathan",
            #             "Thiago",
            #             "Paulo",
            #             "Kaic",
            #             "Enzo"
            
            #         ]
                    
            #         dados_matriz = {"Apontadores Principais": linhas_apontadores}
                    
            #         for nome_sp in sprints_selecionadas:
            #             id_sp = int(df_sprints[df_sprints['nome_sprint'] == nome_sp].iloc[0]['id'])
                        
            #             tot, sus, des = 0, 0, 0
            #             qtd_sergio, qtd_eder, qtd_daniel = 0, 0, 0
            #             tot_foco_se = 0

            #             qtd_fernando,qtd_jonathan, qtd_thiago, qtd_paulo, qtd_kaic, qtd_enzo = 0, 0, 0, 0,0,0
            #             tot_analise = 0
                        
            #             if 'df_snapshots' in locals() and not df_snapshots.empty:
            #                 snaps_sp = df_snapshots[df_snapshots['sprint_id'] == id_sp]
            #                 if not snaps_sp.empty:
            #                     last_snap = snaps_sp.iloc[-1]
            #                     tot, sus, des = last_snap['qtd_total'], last_snap['qtd_sust'], last_snap['qtd_desv']
                        
            #             if 'df_backlog' in locals() and not df_backlog.empty:
            #                 col_id = next((col for col in df_backlog.columns if col.lower() in ['id_sprint', 'sprint_id']), None)
                            
            #                 if col_id:
            #                     bk_sp = df_backlog[df_backlog[col_id] == id_sp]
                                
            #                     if not bk_sp.empty:
            #                         col_resp = next((col for col in bk_sp.columns if col.lower() in ['responsavel', 'assignee', 'responsável']), None)
                                    
            #                         if col_resp:
            #                             resps = bk_sp[col_resp].fillna('').str.lower()
                                        
            #                             qtd_sergio = resps.str.contains('sergio|sérgio').sum()
            #                             qtd_eder = resps.str.contains('eder').sum()
            #                             qtd_daniel = resps.str.contains('daniel').sum()
            #                             tot_foco_se = qtd_sergio + qtd_eder
                                        
            #                             qtd_fernando = resps.str.contains('fernando').sum()
            #                             qtd_jonathan = resps.str.contains('jonathan').sum()
            #                             qtd_thiago = resps.str.contains('thiago').sum()
            #                             qtd_paulo = resps.str.contains('paulo').sum()
            #                             qtd_kaic = resps.str.contains('kaic').sum()
            #                             qtd_enzo = resps.str.contains('enzo').sum()

                            
            #             dados_matriz[nome_sp] = [
            #                 tot, sus, des,
            #                 tot_foco_se, qtd_sergio, qtd_eder, qtd_daniel,
            #                 tot_analise, qtd_jonathan,  qtd_paulo,  qtd_thiago, qtd_enzo, qtd_kaic, qtd_fernando,
            #             ]
                    
            #         df_matriz = pd.DataFrame(dados_matriz)
                    
            #         for col in sprints_selecionadas:
            #             df_matriz[col] = df_matriz[col].astype(int)
                        
            #         st.dataframe(df_matriz, use_container_width=True, hide_index=True)
            #     else:
            #         st.info("⚠️ Selecione pelo menos uma Sprint no filtro acima para visualizar o comparativo.")            
                
            st.divider()
            col_eq1, col_eq2 = st.columns(2)

            with col_eq1:
                with st.container(border=True):
                    st.markdown("#### Gestão (Foco)")
                    st.metric("Total Foco Sergio+Eder", sergio + eder)
                    st.divider()

                    nomes_principais = ["Anderson", "Fernando", "Gustavo", "Nathan", "Daniel", "Eder", "Sergio"]
                    df_outros = df_backlog_filtrado[~df_backlog_filtrado['responsavel'].str.contains('|'.join(nomes_principais), case=False, na=False)]
                    todos_os_outros = len(df_outros)

                    c1, c2, c3,  = st.columns(3)
                    c1.metric("Sergio", sergio)
                    c2.metric("Eder", eder)
                    c3.metric("Daniel", daniel)

                    st.markdown("<br>", unsafe_allow_html=True)
                    df_gest_donut = pd.DataFrame({'categoria': ["Sergio", "Eder", "Daniel"],'quantidade': [sergio, eder, daniel]})
                    df_gest_donut = df_gest_donut[df_gest_donut['quantidade'] > 0]
                    
                    if not df_gest_donut.empty:
                        base_donut = alt.Chart(df_gest_donut).encode(theta=alt.Theta("quantidade:Q", stack=True))
                        donut = base_donut.mark_arc(innerRadius=60, outerRadius=100, stroke="#111").encode(
                            color=alt.Color("categoria:N", title="Responsável", scale=alt.Scale(range=["#4CA6FF", "#5DADE2", "#85C1E9", "#AAA"])),
                            order=alt.Order("quantidade:Q", sort="descending"),
                            tooltip=["categoria", "quantidade"]
                        )
                        text_donut = base_donut.mark_text(radius=120, color='white').encode(text="quantidade:Q", order=alt.Order("quantidade:Q", sort="descending"))
                        st.altair_chart((donut + text_donut).properties(height=250), use_container_width=True, theme="streamlit")

                        with st.expander(" Detalhes de itens da Gestão"):
                            gestor_selecionado = st.selectbox(
                                "Filtrar tarefas de:", 
                                [ "Todos da Equipe","Sergio", "Eder", "Daniel"],
                                label_visibility="collapsed" 
                            )
                            
                            if gestor_selecionado == "Todos da Equipe":
                                df_detalhe = df_backlog_filtrado[df_backlog_filtrado['responsavel'].str.contains("Sergio|Eder|Daniel", case=False, na=False)].copy()
                            else:
                                df_detalhe = df_backlog_filtrado[df_backlog_filtrado['responsavel'].str.contains(gestor_selecionado, case=False, na=False)].copy()
                            
                            if not df_detalhe.empty:
                                df_detalhe['link'] = "https://ddsinfo.atlassian.net/browse/" + df_detalhe['issue_key']
                                st.dataframe(
                                    df_detalhe[['issue_key','resumo',  'responsavel', 'status','tipo_item', 'link']], 
                                    hide_index=True,
                                    use_container_width=True,
                                    column_config={
                                        "issue_key": "Chave",
                                        "resumo" : "Resumo",
                                        "responsavel": "Gestor",
                                        "status": "Status",
                                        "tipo_item": "Tipo",
                                        "link": st.column_config.LinkColumn("Jira")
                                    }
                                )
                            else:
                                st.warning("Nenhuma tarefa pendente para este filtro.")
                    else: st.info("Sem dados de gestão.")

            with col_eq2:
                with st.container(border=True):
                    st.markdown("####  Equipe de Análise")
                    st.metric("Total Análise", fernando + jonathan + thiago + paulo + enzo)
                    st.divider()

                    c1, c2, c3, c4, c5 = st.columns(5)
                    c1.metric("Fernando", fernando)
                    c2.metric("Jonathan", jonathan)
                    c3.metric("Thiago", thiago)
                    c4.metric("Paulo", paulo)
                    c5.metric("Enzo", enzo)

                    st.markdown("<br>", unsafe_allow_html=True)
                    df_an_comp = pd.DataFrame({
                        'responsavel': ["Fernando", "Jonathan", "Thiago", "Paulo", "Enzo"],
                        'quantidade': [fernando, jonathan, thiago, paulo, enzo]
                    })
                    
                    if not df_an_comp.empty and df_an_comp['quantidade'].sum() > 0:
                        bar_comp = alt.Chart(df_an_comp).mark_bar(color="#37a0d2").encode(
                            x=alt.X('quantidade:Q', title='Qtd de Itens', axis=alt.Axis(grid=False)),
                            y=alt.Y('responsavel:N', sort='-x', title=''),
                            tooltip=['responsavel', 'quantidade']
                        )
                        label_comp = bar_comp.mark_text(align='left', baseline='middle', dx=5, color='white').encode(text='quantidade:Q')
                        st.altair_chart((bar_comp + label_comp).properties(height=200), use_container_width=True, theme="streamlit")
                        
                        with st.expander(" Detalhes de itens da Equipe de Análise"):
                            analista_selecionado = st.selectbox(
                                "Filtrar tarefas de:", 
                                ["Todos da Equipe", "Fernando", "Jonathan Ferreira", "Thiago Honorato", "Paulo Domingues", "Enzo"],
                                label_visibility="collapsed" 
                            )
                            
                            if analista_selecionado == "Todos da Equipe":
                                df_detalhe = df_backlog_filtrado[df_backlog_filtrado['responsavel'].str.contains("Fernando|Jonathan Ferreira|Thiago|Paulo Domingues|Enzo", case=False, na=False)].copy()
                            else:
                                df_detalhe = df_backlog_filtrado[df_backlog_filtrado['responsavel'].str.contains(analista_selecionado, case=False, na=False)].copy()
                            
                            if not df_detalhe.empty:
                                df_detalhe['link'] = "https://ddsinfo.atlassian.net/browse/" + df_detalhe['issue_key']
                                st.dataframe(
                                    df_detalhe[['issue_key','resumo' , 'responsavel', 'tipo_item', 'status','cliente','link']], 
                                    hide_index=True,
                                    use_container_width=True,
                                    column_config={
                                        "issue_key": "Chave",
                                        "resumo" : "Resumo",
                                        "responsavel": "Analista",
                                        "tipo_item": "Tipo",
                                        "status": "Status",
                                        "cliente": "Cliente",
                                        "link": st.column_config.LinkColumn("Jira")
                                    }
                                )
                            else:
                                st.warning("Nenhuma tarefa pendente para este filtro.")
                        
                    else: 
                        st.info("Sem dados de análise.")

            with st.container(border=True):
                st.markdown("#### Equipe de Desenvolvimento")
                
                import re
                
                colunas_lower = df_sprint_desenvolvimento.columns.str.lower()
                if 'pontos' in colunas_lower:
                    col_pts_original = df_sprint_desenvolvimento.columns[colunas_lower.tolist().index('pontos')]
                elif 'story_points' in colunas_lower:
                    col_pts_original = df_sprint_desenvolvimento.columns[colunas_lower.tolist().index('story_points')]
                elif 'estimativa' in colunas_lower:
                    col_pts_original = df_sprint_desenvolvimento.columns[colunas_lower.tolist().index('estimativa')]
                else:
                    col_pts_original = 'pontos_calc'
                    df_sprint_desenvolvimento[col_pts_original] = 0.0
                
                if col_pts_original != 'pontos_calc':
                    limpeza = df_sprint_desenvolvimento[col_pts_original].astype(str)
                    limpeza = limpeza.str.replace(',', '.', regex=False)
                    limpeza = limpeza.str.replace(r'[^\d\.]', '', regex=True)
                    limpeza = limpeza.replace('', '0')
                    df_sprint_desenvolvimento['pontos_calc'] = pd.to_numeric(limpeza, errors='coerce').fillna(0.0)

                if not df_sprint_desenvolvimento.empty:
                    nomes_devs = ["Felipe", "Kauan", "Gustavo", "Luiz", "Isaías", "Isaias", "Nei", "Guilherme", "João", "Eder"]
                    nomes_devs_regex = '|'.join(nomes_devs)

                    df_devs_backlog = df_sprint_desenvolvimento[
                        (df_sprint_desenvolvimento['responsavel'].str.contains(nomes_devs_regex, case=False, na=False)) &
                        (df_sprint_desenvolvimento['responsavel'].notna()) & 
                        (df_sprint_desenvolvimento['responsavel'].str.strip() != "") &
                        (~df_sprint_desenvolvimento['status'].isin(status_alvo))
                    ].copy()

                    # "Finalizados" = itens que já entraram em status alvo -> mesma base usada em
                    # "✅ Entregas da Sprint" (TB_SPRINT_DETAILS / df_filtrado), pra bater os números.
                    df_devs_finalizados = df_filtrado[
                        (df_filtrado['responsavel'].str.contains(nomes_devs_regex, case=False, na=False)) &
                        (df_filtrado['responsavel'].notna()) &
                        (df_filtrado['responsavel'].str.strip() != "")
                    ].copy() if not df_filtrado.empty else pd.DataFrame()

                    if not df_devs_finalizados.empty:
                        df_devs_finalizados['pontos_calc'] = pd.to_numeric(
                            df_devs_finalizados['pontos'].astype(str).str.replace(',', '.', regex=False).str.replace(r'[^\d\.]', '', regex=True),
                            errors='coerce'
                        ).fillna(0.0)

                    devs_agrupado_pend = (
                        df_devs_backlog.groupby('responsavel').agg(Quantidade=('issue_key', 'count'), Pontos=('pontos_calc', 'sum')).reset_index()
                        if not df_devs_backlog.empty else pd.DataFrame(columns=['responsavel', 'Quantidade', 'Pontos'])
                    ).rename(columns={'responsavel': 'Responsável'})

                    devs_agrupado_fin = (
                        df_devs_finalizados.groupby('responsavel').agg(Quantidade=('issue_key', 'count'), Pontos=('pontos_calc', 'sum')).reset_index()
                        if not df_devs_finalizados.empty else pd.DataFrame(columns=['responsavel', 'Quantidade', 'Pontos'])
                    ).rename(columns={'responsavel': 'Responsável'})

                    if not devs_agrupado_pend.empty or not devs_agrupado_fin.empty:
                        radio_equipe_dev = st.radio(
                            "Visualizar:", ["Pendentes", "Finalizados"],
                            horizontal=True, key="radio_equipe_dev_view", index=1
                        )

                        if radio_equipe_dev == "Pendentes":
                            devs_agrupado, devs_agrupado_ghost = devs_agrupado_pend.copy(), devs_agrupado_fin.copy()
                            rotulo_view, rotulo_ghost = "Pendentes", "Entregue"
                        else:
                            devs_agrupado, devs_agrupado_ghost = devs_agrupado_fin.copy(), devs_agrupado_pend.copy()
                            rotulo_view, rotulo_ghost = "Finalizados", "Pendente"

                        total_devs = devs_agrupado['Quantidade'].sum() if not devs_agrupado.empty else 0
                        total_pontos = devs_agrupado['Pontos'].sum() if not devs_agrupado.empty else 0.0

                        col_t1, col_t2 = st.columns(2)
                        col_t1.metric(f"Total de Itens ({rotulo_view})", int(total_devs))
                        col_t2.metric(f"Total de Pontos ({rotulo_view})", f"{total_pontos:.1f}")

                        # ---- Marcador global da equipe: finalizado x solicitado ----
                        # Os cards por dev respondem "quem está com o quê". Este bloco responde
                        # "quanto do total pedido à equipe já saiu", que é a leitura de gestão.
                        eq_itens_fin = float(devs_agrupado_fin['Quantidade'].sum()) if not devs_agrupado_fin.empty else 0.0
                        eq_itens_pend = float(devs_agrupado_pend['Quantidade'].sum()) if not devs_agrupado_pend.empty else 0.0
                        eq_itens_total = eq_itens_fin + eq_itens_pend

                        def _barra_consolidada(feito, total, cor, casas=0):
                            """Barra única equipe: sólido = finalizado, silhueta = total solicitado."""
                            fmt = f".{casas}f"
                            pct = (feito / total * 100) if total > 0 else 0.0
                            df_eq = pd.DataFrame({
                                'Equipe': ['Equipe'],
                                'Finalizado': [feito],
                                'Solicitado': [total],
                                'Rotulo': [f"{feito:.{casas}f} de {total:.{casas}f}  ({pct:.1f}%)"],
                            })
                            eixo_y_eq = alt.Y('Equipe:N', title='', axis=None)
                            ghost = alt.Chart(df_eq).mark_bar(
                                fill=cor, fillOpacity=0.15, stroke=cor, strokeOpacity=0.55,
                                strokeWidth=1, cornerRadiusEnd=3, height=34
                            ).encode(
                                x=alt.X('Solicitado:Q', title='', axis=alt.Axis(grid=False)),
                                y=eixo_y_eq,
                                tooltip=[
                                    alt.Tooltip('Solicitado:Q', title='Solicitado', format=fmt),
                                    alt.Tooltip('Finalizado:Q', title='Finalizado', format=fmt),
                                ]
                            )
                            solido = alt.Chart(df_eq).mark_bar(
                                color=cor, cornerRadiusEnd=3, height=34
                            ).encode(
                                x=alt.X('Finalizado:Q', title='', axis=alt.Axis(grid=False)),
                                y=eixo_y_eq,
                                tooltip=[alt.Tooltip('Finalizado:Q', title='Finalizado', format=fmt)]
                            )
                            # Rótulo ancorado no zero (align left): encostado na ponta da barra ele
                            # sairia do gráfico quando o percentual fosse alto.
                            texto = alt.Chart(df_eq).mark_text(
                                align='left', baseline='middle', dx=6, color='white', fontWeight='bold'
                            ).encode(x=alt.value(0), y=eixo_y_eq, text=alt.Text('Rotulo:N'))
                            return (ghost + solido + texto).properties(height=60)

                        with st.container(border=True):
                            st.markdown("**Consolidado da Equipe**")
                            st.altair_chart(
                                _barra_consolidada(eq_itens_fin, eq_itens_total, '#4CA6FF', casas=0),
                                use_container_width=True, theme="streamlit"
                            )

                        st.divider()

                        if not devs_agrupado.empty:
                            devs_agrupado_cards = devs_agrupado.sort_values(by='Quantidade', ascending=False).reset_index(drop=True)
                            num_devs = len(devs_agrupado_cards)
                            cols_devs = st.columns(min(num_devs, 6) if num_devs > 0 else 1)

                            for i, row in devs_agrupado_cards.iterrows():
                                cols_devs[i % len(cols_devs)].metric(
                                    label=str(row['Responsável']),
                                    value=f"{row['Quantidade']}",
                                    delta=f"{row['Pontos']:.1f} pts"
                                )

                            st.markdown("<br>", unsafe_allow_html=True)

                            # outer: dev que só tem itens na outra visão (ex.: entregou tudo e não tem
                            # nada pendente) precisa aparecer no gráfico, senão a barra "total" mente.
                            df_combo = devs_agrupado.merge(
                                devs_agrupado_ghost, on='Responsável', how='outer', suffixes=('', '_ghost')
                            ).fillna(0)

                            # Total analisado do dev = o que está na visão atual + o que está na outra.
                            # A barra sólida vai de 0 até a visão atual; a silhueta se estende até o total.
                            df_combo['Total_Itens'] = df_combo['Quantidade'] + df_combo['Quantidade_ghost']
                            df_combo['Total_Pontos'] = df_combo['Pontos'] + df_combo['Pontos_ghost']

                            # Rótulo do total só aparece quando há sobra de silhueta, senão colide
                            # com o rótulo da barra sólida (que fica na mesma posição).
                            df_combo['Rotulo_Total_Itens'] = [
                                f"{t:.0f}" if t > q else "" for t, q in zip(df_combo['Total_Itens'], df_combo['Quantidade'])
                            ]
                            df_combo['Rotulo_Total_Pontos'] = [
                                f"{t:.1f}" if t > p else "" for t, p in zip(df_combo['Total_Pontos'], df_combo['Pontos'])
                            ]

                            ordem_devs = (
                                df_combo.sort_values(by=['Quantidade', 'Total_Itens'], ascending=False)['Responsável'].tolist()
                            )

                            col_graf1, col_graf2 = st.columns(2)
                            altura_grafico = max(250, num_devs * 35)

                            with col_graf1:
                                st.markdown(f"###### Itens {rotulo_view.lower()} por Devs")
                                ghost_itens = alt.Chart(df_combo).mark_bar(
                                    fill="#4CA6FF", fillOpacity=0.15,
                                    stroke="#4CA6FF", strokeOpacity=0.55, strokeWidth=1,
                                    cornerRadiusEnd=3
                                ).encode(
                                    x=alt.X('Total_Itens:Q', title='Itens'),
                                    y=alt.Y('Responsável:N', sort=ordem_devs, title=''),
                                    tooltip=[
                                        'Responsável',
                                        alt.Tooltip('Total_Itens:Q', title='Itens (Total)', format='.0f'),
                                        alt.Tooltip('Quantidade:Q', title=f'Itens ({rotulo_view})', format='.0f'),
                                        alt.Tooltip('Quantidade_ghost:Q', title=f'Itens ({rotulo_ghost})', format='.0f')
                                    ]
                                )
                                label_total_itens = ghost_itens.mark_text(
                                    align='left', baseline='middle', dx=3, color='#9AA5B1'
                                ).encode(text=alt.Text('Rotulo_Total_Itens:N'))
                                bar_itens = alt.Chart(df_combo).mark_bar(color="#4CA6FF", cornerRadiusEnd=3).encode(
                                    x=alt.X('Quantidade:Q', title='Itens', axis=alt.Axis(grid=False)),
                                    y=alt.Y('Responsável:N', sort=ordem_devs, title=''),
                                    tooltip=['Responsável', alt.Tooltip('Quantidade:Q', title=f'Itens ({rotulo_view})'), alt.Tooltip('Pontos:Q', format='.1f')]
                                )
                                # outer merge pode transformar a contagem em float -> formata pra não virar "19.0"
                                label_itens = bar_itens.mark_text(align='left', baseline='middle', dx=3, color='white').encode(
                                    text=alt.Text('Quantidade:Q', format='.0f')
                                )
                                st.altair_chart(
                                    (ghost_itens + bar_itens + label_itens + label_total_itens).properties(height=altura_grafico),
                                    use_container_width=True, theme="streamlit"
                                )

                            with col_graf2:
                                st.markdown(f"###### Pontos {rotulo_view.lower()} por Devs")
                                ghost_pontos = alt.Chart(df_combo).mark_bar(
                                    fill="#FF9F43", fillOpacity=0.15,
                                    stroke="#FF9F43", strokeOpacity=0.55, strokeWidth=1,
                                    cornerRadiusEnd=3
                                ).encode(
                                    x=alt.X('Total_Pontos:Q', title='Pontos'),
                                    y=alt.Y('Responsável:N', sort=ordem_devs, title=''),
                                    tooltip=[
                                        'Responsável',
                                        alt.Tooltip('Total_Pontos:Q', title='Pontos (Total)', format='.1f'),
                                        alt.Tooltip('Pontos:Q', title=f'Pontos ({rotulo_view})', format='.1f'),
                                        alt.Tooltip('Pontos_ghost:Q', title=f'Pontos ({rotulo_ghost})', format='.1f')
                                    ]
                                )
                                label_total_pontos = ghost_pontos.mark_text(
                                    align='left', baseline='middle', dx=3, color='#9AA5B1'
                                ).encode(text=alt.Text('Rotulo_Total_Pontos:N'))
                                bar_pontos = alt.Chart(df_combo).mark_bar(color="#FF9F43", cornerRadiusEnd=3).encode(
                                    x=alt.X('Pontos:Q', title='Pontos', axis=alt.Axis(grid=False)),
                                    y=alt.Y('Responsável:N', sort=ordem_devs, title=''),
                                    tooltip=['Responsável', alt.Tooltip('Quantidade:Q', title=f'Itens ({rotulo_view})'), alt.Tooltip('Pontos:Q', format='.1f')]
                                )
                                label_pontos = bar_pontos.mark_text(align='left', baseline='middle', dx=3, color='white').encode(text=alt.Text('Pontos:Q', format='.1f'))
                                st.altair_chart(
                                    (ghost_pontos + bar_pontos + label_pontos + label_total_pontos).properties(height=altura_grafico),
                                    use_container_width=True, theme="streamlit"
                                )

                            st.caption(
                                f"Barra sólida = {rotulo_view.lower()}. A silhueta se estende até o **total analisado** "
                                f"do dev na sprint ({rotulo_view.lower()} + {rotulo_ghost.lower()})."
                            )
                        else:
                            st.info(f"Nenhum item {rotulo_view.lower()} encontrado para a equipe.")

                        st.markdown("<br>", unsafe_allow_html=True)
                        

                        with st.expander("Detalhes de itens da Equipe de Desenvolvimento"):
                            df_resumo_devs = devs_agrupado_pend.merge(
                                devs_agrupado_fin, on='Responsável', how='outer', suffixes=('_pend', '_fin')
                            ).fillna(0)
                            df_resumo_devs = df_resumo_devs.rename(columns={
                                'Quantidade_pend': 'Pendente (Itens)',
                                'Quantidade_fin': 'Entregue (Itens)',
                                'Pontos_pend': 'Pendente (Pts)',
                                'Pontos_fin': 'Entregue (Pts)'
                            })
                            df_resumo_devs['Pendente (Itens)'] = df_resumo_devs['Pendente (Itens)'].astype(int)
                            df_resumo_devs['Entregue (Itens)'] = df_resumo_devs['Entregue (Itens)'].astype(int)
                            df_resumo_devs = df_resumo_devs.sort_values(by='Pendente (Itens)', ascending=False)
    
                            st.dataframe(
                                df_resumo_devs[['Responsável', 'Pendente (Itens)', 'Entregue (Itens)' , 'Pendente (Pts)', 'Entregue (Pts)']],
                                hide_index=True,
                                use_container_width=True,
                                column_config={
                                    'Pendente (Pts)': st.column_config.NumberColumn(format="%.1f"),
                                    'Entregue (Pts)': st.column_config.NumberColumn(format="%.1f"),
                                }
                            )
                           
                


        st.divider()

        st.subheader(f"Entregas da {sprint_selecionada.split(' - ')[0]} (Pontos)")

        if not df_filtrado.empty:
            
            with st.container(border=True):
                col1, col2, col3 = st.columns(3)
                total_pontos = df_filtrado['pontos'].sum()
                sustentacao = df_filtrado[df_filtrado['categoria'] == 'Sustentação']['pontos'].sum()
                desenvolvimento = df_filtrado[df_filtrado['categoria'] == 'Desenvolvimento']['pontos'].sum()

                col1.metric("Total de Pontos Entregues", f"{total_pontos:.1f}")
                perc_sust = (sustentacao/total_pontos*100) if total_pontos > 0 else 0
                perc_desv = (desenvolvimento/total_pontos*100) if total_pontos > 0 else 0
                col2.metric("Sustentação", f"{sustentacao:.1f}", f"{perc_sust:.1f}%")
                col3.metric("Desenvolvimento", f"{desenvolvimento:.1f}", f"{perc_desv:.1f}%")

            col_rank1, col_rank2 = st.columns([2, 3])
            
            with col_rank1:
                    st.write("Entregas por Desenvolvedor")
                    
                    df_ranking = df_filtrado.groupby('responsavel')['pontos'].sum().reset_index()
                    df_ranking = df_ranking[df_ranking['pontos'] > 0]
                    
                    df_ranking = df_ranking.sort_values(by='pontos', ascending=False)

                    if not df_ranking.empty:
                        altura_dinamica = max(350, len(df_ranking) * 30)

                        grafico_barras = alt.Chart(df_ranking).mark_bar(color='#4CA6FF').encode(
                            x=alt.X('pontos:Q', title='Pontos Entregues', axis=alt.Axis(grid=False)),
                            y=alt.Y('responsavel:N', sort='-x', title=''), 
                            tooltip=['responsavel', 'pontos']
                        )
                        
                        textos = grafico_barras.mark_text(align='left', baseline='middle', dx=5, color='white').encode(text='pontos:Q')
                        
                        grafico_final = (grafico_barras + textos).properties(height=altura_dinamica)
                        st.altair_chart(grafico_final, use_container_width=True, theme="streamlit")
                    else:
                        st.info("Sem pontuações > 0.")

            with col_rank2:
                    st.write("**Detalhamento das Tarefas Entregues**")
                    dev_selecionado = st.selectbox("Filtrar entregas por Desenvolvedor:", ["Todos"] + list(df_ranking['responsavel']))

                    if dev_selecionado != "Todos": tabela_detalhe = df_filtrado[df_filtrado['responsavel'] == dev_selecionado].copy()
                    else: tabela_detalhe = df_filtrado.copy()
                    
                    tabela_detalhe.columns = tabela_detalhe.columns.str.lower()
                    if 'status' not in tabela_detalhe.columns:
                        tabela_detalhe['status'] = 'Aguardando Sincronização'
                    
                    tabela_detalhe['link'] = "https://ddsinfo.atlassian.net/browse/" + tabela_detalhe['issue_key']
                    
                    st.dataframe(
                        tabela_detalhe[['issue_key', 'sistema', 'cliente', 'resumo', 'status', 'tipo_item', 'categoria', 'pontos', 'link']], 
                        use_container_width=True, hide_index=True,
                        column_config={
                            "issue_key": "Chave", 
                            "sistema": "Sistema", 
                            "cliente": "Cliente",
                            "resumo": st.column_config.TextColumn("Resumo", width="large"),
                            "status": "Status",
                            "tipo_item": "Tipo", "categoria": "Categoria", "pontos": "Pontos",
                            "link": st.column_config.LinkColumn("Jira")
                        }
                    )

            # ========================================================
            # RITMO DA EQUIPE: PONTOS POR DEV x ESPERADO
            # ========================================================
            # A escala do time fecha 13 pontos em 5 dias (1 semana útil). Esse é o ritmo esperado
            # de UM dev por semana -- e a referência contra a qual a média real é medida.
            PONTOS_POR_SEMANA_DEV = 13
            DIAS_UTEIS_SEMANA = 5
            # Tamanho fixo da equipe de desenvolvimento. É o denominador da média por dev e não
            # sai dos dados de propósito: quem entregou 0 ponto não aparece em df_filtrado
            # (férias, alocação em outro projeto, dev novo), e usar só quem entregou inflaria a
            # média justamente nas sprints com gente parada.
            QTD_DEVS_EQUIPE = 8

            with st.expander("Ritmo da equipe", expanded=False):
                _linha_sprint_ritmo = df_sprints[df_sprints['nome_exibicao'] == sprint_selecionada]
                _ini_ritmo = pd.to_datetime(_linha_sprint_ritmo['data_inicio'].iloc[0], errors='coerce') if not _linha_sprint_ritmo.empty else pd.NaT
                _fim_ritmo = pd.to_datetime(_linha_sprint_ritmo['data_fim'].iloc[0], errors='coerce') if not _linha_sprint_ritmo.empty else pd.NaT

                if pd.isna(_ini_ritmo) or pd.isna(_fim_ritmo):
                    st.info("Sprint sem datas cadastradas.")
                else:
                    hoje_ritmo = pd.Timestamp(datetime.now().date())
                    # Dias ÚTEIS (bdate_range = seg-sex). Contar dia corrido inflaria o esperado
                    # em ~40%, já que fim de semana não produz entrega.
                    _fim_decorrido = min(hoje_ritmo, _fim_ritmo)
                    dias_uteis_totais = len(pd.bdate_range(_ini_ritmo, _fim_ritmo))
                    dias_uteis_decorridos = len(pd.bdate_range(_ini_ritmo, _fim_decorrido)) if _fim_decorrido >= _ini_ritmo else 0

                    df_ritmo = df_filtrado.copy()
                    df_ritmo['pontos'] = pd.to_numeric(df_ritmo['pontos'], errors='coerce').fillna(0.0)

                    s_dev, s_dias = st.columns(2)
                    qtd_devs_ativos = s_dev.slider(
                        "Quantidade de devs:", min_value=1, max_value=20, value=QTD_DEVS_EQUIPE,
                        key=f"slider_devs_ritmo_{id_sprint_selecionada}",
                        help="Denominador da média por dev. Quem não entregou nada também conta."
                    )
                    dias_considerados = s_dias.slider(
                        f"Dias úteis considerados (de {dias_uteis_totais}):", min_value=0, max_value=dias_uteis_totais,
                        value=dias_uteis_decorridos, key=f"slider_dias_ritmo_{id_sprint_selecionada}",
                        help="Padrão: dias úteis (seg-sex) desde o início da sprint até hoje."
                    )

                    pontos_realizados = float(df_ritmo['pontos'].sum())
                    media_real_por_dev = pontos_realizados / qtd_devs_ativos

                    # Esperado proporcional aos dias úteis considerados, não à sprint inteira.
                    esperado_por_dev = PONTOS_POR_SEMANA_DEV * (dias_considerados / DIAS_UTEIS_SEMANA)
                    esperado_equipe_total = PONTOS_POR_SEMANA_DEV * (dias_uteis_totais / DIAS_UTEIS_SEMANA) * qtd_devs_ativos

                    desvio_por_dev = media_real_por_dev - esperado_por_dev
                    pct_atingido = (media_real_por_dev / esperado_por_dev * 100) if esperado_por_dev > 0 else 0.0

                    r1, r2, r3, r4, r5 = st.columns(5)
                    r1.metric("Pontos Entregues", f"{pontos_realizados:.1f}")
                    r2.metric("Média por Dev", f"{media_real_por_dev:.1f} pts")
                    r3.metric("Esperado por Dev", f"{esperado_por_dev:.1f} pts",
                              help=f"{PONTOS_POR_SEMANA_DEV} pts por semana útil × {dias_considerados} dia(s) útil(eis) / {DIAS_UTEIS_SEMANA}.")
                    r4.metric("Ritmo", f"{pct_atingido:.0f}%", delta=f"{desvio_por_dev:+.1f} pts/dev")
                    r5.metric("Meta da Equipe (sprint)", f"{esperado_equipe_total:.1f} pts",
                              help=f"Sprint inteira ({dias_uteis_totais} dias úteis) × {qtd_devs_ativos} devs.")

                    st.divider()

                    # ---- Por dev: quem está puxando o ritmo para cima/baixo ----
                    st.write("**Pontos por Desenvolvedor**")
                    df_por_dev = (
                        df_ritmo[df_ritmo['pontos'] > 0]
                        .groupby('responsavel')
                        .agg(Itens=('issue_key', 'count'), Pontos=('pontos', 'sum'))
                        .reset_index()
                        .rename(columns={'responsavel': 'Responsável'})
                    )

                    if df_por_dev.empty:
                        st.info("Nenhum ponto entregue nesta sprint.")
                    else:
                        df_por_dev['Esperado'] = esperado_por_dev
                        df_por_dev['Desvio'] = df_por_dev['Pontos'] - esperado_por_dev
                        df_por_dev['% do Esperado'] = (
                            (df_por_dev['Pontos'] / esperado_por_dev * 100) if esperado_por_dev > 0 else 0.0
                        )
                        df_por_dev = df_por_dev.sort_values(by='Pontos', ascending=False)

                        col_rt1, col_rt2 = st.columns([3, 2])

                        with col_rt1:
                            st.dataframe(
                                df_por_dev[['Responsável', 'Itens', 'Pontos', 'Esperado', 'Desvio', '% do Esperado']],
                                hide_index=True, use_container_width=True,
                                column_config={
                                    'Pontos': st.column_config.NumberColumn(format="%.1f"),
                                    'Esperado': st.column_config.NumberColumn("Esperado (até hoje)", format="%.1f"),
                                    'Desvio': st.column_config.NumberColumn(format="%+.1f"),
                                    '% do Esperado': st.column_config.NumberColumn(format="%.0f%%"),
                                }
                            )

                        with col_rt2:
                            altura_ritmo = max(220, len(df_por_dev) * 30)
                            barras_ritmo = alt.Chart(df_por_dev).mark_bar(color='#4CA6FF').encode(
                                x=alt.X('Pontos:Q', title='Pontos entregues', axis=alt.Axis(grid=False)),
                                y=alt.Y('Responsável:N', sort='-x', title=''),
                                tooltip=[
                                    'Responsável',
                                    alt.Tooltip('Itens:Q'),
                                    alt.Tooltip('Pontos:Q', format='.1f'),
                                    alt.Tooltip('Desvio:Q', title='Desvio vs. esperado', format='+.1f'),
                                ]
                            )
                            rotulos_ritmo = barras_ritmo.mark_text(
                                align='left', baseline='middle', dx=4, color='white'
                            ).encode(text=alt.Text('Pontos:Q', format='.1f'))
                            # Régua no esperado: é ela que transforma a barra em diagnóstico
                            # ("passou ou não da meta") em vez de só um ranking.
                            regua_esperado = alt.Chart(
                                pd.DataFrame({'esperado': [esperado_por_dev]})
                            ).mark_rule(color='#FF9F43', strokeDash=[4, 4], strokeWidth=2).encode(
                                x=alt.X('esperado:Q'),
                                tooltip=[alt.Tooltip('esperado:Q', title='Esperado por dev', format='.1f')]
                            )
                            st.altair_chart(
                                (barras_ritmo + rotulos_ritmo + regua_esperado).properties(height=altura_ritmo),
                                use_container_width=True, theme="streamlit"
                            )
        else:
            st.info("Nenhuma entrega contabilizada.")

        st.subheader("Burndown da Sprint")

        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            escopo_burndown = st.radio(
                "Escopo:",
                ["Sprint Atual", "Sprint Atual + Backlog 2"],
                horizontal=True
            )
        with col_b2:
            visao_burndown = st.radio(
                "Visão:",
                ["Geral", "Sustentação", "Desenvolvimento"],
                horizontal=True
            )
        with col_b3:
            ciclo_burndown = st.radio(
                "Ciclo:",
                ["Parcial (até 3.3)", "Total (até 6.0 Concluído)"],
                horizontal=True, key="radio_ciclo_burndown",
                help="Parcial: o item sai do restante ao entrar em 3.3 Revisão de Código (cálculo original). "
                     "Total: só sai ao entrar em 6.0 Concluído. Pendências de terceiros (5.0/5.1/5.2) e "
                     "7.0 Dispensado ficam fora das duas contas no ciclo total."
            )

        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            num_sprints = st.slider("Qtd de Sprints anteriores para média:", min_value=1, max_value=6, value=5, key="slider_sprints_burndown")
        with col2:
            show_media_entrega = st.checkbox("Média de Entrega Diária", value=True)
        with col3:
            show_media_sprint = st.checkbox("Média por Sprint", value=True)

        col4, col5, col6 = st.columns(3)
        with col4:
            show_incluidos_diario = st.checkbox("Exibir Incluídos Diários", value=False)
        with col5:
            show_concluidos_diario = st.checkbox("Exibir Concluídos Diários", value=False)

        if not df_backlog_filtrado.empty or not df_filtrado.empty:
            id_sprint = int(df_sprints[df_sprints['nome_exibicao'] == sprint_selecionada]['id'].iloc[0])
            
            tipos_sustentacao = ["erro", "atendimento", "retorno negativo (rn)"]
            if not df_backlog_filtrado.empty and 'categoria' not in df_backlog_filtrado.columns:
                df_backlog_filtrado['categoria'] = df_backlog_filtrado['tipo_item'].apply(lambda x: "Sustentação" if str(x).lower() in tipos_sustentacao else "Desenvolvimento")
            if not df_filtrado.empty and 'categoria' not in df_filtrado.columns:
                df_filtrado['categoria'] = df_filtrado['tipo_item'].apply(lambda x: "Sustentação" if str(x).lower() in tipos_sustentacao else "Desenvolvimento")

            
            if escopo_burndown == "Sprint Atual":
                df_base = df_sprint_desenvolvimento.copy() if 'df_sprint_desenvolvimento' in locals() else df_backlog_filtrado.copy()
                col_snap_prefix = 'qtd_{}_nativa'
            else:
                df_base = df_ambas_sprints.copy() if 'df_ambas_sprints' in locals() else df_backlog_filtrado.copy()
                col_snap_prefix = 'qtd_{}'

            if visao_burndown == "Geral":
                df_backlog_ativo = df_base.copy()
                df_filtrado_ativo = df_filtrado.copy()
                col_snapshot = col_snap_prefix.format('total')
            elif visao_burndown == "Sustentação":
                df_backlog_ativo = df_base[df_base['categoria'] == 'Sustentação'].copy() if not df_base.empty else pd.DataFrame()
                df_filtrado_ativo = df_filtrado[df_filtrado['categoria'] == 'Sustentação'].copy() if not df_filtrado.empty else pd.DataFrame()
                col_snapshot = col_snap_prefix.format('sust')
            else: 
                df_backlog_ativo = df_base[df_base['categoria'] == 'Desenvolvimento'].copy() if not df_base.empty else pd.DataFrame()
                df_filtrado_ativo = df_filtrado[df_filtrado['categoria'] == 'Desenvolvimento'].copy() if not df_filtrado.empty else pd.DataFrame()
                col_snapshot = col_snap_prefix.format('desv')

            total_atual_pendentes = len(df_backlog_ativo)

            # Burndown individual: snapshots não têm pessoa, então a curva é reconstruída item a item.
            # Fila real (TB_SPRINT_FILA_ESTADO): quando existe, o item conta a partir da entrada na sprint.
            df_fila_sp = (df_fila_estado[pd.to_numeric(df_fila_estado['sprint_id'], errors='coerce') == id_sprint].copy()
                          if not df_fila_estado.empty else df_fila_estado)
            usar_fila_real = not df_fila_sp.empty

            _resp_opcoes = pd.concat([
                df_backlog_filtrado['responsavel'] if not df_backlog_filtrado.empty else pd.Series(dtype=str),
                df_filtrado['responsavel'] if not df_filtrado.empty else pd.Series(dtype=str),
                df_fila_sp['responsavel'] if usar_fila_real else pd.Series(dtype=str),
            ]).dropna().astype(str).str.strip()
            opcoes_pessoas_bd = sorted(p for p in _resp_opcoes.unique() if p)
            with col6:
                pessoas_burndown = st.multiselect(
                    "Pessoas (burndown individual):", opcoes_pessoas_bd,
                    key=f"multiselect_pessoas_burndown_{id_sprint}",
                    placeholder="Toda a equipe",
                    help="Vazio = equipe inteira (cálculo padrão pelos snapshots). "
                         "Com pessoas selecionadas, a curva é reconstruída a partir dos itens delas, sem os Ajustes."
                )
            # Com a fila real, o filtro por pessoa vale também no ciclo total (o estado guarda o responsável).
            filtro_pessoas_bd = bool(pessoas_burndown) and (ciclo_burndown.startswith("Parcial") or usar_fila_real)
            if pessoas_burndown and not filtro_pessoas_bd:
                st.info("O filtro por pessoa vale só para o ciclo parcial: o ciclo total não guarda "
                        "de quem são os itens entre 3.3 e 6.0. O gráfico abaixo mostra a equipe inteira.")
            # Ajuste é subtarefa no Jira: contaria o mesmo trabalho duas vezes.
            TIPOS_FORA_BURNDOWN_INDIVIDUAL = ["ajuste"]

            def _filtro_pessoas_e_tipo(df):
                if df.empty:
                    return df
                d = df[df['responsavel'].astype(str).str.strip().isin(pessoas_burndown)]
                return d[~d['tipo_item'].astype(str).str.lower().str.strip().isin(TIPOS_FORA_BURNDOWN_INDIVIDUAL)].copy()

            if filtro_pessoas_bd:
                df_backlog_ativo = _filtro_pessoas_e_tipo(df_backlog_ativo)
                df_filtrado_ativo = _filtro_pessoas_e_tipo(df_filtrado_ativo)
                total_atual_pendentes = len(df_backlog_ativo)

            # Na fila real, Ajuste fica fora também do burndown da equipe.
            def _sem_ajuste(df):
                if df is None or df.empty or 'tipo_item' not in df.columns:
                    return df
                return df[~df['tipo_item'].astype(str).str.lower().str.strip().isin(TIPOS_FORA_BURNDOWN_INDIVIDUAL)].copy()

            if usar_fila_real:
                df_backlog_ativo = _sem_ajuste(df_backlog_ativo)
                df_filtrado_ativo = _sem_ajuste(df_filtrado_ativo)

            # Snapshots não separam projeto: com parte dos projetos, usa a reconstrução item a item.
            filtro_projeto_bd = set(projeto) != set(projetos_disponiveis)
            if filtro_projeto_bd and not ciclo_burndown.startswith("Parcial") and not usar_fila_real:
                st.warning("O ciclo total ainda não separa por projeto: a contagem de itens entre 3.3 e 6.0 é "
                           "gravada somando todos os projetos. Para ver um projeto só, use o ciclo parcial "
                           "ou marque todos os projetos na barra lateral.")
            # Reconstrução item a item: pessoas selecionadas e/ou parte dos projetos (só no ciclo parcial).
            reconstruir_bd = (not usar_fila_real) and ciclo_burndown.startswith("Parcial") and (filtro_pessoas_bd or filtro_projeto_bd)

            # Ciclo total troca só as fontes (snapshots, entregas históricas, concluídos); o cálculo é o mesmo.
            df_snapshots_bd = df_snapshots
            df_entregas_hist_bd = df_issues
            df_concluidos_bd = df_filtrado_ativo
            ciclo_total = ciclo_burndown.startswith("Total")

            if ciclo_total:
                # Restante = backlog (antes de 3.3) + itens entre 3.3 e 6.0 (colunas *_POS).
                col_pos = col_snapshot.replace('_nativa', '') + '_pos' + ('_nativa' if col_snapshot.endswith('_nativa') else '')
                df_snapshots_bd = df_snapshots.copy()
                if col_pos in df_snapshots_bd.columns:
                    df_snapshots_bd['restante_ciclo_total'] = (
                        pd.to_numeric(df_snapshots_bd[col_snapshot], errors='coerce')
                        + pd.to_numeric(df_snapshots_bd[col_pos], errors='coerce')
                    )
                else:
                    df_snapshots_bd['restante_ciclo_total'] = float('nan')
                col_snapshot = 'restante_ciclo_total'

                # Hoje: backlog atual + contagem pós-desenvolvimento da última sincronização da sprint.
                if col_pos in df_snapshots.columns:
                    pos_sprint = pd.to_numeric(df_snapshots[df_snapshots['sprint_id'] == id_sprint][col_pos], errors='coerce').dropna()
                else:
                    pos_sprint = pd.Series(dtype=float)
                total_atual_pendentes = (len(df_backlog_ativo) + int(pos_sprint.iloc[-1])) if not pos_sprint.empty else None

                # Concluídos = entrada em 6.0 Concluído (TB_SPRINT_CONCLUSAO_TOTAL).
                df_ct = df_conclusao_total.copy()
                if not df_ct.empty:
                    df_ct['sprint_id'] = pd.to_numeric(df_ct['sprint_id'], errors='coerce').fillna(0).astype(int)
                    df_ct['projeto'] = df_ct['projeto'].astype(str).str.strip()
                    df_ct = df_ct[df_ct['projeto'].isin(projeto)].copy()
                    df_ct['categoria'] = df_ct['tipo_item'].apply(lambda x: "Sustentação" if str(x).lower() in tipos_sustentacao else "Desenvolvimento")
                df_entregas_hist_bd = df_ct
                df_concluidos_bd = df_ct[df_ct['sprint_id'] == id_sprint].copy() if not df_ct.empty else df_ct
                if visao_burndown != "Geral" and not df_concluidos_bd.empty:
                    df_concluidos_bd = df_concluidos_bd[df_concluidos_bd['categoria'] == visao_burndown].copy()
                if filtro_pessoas_bd and not df_concluidos_bd.empty:
                    # TB_SPRINT_CONCLUSAO_TOTAL não guarda o responsável: busca em DETAILS/BACKLOG pela chave.
                    _resp_ct = (pd.concat([df_backlog, df_issues], ignore_index=True)[['issue_key', 'responsavel']]
                                .drop_duplicates(subset=['issue_key'], keep='last'))
                    df_concluidos_bd = _filtro_pessoas_e_tipo(df_concluidos_bd.merge(_resp_ct, on='issue_key', how='left'))
                if usar_fila_real:
                    df_concluidos_bd = _sem_ajuste(df_concluidos_bd)

                if total_atual_pendentes is None:
                    st.info("Ciclo total ainda sem a contagem de itens entre 3.3 e 6.0 para esta sprint. "
                            "Ela passa a ser gravada a partir da próxima sincronização em 'Gerenciar Sprints'.")

            tickets_iniciais = (total_atual_pendentes or 0) + len(df_concluidos_bd)

            if 'df_snapshots_bd' in locals() and not df_snapshots_bd.empty:
                snaps_sp = df_snapshots_bd[df_snapshots_bd['sprint_id'] == id_sprint].copy()
                snaps_inicio = snaps_sp[snaps_sp['fase'] == 'INICIO']
                if not snaps_inicio.empty:
                    valor_snap = snaps_inicio.iloc[-1].get(col_snapshot, 0)
                    if pd.notnull(valor_snap) and valor_snap > 0:
                        tickets_iniciais = valor_snap

            data_ini_str = df_sprints[df_sprints['nome_exibicao'] == sprint_selecionada]['data_inicio'].iloc[0]
            data_fim_str = df_sprints[df_sprints['nome_exibicao'] == sprint_selecionada]['data_fim'].iloc[0]
            data_ini = data_ini_str if not isinstance(data_ini_str, str) else datetime.strptime(data_ini_str, "%Y-%m-%d").date()
            data_fim = data_fim_str if not isinstance(data_fim_str, str) else datetime.strptime(data_fim_str, "%Y-%m-%d").date()
            
            qtd_dias = (data_fim - data_ini).days + 1
            dias_sprint = [data_ini + timedelta(days=x) for x in range(qtd_dias)]

            # Reconstrução: restante no dia d = criado até d e sem entrada em 3.3 até d.
            def _base_reconstrucao(df_pend, df_entr):
                partes = []
                if df_pend is not None and not df_pend.empty:
                    p = df_pend[['issue_key', 'data_criacao']].copy()
                    p['_concl'] = pd.NaT
                    partes.append(p)
                if df_entr is not None and not df_entr.empty:
                    e = df_entr[['issue_key', 'data_criacao']].copy()
                    e['_concl'] = pd.to_datetime(df_entr['data_conclusao'], errors='coerce')
                    partes.append(e)
                if not partes:
                    return pd.DataFrame(columns=['issue_key', '_criado', '_concl'])
                # Mesma issue pendente e entregue: vale a entrega (mesmo critério da linha de concluídos).
                base = pd.concat(partes, ignore_index=True).drop_duplicates(subset=['issue_key'], keep='last')
                criado = pd.to_datetime(base['data_criacao'], errors='coerce').dt.date
                concl = pd.to_datetime(base['_concl'], errors='coerce').dt.date
                base['_criado'] = criado.where(criado.notna(), datetime.min.date())
                base['_concl'] = concl.where(concl.notna(), datetime.max.date())
                return base

            def _restante_no_dia(base, dia):
                return int(((base['_criado'] <= dia) & (base['_concl'] > dia)).sum())

            if reconstruir_bd:
                base_pessoas_bd = _base_reconstrucao(df_backlog_ativo, df_filtrado_ativo)
                # Diretriz: itens do recorte que já existiam no 1º dia (o snapshot de INÍCIO é da equipe toda).
                tickets_iniciais = int((base_pessoas_bd['_criado'] <= data_ini).sum()) if not base_pessoas_bd.empty else 0

            media_entrega_por_dia = []
            media_restante_por_dia = [None] * qtd_dias
            historico_restante = {d: None for d in range(qtd_dias)}
            historico_dias_entrega = {d: None for d in range(qtd_dias)}

            try:
                idx_atual = df_sprints.index[df_sprints['id'] == id_sprint].tolist()[0]
                sprints_anteriores = df_sprints.iloc[idx_atual+1 : idx_atual+1+num_sprints]
                ids_sprints_anteriores = sprints_anteriores['id'].tolist()

                historico_restante = {d: [] for d in range(qtd_dias)}

                if 'df_snapshots_bd' in locals() and not df_snapshots_bd.empty:
                    df_snaps_hist = df_snapshots_bd[
                        df_snapshots_bd['sprint_id'].isin(ids_sprints_anteriores)
                    ].copy()
                    
                    df_snaps_hist[col_snapshot] = pd.to_numeric(df_snaps_hist[col_snapshot], errors='coerce')
                    df_snaps_hist['data_dt'] = (
                        pd.to_datetime(df_snaps_hist['data_registro'], errors='coerce')
                        - pd.Timedelta(hours=3)
                    ).dt.date

                    for _, sp_row in sprints_anteriores.iterrows():
                        sp_id = sp_row['id']
                        sp_ini_str = sp_row['data_inicio']
                        sp_ini_date = (sp_ini_str if not isinstance(sp_ini_str, str)
                                       else datetime.strptime(sp_ini_str, "%Y-%m-%d").date())

                        df_sp_snaps = df_snaps_hist[df_snaps_hist['sprint_id'] == sp_id]
                        if df_sp_snaps.empty:
                            continue

                        dict_sp_restante = (
                            df_sp_snaps.sort_values('data_registro')
                            .groupby('data_dt')[col_snapshot] 
                            .last()
                            .dropna()
                            .to_dict()
                        )
                        if not dict_sp_restante:
                            continue

                        snaps_antes = {d: v for d, v in dict_sp_restante.items() if d <= sp_ini_date}
                        ultimo_conhecido = snaps_antes[max(snaps_antes)] if snaps_antes else None

                        for offset in range(qtd_dias):
                            dia_alvo = sp_ini_date + timedelta(days=offset)
                            if dia_alvo in dict_sp_restante:
                                ultimo_conhecido = dict_sp_restante[dia_alvo]
                            if ultimo_conhecido is not None:
                                historico_restante[offset].append((ultimo_conhecido, sp_row.get('descricao', sp_row.get('nome_sprint', str(sp_id)))))

                for offset in range(qtd_dias):
                    pares = [(v, s) for v, s in historico_restante[offset] if v is not None]
                    if pares:
                        valores = [v for v, _ in pares]
                        media_restante_por_dia[offset] = round(sum(valores) / len(valores), 1)
                        max_par = max(pares, key=lambda x: x[0])
                        min_par = min(pares, key=lambda x: x[0])
                        historico_restante[offset] = {'media': media_restante_por_dia[offset],
                                                      'max_val': max_par[0], 'max_sp': max_par[1],
                                                      'min_val': min_par[0], 'min_sp': min_par[1]}
                    else:
                        historico_restante[offset] = None

                historico_dias_entrega = {d: [] for d in range(qtd_dias)}

                if not df_entregas_hist_bd.empty and ids_sprints_anteriores:
                    df_issues_hist = df_entregas_hist_bd[
                        (df_entregas_hist_bd['projeto'].isin(projeto)) &
                        (df_entregas_hist_bd['sprint_id'].isin(ids_sprints_anteriores))
                    ].copy()
                    
                    if not df_issues_hist.empty:
                        if 'categoria' not in df_issues_hist.columns:
                            df_issues_hist['categoria'] = df_issues_hist['tipo_item'].apply(lambda x: "Sustentação" if str(x).lower() in tipos_sustentacao else "Desenvolvimento")
                        
                        if visao_burndown != "Geral":
                            df_issues_hist = df_issues_hist[df_issues_hist['categoria'] == visao_burndown]
                            
                        df_issues_hist['data_conclusao_dt'] = pd.to_datetime(
                            df_issues_hist['data_conclusao'], errors='coerce'
                        ).dt.date

                    for _, sp_row in sprints_anteriores.iterrows():
                        sp_id = sp_row['id']
                        sp_ini_str = sp_row['data_inicio']
                        sp_ini_date = (sp_ini_str if not isinstance(sp_ini_str, str)
                                       else datetime.strptime(sp_ini_str, "%Y-%m-%d").date())
                        df_sp_issues = df_issues_hist[df_issues_hist['sprint_id'] == sp_id]

                        if df_sp_issues.empty:
                            continue

                        dict_sp_concluidos = df_sp_issues.groupby('data_conclusao_dt').size().to_dict()
                        total_acc = 0
                        sp_nome = sp_row.get('descricao', sp_row.get('nome_sprint', str(sp_id)))
                        for offset in range(qtd_dias):
                            dia_alvo = sp_ini_date + timedelta(days=offset)
                            total_acc += dict_sp_concluidos.get(dia_alvo, 0)
                            historico_dias_entrega[offset].append((total_acc, sp_nome))

                for offset in range(qtd_dias):
                    pares = [(v, s) for v, s in historico_dias_entrega[offset] if v is not None]
                    if pares:
                        valores = [v for v, _ in pares]
                        media = round(sum(valores) / len(valores), 1)
                        media_entrega_por_dia.append(media)
                        max_par = max(pares, key=lambda x: x[0])
                        min_par = min(pares, key=lambda x: x[0])
                        historico_dias_entrega[offset] = {'media': media,
                                                          'max_val': max_par[0], 'max_sp': max_par[1],
                                                          'min_val': min_par[0], 'min_sp': min_par[1]}
                    else:
                        media_entrega_por_dia.append(None)
                        historico_dias_entrega[offset] = None
            except Exception as e:
                media_entrega_por_dia = [None] * qtd_dias
                media_restante_por_dia = [None] * qtd_dias

            dict_real_diario = {}
            if 'snaps_sp' in locals() and not snaps_sp.empty:
                snaps_sp['data_dt'] = (pd.to_datetime(snaps_sp['data_registro']) - pd.Timedelta(hours=3)).dt.date
                dict_real_diario = snaps_sp.sort_values('data_registro').groupby('data_dt')[col_snapshot].last().to_dict()
                if ciclo_total:
                    # Dias só com snapshots anteriores às colunas *_POS não têm valor de ciclo total.
                    dict_real_diario = {d: v for d, v in dict_real_diario.items() if pd.notnull(v)}

            if reconstruir_bd:
                # Trabalho Restante dia a dia pela reconstrução (vale também para os dias sem sincronização).
                dict_real_diario = (
                    {dia: _restante_no_dia(base_pessoas_bd, dia) for dia in dias_sprint if dia <= datetime.now().date()}
                    if not base_pessoas_bd.empty else {}
                )

                # Médias das sprints anteriores com os mesmos filtros.
                def _filtro_hist(df, sp_id, eh_pendente):
                    if df.empty:
                        return df
                    d = df[(df['sprint_id'] == sp_id) & (df['projeto'].isin(projeto))].copy()
                    if filtro_pessoas_bd:
                        d = _filtro_pessoas_e_tipo(d)
                    if eh_pendente and escopo_burndown == "Sprint Atual" and 'sprint_nativa' in d.columns:
                        d = d[d['sprint_nativa'] == 'SIM']
                    if visao_burndown != "Geral":
                        cat = d['tipo_item'].apply(lambda x: "Sustentação" if str(x).lower() in tipos_sustentacao else "Desenvolvimento")
                        d = d[cat == visao_burndown]
                    return d

                restantes_hist_p = {i: [] for i in range(qtd_dias)}
                entregas_hist_p = {i: [] for i in range(qtd_dias)}
                try:
                    _idx = df_sprints.index[df_sprints['id'] == id_sprint].tolist()[0]
                    _anteriores = df_sprints.iloc[_idx + 1: _idx + 1 + num_sprints]
                except IndexError:
                    _anteriores = df_sprints.iloc[0:0]
                for _, sp_row in _anteriores.iterrows():
                    sp_id = int(sp_row['id'])
                    sp_ini = pd.to_datetime(sp_row['data_inicio']).date()
                    base_sp = _base_reconstrucao(_filtro_hist(df_backlog, sp_id, True), _filtro_hist(df_issues, sp_id, False))
                    if base_sp.empty:
                        continue
                    for i in range(qtd_dias):
                        dia_sp = sp_ini + timedelta(days=i)
                        restantes_hist_p[i].append(_restante_no_dia(base_sp, dia_sp))
                        entregas_hist_p[i].append(int(((base_sp['_concl'] >= sp_ini) & (base_sp['_concl'] <= dia_sp)).sum()))
                media_restante_por_dia = [round(sum(v) / len(v), 1) if v else None for v in restantes_hist_p.values()]
                media_entrega_por_dia = [round(sum(v) / len(v), 1) if v else None for v in entregas_hist_p.values()]

            dict_concluidos_diario = {}
            if not df_concluidos_bd.empty:
                df_filtrado_copy = df_concluidos_bd.copy()
                df_filtrado_copy['data_conclusao_dt'] = pd.to_datetime(df_filtrado_copy['data_conclusao']).dt.date
                dict_concluidos_diario = df_filtrado_copy.groupby('data_conclusao_dt').size().to_dict()

            # Fila real: o item está no restante enquanto estiver na sprint, não for Bug/Ajuste e estiver antes
            # do fim do ciclo. Responsável, tipo e status são os de cada momento.
            STATUS_FORA_FILA_PARCIAL = {s.lower() for s in [
                "6.0 Concluído", "6.0 Pend. Merge p/ Homol.", "6.1 Pend. Gerar Artefatos", "6.2 Pend. Envio Homolog.",
                "7.0 Dispensado", "5.0 Pendência do Usuário", "5.1 Esperando por Aprovação", "5.2 Comercial - Aprovado",
                "5.3 Pendência de Homolog", "3.3 Revisão de Código", "4.0 A TESTAR", "4.1 Testando", "4.2 Mergear",
                "4.3 Pend. Versão",  # mesma lista que a sincronização exclui do backlog...
                "5.1.1 Em quarentena"]}  # ...+ quarentena, que conta como concluído (decisão da gestão)
            STATUS_FORA_FILA_TOTAL = {s.lower() for s in [
                "6.0 Concluído", "7.0 Dispensado", "5.0 Pendência do Usuário", "5.1 Esperando por Aprovação",
                "5.2 Comercial - Aprovado", "5.1.1 Em quarentena"]}
            # Entrar em quarentena conta como conclusão na linha de Concluídos (além de sair do restante).
            STATUS_CONCLUSAO_EXTRA = "5.1.1 em quarentena"
            agora_local = pd.Timestamp.now(tz="America/Sao_Paulo").tz_localize(None)

            def _recorte_fila(df_est):
                """Filtros que não dependem do tempo: projeto, escopo, ciclo, visão e pessoas."""
                if df_est.empty:
                    return df_est
                d = df_est[(df_est['tipo_item'].astype(str).str.lower() != 'bug') & (df_est['projeto'].isin(projeto))]
                if escopo_burndown == "Sprint Atual":
                    d = d[d['em_sprint_ativa'] == 1]
                else:
                    d = d[(d['em_sprint_ativa'] == 1) | (d['em_backlog2'] == 1)]
                fora = STATUS_FORA_FILA_TOTAL if ciclo_total else STATUS_FORA_FILA_PARCIAL
                d = d[~d['status'].astype(str).str.lower().isin(fora)]
                if visao_burndown != "Geral":
                    cat = d['tipo_item'].apply(lambda x: "Sustentação" if str(x).lower() in tipos_sustentacao else "Desenvolvimento")
                    d = d[cat == visao_burndown]
                if filtro_pessoas_bd:
                    d = _filtro_pessoas_e_tipo(d)
                return _sem_ajuste(d)

            def _fila_em(d, t):
                return set(d.loc[(d['valido_de'] <= t) & (d['valido_ate'].isna() | (d['valido_ate'] > t)), 'issue_key'])

            def _filas_por_dia(d, ini):
                """Fila no fim de cada dia da sprint (até agora) + entradas/saídas de cada dia."""
                filas, entradas, saidas = {}, {}, {}
                anterior = _fila_em(d, pd.Timestamp(ini))
                for offset in range(qtd_dias):
                    dia_x = ini + timedelta(days=offset)
                    if pd.Timestamp(dia_x) > agora_local:
                        break
                    # Fim do dia = 23:59:59 (o último período de uma sprint encerrada termina às 23:59:59.999).
                    t = min(pd.Timestamp(dia_x) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1), agora_local)
                    atual = _fila_em(d, t)
                    filas[offset], entradas[offset], saidas[offset] = atual, atual - anterior, anterior - atual
                    anterior = atual
                return filas, entradas, saidas

            def _quarentenas(df_est, saidas, ini, ja_concluidos, status_alvo_saida=None):
                """Saídas da fila que foram para um status de conclusão -> [(dia, chave)]. Padrão: 5.1.1 Em
                quarentena. Cada item conta uma vez e não conta se já foi concluído por outro critério."""
                status_alvo_saida = status_alvo_saida or {STATUS_CONCLUSAO_EXTRA}
                grupos = {k: g for k, g in df_est.groupby('issue_key')} if not df_est.empty else {}
                vistos, achados = set(ja_concluidos), []
                for o in sorted(saidas):
                    dia_x = ini + timedelta(days=o)
                    t = min(pd.Timestamp(dia_x) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1), agora_local)
                    for k in sorted(saidas[o] - vistos):
                        g = grupos.get(k)
                        if g is None:
                            continue
                        linha = g[(g['valido_de'] <= t) & (g['valido_ate'].isna() | (g['valido_ate'] > t))]
                        if not linha.empty and str(linha.iloc[0]['status']).lower() in status_alvo_saida:
                            achados.append((dia_x, k))
                            vistos.add(k)
                return achados

            quarentena_itens = []
            if usar_fila_real:
                fila_recorte = _recorte_fila(df_fila_sp)
                filas_dia, entradas_fila_dia, saidas_fila_dia = _filas_por_dia(fila_recorte, data_ini)
                if ciclo_total:
                    # Ciclo total: conclusão = saída da fila para 6.0, pela própria fila real.
                    concl_6 = _quarentenas(df_fila_sp, saidas_fila_dia, data_ini, set(), {"6.0 concluído"})
                    df_concluidos_bd = pd.DataFrame({'issue_key': [k for _, k in concl_6],
                                                     'data_conclusao': [pd.Timestamp(d) for d, _ in concl_6]})
                    dict_concluidos_diario = {}
                    for dia_c, _ in concl_6:
                        dict_concluidos_diario[dia_c] = dict_concluidos_diario.get(dia_c, 0) + 1
                quarentena_itens = _quarentenas(
                    df_fila_sp, saidas_fila_dia, data_ini,
                    set(df_concluidos_bd['issue_key']) if not df_concluidos_bd.empty else set())
                for dia_q, _ in quarentena_itens:
                    dict_concluidos_diario[dia_q] = dict_concluidos_diario.get(dia_q, 0) + 1
                dict_real_diario = {data_ini + timedelta(days=o): len(f) for o, f in filas_dia.items()}
                # Hoje também vem da fila (o backlog sincronizado não é mais a fonte do ponto de hoje).
                total_atual_pendentes = None
                # Diretriz: fila no fim do 1º dia + concluídos nele.
                tickets_iniciais = (len(filas_dia[0]) + dict_concluidos_diario.get(data_ini, 0)) if 0 in filas_dia else 0

                # Médias das sprints anteriores pela mesma regra (só as que têm fila reconstruída).
                restantes_hist_f = {i: [] for i in range(qtd_dias)}
                entregas_hist_f = {i: [] for i in range(qtd_dias)}
                try:
                    _idx_f = df_sprints.index[df_sprints['id'] == id_sprint].tolist()[0]
                    _anteriores_f = df_sprints.iloc[_idx_f + 1: _idx_f + 1 + num_sprints]
                except IndexError:
                    _anteriores_f = df_sprints.iloc[0:0]
                for _, sp_row in _anteriores_f.iterrows():
                    sp_id = int(sp_row['id'])
                    sp_ini = pd.to_datetime(sp_row['data_inicio']).date()
                    fila_sp_ant = _recorte_fila(df_fila_estado[pd.to_numeric(df_fila_estado['sprint_id'], errors='coerce') == sp_id])
                    if fila_sp_ant.empty:
                        continue
                    filas_ant, _, saidas_ant = _filas_por_dia(fila_sp_ant, sp_ini)
                    for o, f in filas_ant.items():
                        restantes_hist_f[o].append(len(f))
                    # Entregas acumuladas da sprint anterior com os mesmos filtros (projeto, visão, pessoas).
                    entr_ant = df_entregas_hist_bd[df_entregas_hist_bd['sprint_id'] == sp_id] if not df_entregas_hist_bd.empty else df_entregas_hist_bd
                    if ciclo_total:
                        # Mesma regra da sprint atual: conclusão = saída da fila para 6.0, pela fila real.
                        _c6 = _quarentenas(df_fila_estado[pd.to_numeric(df_fila_estado['sprint_id'], errors='coerce') == sp_id],
                                           saidas_ant, sp_ini, set(), {"6.0 concluído"})
                        entr_ant = pd.DataFrame({'issue_key': [k for _, k in _c6],
                                                 'data_conclusao': [pd.Timestamp(d) for d, _ in _c6]})
                    elif not entr_ant.empty:
                        entr_ant = entr_ant[entr_ant['projeto'].isin(projeto)]
                        if visao_burndown != "Geral":
                            cat_e = entr_ant['tipo_item'].apply(lambda x: "Sustentação" if str(x).lower() in tipos_sustentacao else "Desenvolvimento")
                            entr_ant = entr_ant[cat_e == visao_burndown]
                        if filtro_pessoas_bd:
                            if 'responsavel' not in entr_ant.columns:
                                _resp_e = (pd.concat([df_backlog, df_issues], ignore_index=True)[['issue_key', 'responsavel']]
                                           .drop_duplicates(subset=['issue_key'], keep='last'))
                                entr_ant = entr_ant.merge(_resp_e, on='issue_key', how='left')
                            entr_ant = _filtro_pessoas_e_tipo(entr_ant)
                        entr_ant = _sem_ajuste(entr_ant)
                    concl_ant = (pd.to_datetime(entr_ant['data_conclusao'], errors='coerce').dt.date
                                 if not entr_ant.empty else pd.Series(dtype=object))
                    # Quarentenas da sprint anterior também contam como conclusão (mesma regra da atual).
                    q_ant = _quarentenas(
                        df_fila_estado[pd.to_numeric(df_fila_estado['sprint_id'], errors='coerce') == sp_id],
                        saidas_ant, sp_ini, set(entr_ant['issue_key']) if not entr_ant.empty else set())
                    for o in range(qtd_dias):
                        limite = sp_ini + timedelta(days=o)
                        entregas_hist_f[o].append(int(((concl_ant >= sp_ini) & (concl_ant <= limite)).sum())
                                                  + sum(1 for d_q, _ in q_ant if d_q <= limite))
                media_restante_por_dia = [round(sum(v) / len(v), 1) if v else None for v in restantes_hist_f.values()]
                media_entrega_por_dia = [round(sum(v) / len(v), 1) if v else None for v in entregas_hist_f.values()]

            bd_dados = []
            passo_ideal = tickets_iniciais / (qtd_dias - 1) if qtd_dias > 1 else 0
            hoje = datetime.now().date()
            # Antes começava com ultimo_valor_conhecido = tickets_iniciais e ficava "preso" nesse valor
            # (ou em 0, quando não havia backlog sincronizado ainda) até achar o primeiro dado real.
            # Isso desenhava uma linha reta em 0/errada nos dias sem snapshot, dando a impressão de que
            # o trabalho já estava zerado, quando na verdade é que nunca existiu sincronização pra esse dia
            # (ex.: dias em que a extração falhava por causa do bug do ANALISTAS). Agora deixamos None
            # (lacuna no gráfico) até o primeiro dado real conhecido.
            ultimo_valor_conhecido = None
            total_concluidos_acumulado = 0

            # Incluídos (Diário) sem fila real: itens do recorte criados no dia (mesma regra do expander).
            _partes_incluidos = [
                d for d in (df_backlog_ativo, df_filtrado_ativo)
                if d is not None and not d.empty and 'data_criacao' in d.columns
            ]
            dict_criados_diario = {}
            if _partes_incluidos:
                _df_incluidos = pd.concat(_partes_incluidos, ignore_index=True)
                if 'issue_key' in _df_incluidos.columns:
                    _df_incluidos = _df_incluidos.drop_duplicates(subset=['issue_key'])
                dict_criados_diario = (
                    pd.to_datetime(_df_incluidos['data_criacao'], errors='coerce').dropna().dt.date
                    .value_counts().to_dict()
                )
            if usar_fila_real:
                # Com a fila real, "Incluídos" = itens que ENTRARAM na fila no dia (mesma lista do expander).
                dict_criados_diario = {data_ini + timedelta(days=o): len(e) for o, e in entradas_fila_dia.items()}

            for i, dia in enumerate(dias_sprint):
                ideal_restante = tickets_iniciais - (passo_ideal * i)
                # total_atual_pendentes só é None no ciclo total sem contagem pós-desenvolvimento.
                if dia == hoje and total_atual_pendentes is not None: ultimo_valor_conhecido = total_atual_pendentes
                elif dia in dict_real_diario: ultimo_valor_conhecido = dict_real_diario[dia]
                concluidos_hoje = dict_concluidos_diario.get(dia, 0)
                if dia <= hoje: total_concluidos_acumulado += concluidos_hoje

                itens_incluidos_dia = dict_criados_diario.get(dia, 0)

                bd_dados.append({
                    "Data": dia.strftime("%d/%m"),
                    "Diretriz": round(ideal_restante, 1),
                    "Trabalho Restante": ultimo_valor_conhecido if dia <= hoje else None,
                    "Concluídos Acumulados": total_concluidos_acumulado if dia <= hoje else None,
                    "Média Entrega Diária": round(media_entrega_por_dia[i], 1) if i < len(media_entrega_por_dia) and media_entrega_por_dia[i] is not None else None,
                    "Média por Sprint": media_restante_por_dia[i] if i < len(media_restante_por_dia) and media_restante_por_dia[i] is not None else None,
                    "Itens Incluídos (Diário)": itens_incluidos_dia if dia <= hoje else None,
                    "Itens Concluídos (Diário)": concluidos_hoje if dia <= hoje else None
                })

            df_burndown = pd.DataFrame(bd_dados)
            df_burndown['Média Entrega Diária'] = pd.to_numeric(df_burndown['Média Entrega Diária'], errors='coerce')
            df_burndown['Média por Sprint'] = pd.to_numeric(df_burndown['Média por Sprint'], errors='coerce')

            # ========================================================
            # MONTAGEM DO GRÁFICO (Limpo, sem picos)
            # ========================================================
            legenda_itens = [
                '<div><b style="color: gray;">- - -</b> Diretriz Ideal</div>',
                '<div><b style="color: #4CA6FF;">━●━</b> Trabalho Restante</div>',
                '<div><b style="color: #28A745;">━●━</b> Concluídos Acumulados</div>',
            ]
            if show_media_entrega:
                legenda_itens.append('<div><b style="color: #FF9F43;">- - -</b> Média Entrega Diária</div>')
            if show_media_sprint:
                legenda_itens.append('<div><b style="color: #8E44AD;">- - -</b> Média por Sprint</div>')
            if show_incluidos_diario:
                legenda_itens.append('<div><b style="color: #9B59B6;">▮</b> Itens Incluídos (Diário)</div>')
            if show_concluidos_diario:
                legenda_itens.append('<div><b style="color: #82E0AA;">▮</b> Itens Concluídos (Diário)</div>')

            st.markdown(
                '<div style="display:flex;flex-wrap:wrap;justify-content:center;gap:20px;font-size:14px;margin-bottom:15px;">'
                + "".join(legenda_itens)
                + '</div>',
                unsafe_allow_html=True
            )

            # O domínio do eixo X precisa ser FIXO e explícito. Com sort=None cada camada declarava a
            # ordem do seu próprio recorte (cada uma com dropna diferente) e o Vega unia os domínios
            # camada a camada -> os dias saíam embaralhados (11/08, 13/08, 14/08, 17/08, 10/08...).
            ordem_datas = df_burndown['Data'].tolist()
            eixo_x = alt.X(
                'Data:O', sort=ordem_datas, title="Dias da Sprint",
                scale=alt.Scale(domain=ordem_datas)
            )
            eixo_y = alt.Y('Valor:Q', title="Quantidade de Itens")
            # Eixo secundário (direita), só pras barras DIÁRIAS: o volume diário (poucos itens/dia)
            # ficaria imperceptível na mesma escala do acumulado (que passa de 140+). O "Incluídos
            # (Acumulado)" fica no eixo primário porque é comparável em ordem de grandeza ao restante/diretriz.
            # Teto folgado no eixo direito: sem isso a maior barra do dia encosta no topo do gráfico
            # e as linhas (que são a informação principal do burndown) ficam soterradas. Com ~2.4x
            # o pico diário as barras ocupam no máximo ~40% da altura e viram pano de fundo.
            _max_diario = pd.concat([
                pd.to_numeric(df_burndown['Itens Incluídos (Diário)'], errors='coerce'),
                pd.to_numeric(df_burndown['Itens Concluídos (Diário)'], errors='coerce'),
            ]).max()
            _teto_direita = max(1.0, float(_max_diario) * 2.4) if pd.notna(_max_diario) else 1.0
            eixo_y_direita = alt.Y(
                'Valor:Q', title="Itens no Dia",
                scale=alt.Scale(domain=[0, _teto_direita], nice=False),
                axis=alt.Axis(orient='right', grid=False)
            )

            def _make_serie(df_base, coluna, cor, stroke_dash, point, stroke_width):
                df_serie = (
                    df_base[['Data', coluna]]
                    .rename(columns={coluna: 'Valor'})
                    .dropna(subset=['Valor'])
                    .copy()
                )
                df_serie['Valor'] = pd.to_numeric(df_serie['Valor'], errors='coerce')
                df_serie = df_serie.dropna(subset=['Valor'])
                if df_serie.empty:
                    return None
                
                mark_kwargs = dict(color=cor, strokeWidth=stroke_width)
                if stroke_dash:
                    mark_kwargs['strokeDash'] = stroke_dash
                if point:
                    mark_kwargs['point'] = True
                    
                return (
                    alt.Chart(df_serie)
                    .mark_line(**mark_kwargs)
                    .encode(
                        x=eixo_x,
                        y=eixo_y,
                        tooltip=[
                            alt.Tooltip('Data:O', title='Data'),
                            alt.Tooltip('Valor:Q', title=coluna, format='.1f'),
                        ]
                    )
                )

            def _make_bars_diarias(df_base, series):
                """Barras diárias agrupadas (lado a lado) + rótulo com a quantidade do dia.

                Sobrepostas na mesma posição X, incluídos e concluídos se mascaravam (a cor da
                frente virava uma mistura e não dava pra ler nenhum dos dois). xOffset separa as
                barras dentro do mesmo dia; o rótulo dispensa a leitura pelo eixo.
                """
                frames = []
                for coluna, cor in series:
                    d = df_base[['Data', coluna]].rename(columns={coluna: 'Valor'}).copy()
                    d['Valor'] = pd.to_numeric(d['Valor'], errors='coerce')
                    d = d.dropna(subset=['Valor'])
                    if d.empty:
                        continue
                    d['Série'] = coluna
                    frames.append(d)
                if not frames:
                    return None

                df_bars = pd.concat(frames, ignore_index=True)
                dominio = [coluna for coluna, _ in series]
                faixa = [cor for _, cor in series]
                escala_cor = alt.Color(
                    'Série:N', scale=alt.Scale(domain=dominio, range=faixa), legend=None
                )
                offset = alt.XOffset('Série:N', scale=alt.Scale(domain=dominio))

                base = alt.Chart(df_bars).encode(
                    x=eixo_x,
                    y=eixo_y_direita,
                    xOffset=offset,
                    tooltip=[
                        alt.Tooltip('Data:O', title='Data'),
                        alt.Tooltip('Série:N', title='Série'),
                        alt.Tooltip('Valor:Q', title='Qtd no dia', format='.0f'),
                    ]
                )
                barras = base.mark_bar(opacity=0.55)
                # Dia com 0 não ganha rótulo, senão a faixa do eixo vira uma fileira de zeros.
                rotulos = base.transform_filter(alt.datum.Valor > 0).mark_text(
                    dy=-6, fontSize=11, fontWeight='bold'
                ).encode(text=alt.Text('Valor:Q', format='.0f'), color=escala_cor)

                return alt.layer(barras.encode(color=escala_cor), rotulos)

            camadas = []

            for coluna, cor, dash, pt, sw in [
                ('Diretriz',              'gray',    [5, 5], False, 2),
                ('Trabalho Restante',     '#4CA6FF', [],     True,  3),
                ('Concluídos Acumulados', '#28A745', [],     True,  3),
            ]:
                c = _make_serie(df_burndown, coluna, cor, dash if dash else None, pt, sw)
                if c is not None:
                    camadas.append(c)

            if show_media_entrega:
                c = _make_serie(df_burndown, 'Média Entrega Diária', '#FF9F43', [2, 2], False, 3)
                if c is not None: camadas.append(c)

            if show_media_sprint:
                c = _make_serie(df_burndown, 'Média por Sprint', '#8E44AD', [4, 2], False, 3)
                if c is not None: camadas.append(c)

            # Barras diárias (eixo secundário/direita) — uma única camada agrupada, resolvida
            # com escala Y independente.
            series_diarias = []
            if show_incluidos_diario:
                series_diarias.append(('Itens Incluídos (Diário)', '#9B59B6'))
            if show_concluidos_diario:
                series_diarias.append(('Itens Concluídos (Diário)', '#82E0AA'))

            grafico_secundario = _make_bars_diarias(df_burndown, series_diarias) if series_diarias else None

            if camadas or grafico_secundario is not None:
                grafico_primario = alt.layer(*camadas).resolve_scale(y='shared') if camadas else None
                if grafico_secundario is not None:
                    # Barras diárias primeiro (ficam atrás), linhas por cima -> resolve_scale independente
                    # é o que cria o eixo Y da direita de verdade.
                    if grafico_primario is not None:
                        grafico_burndown = alt.layer(grafico_secundario, grafico_primario).resolve_scale(y='independent').properties(height=420)
                    else:
                        grafico_burndown = grafico_secundario.properties(height=420)
                else:
                    grafico_burndown = grafico_primario.properties(height=420)
                st.altair_chart(grafico_burndown, use_container_width=True, theme="streamlit")
            else:
                st.info("Sem dados suficientes para renderizar o gráfico de Burndown.")
            
            # Ciclo total: resumo, dev e pontos vêm de DETAILS/BACKLOG pela chave.
            df_itens_entregues = df_filtrado_ativo
            if ciclo_total:
                # (com filtro de pessoa o responsável já veio do merge acima; tira para não duplicar a coluna)
                df_itens_entregues = df_concluidos_bd.drop(columns=['responsavel'], errors='ignore').copy()
                if not df_itens_entregues.empty:
                    _info_itens = (
                        pd.concat([df_backlog, df_issues], ignore_index=True)[['issue_key', 'resumo', 'responsavel', 'pontos']]
                        .drop_duplicates(subset=['issue_key'], keep='last')
                    )
                    df_itens_entregues = df_itens_entregues.merge(_info_itens, on='issue_key', how='left')
                    df_itens_entregues['pontos'] = pd.to_numeric(df_itens_entregues['pontos'], errors='coerce')
                    df_itens_entregues['resumo'] = df_itens_entregues['resumo'].fillna("—")
                    df_itens_entregues['responsavel'] = df_itens_entregues['responsavel'].fillna("—")

            if quarentena_itens:
                # Fila real: quem foi para 5.1.1 Em quarentena também conta como concluído no dia.
                _info_q = (pd.concat([df_backlog, df_issues], ignore_index=True)[['issue_key', 'resumo', 'responsavel', 'pontos']]
                           .drop_duplicates(subset=['issue_key'], keep='last'))
                df_q = pd.DataFrame({'issue_key': [k for _, k in quarentena_itens],
                                     'data_conclusao': [pd.Timestamp(d) for d, _ in quarentena_itens]}).merge(_info_q, on='issue_key', how='left')
                df_q['resumo'] = "[Quarentena] " + df_q['resumo'].fillna("—").astype(str)
                df_q['responsavel'] = df_q['responsavel'].fillna("—")
                df_q['pontos'] = pd.to_numeric(df_q['pontos'], errors='coerce')
                df_itens_entregues = pd.concat([df_itens_entregues, df_q], ignore_index=True)

            # with st.expander("Itens entregues por dia", expanded=False):
            #     if ciclo_total:
            #         st.caption("Ciclo total: data de entrada em 6.0 Concluído.")
            #     if quarentena_itens:
            #         st.caption("Itens marcados [Quarentena]: foram para 5.1.1 Em quarentena, que conta como concluído.")
            #     if not df_itens_entregues.empty:
            #         df_auditoria = df_itens_entregues.copy()
            #         df_auditoria['Data da Entrega'] = pd.to_datetime(df_auditoria['data_conclusao']).dt.strftime('%d/%m/%Y')
            #         df_auditoria = df_auditoria.sort_values('data_conclusao')
            #         df_auditoria['link'] = "https://ddsinfo.atlassian.net/browse/" + df_auditoria['issue_key']
            #         dias_com_entrega = ["Todos os Dias"] + df_auditoria['Data da Entrega'].unique().tolist()
            #         dia_selecionado = st.selectbox("Filtrar por dia específico:", dias_com_entrega)
            #         if dia_selecionado != "Todos os Dias": df_auditoria = df_auditoria[df_auditoria['Data da Entrega'] == dia_selecionado]
            #         st.dataframe(
            #             df_auditoria[['Data da Entrega', 'issue_key', 'resumo', 'responsavel', 'pontos', 'link']],
            #             use_container_width=True, hide_index=True,
            #             column_config={"Data da Entrega": "Data de Conclusão", "issue_key": "Chave", "resumo": st.column_config.TextColumn("Resumo", width="large"), "responsavel": "Dev", "pontos": st.column_config.NumberColumn("Pontos", format="%d"), "link": st.column_config.LinkColumn("Jira")}
            #         )
            #     else: st.info(f"Nenhum item de {visao_burndown} foi concluído nesta sprint ainda.")

            # Entradas e saídas da fila por dia (os mesmos itens das barras "Incluídos"), com o motivo.
            if usar_fila_real:
                with st.expander("Entradas e saídas da fila por dia", expanded=False):
                    fim_ciclo_txt = "6.0 Concluído" if ciclo_total else "3.3 ou além"
                    st.caption(
                        "Entrada = o item passou a fazer parte da fila da sprint naquele dia (colocado na sprint, "
                        "reprovado, reaberto, saiu de pendência...). Saída = deixou a fila (foi para "
                        f"{fim_ciclo_txt}, tirado da sprint, dispensado...). Comparação entre o fim do dia anterior "
                        "e o fim do dia."
                    )
                    _info_fila = (pd.concat([df_backlog, df_issues], ignore_index=True)[['issue_key', 'resumo']]
                                  .drop_duplicates(subset=['issue_key'], keep='last'))
                    _resumo_fila = dict(zip(_info_fila['issue_key'], _info_fila['resumo']))
                    _estados_por_item = {k: g for k, g in df_fila_sp.groupby('issue_key')}

                    def _estado_item(chave, t):
                        g = _estados_por_item.get(chave)
                        if g is None:
                            return None
                        linha = g[(g['valido_de'] <= t) & (g['valido_ate'].isna() | (g['valido_ate'] > t))]
                        return None if linha.empty else linha.iloc[0]

                    def _na_sprint(e):
                        return e is not None and (e['em_sprint_ativa'] == 1 or
                                                  (escopo_burndown != "Sprint Atual" and e['em_backlog2'] == 1))

                    def _motivo(a, b, entrou):
                        if entrou:
                            if a is None: return "Criado / passou a ser acompanhado"
                            if not _na_sprint(a) and _na_sprint(b):
                                return "Puxado do Backlog 2" if a['em_backlog2'] == 1 else "Colocado na sprint"
                            if a['status'] != b['status']: return f"Voltou para a fila: {a['status']} → {b['status']}"
                            if a['responsavel'] != b['responsavel']: return f"Atribuído (antes: {a['responsavel']})"
                            if a['tipo_item'] != b['tipo_item']: return f"Tipo: {a['tipo_item']} → {b['tipo_item']}"
                            return "Entrou na fila"
                        if b is None: return "Saiu do acompanhamento"
                        if _na_sprint(a) and not _na_sprint(b):
                            return "Movido para o Backlog 2" if b['em_backlog2'] == 1 else "Tirado da sprint"
                        if a['status'] != b['status']: return f"{a['status']} → {b['status']}"
                        if a['responsavel'] != b['responsavel']: return f"Reatribuído para {b['responsavel']}"
                        if a['tipo_item'] != b['tipo_item']: return f"Tipo: {a['tipo_item']} → {b['tipo_item']}"
                        return "Saiu da fila"

                    movimentos = []
                    for o in sorted(entradas_fila_dia):
                        dia_o = data_ini + timedelta(days=o)
                        t_ant = pd.Timestamp(data_ini) if o == 0 else pd.Timestamp(dia_o) - pd.Timedelta(seconds=1)
                        t_dep = min(pd.Timestamp(dia_o) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1), agora_local)
                        for chave, entrou in [(k, True) for k in entradas_fila_dia[o]] + [(k, False) for k in saidas_fila_dia[o]]:
                            a, b = _estado_item(chave, t_ant), _estado_item(chave, t_dep)
                            ref = b if entrou else a  # tipo/responsável/status de quando estava na fila
                            movimentos.append({
                                'Dia': dia_o.strftime('%d/%m'), '_ordem': o,
                                'Movimento': 'Entrada' if entrou else 'Saída', 'issue_key': chave,
                                'resumo': _resumo_fila.get(chave, "—"),
                                'tipo_item': ref['tipo_item'] if ref is not None else "",
                                'responsavel': ref['responsavel'] if ref is not None else "",
                                'Motivo': _motivo(a, b, entrou),
                            })
                    df_mov = pd.DataFrame(movimentos)

                    if df_mov.empty:
                        st.info("Nenhuma entrada ou saída na fila neste recorte.")
                    else:
                        ent = df_mov[df_mov['Movimento'] == 'Entrada']
                        k1, k2, k3, k4 = st.columns(4)
                        k1.metric("Fila no início", len(_fila_em(fila_recorte, pd.Timestamp(data_ini))))
                        k2.metric("Entradas na sprint", len(ent))
                        k3.metric("Saídas na sprint", int((df_mov['Movimento'] == 'Saída').sum()))
                        if not ent.empty:
                            pico_f = ent.groupby('Dia').size().sort_values(ascending=False)
                            k4.metric("Dia de maior entrada", pico_f.index[0], delta=f"{int(pico_f.iloc[0])} itens")

                        cf1, cf2 = st.columns([1, 2])
                        tipo_mov = cf1.radio("Mostrar:", ["Entradas", "Saídas", "Entradas e saídas"],
                                             horizontal=True, key="radio_mov_fila")
                        filtro_mov = {"Entradas": ["Entrada"], "Saídas": ["Saída"]}.get(tipo_mov, ["Entrada", "Saída"])
                        df_ver = df_mov[df_mov['Movimento'].isin(filtro_mov)]
                        qtd_dia_mov = df_ver.groupby('Dia').size().to_dict()
                        dias_mov = df_ver.sort_values('_ordem')['Dia'].unique().tolist()
                        dia_mov = cf2.selectbox(
                            "Dia:", ["Todos os dias"] + dias_mov, key="select_dia_fila",
                            format_func=lambda d: d if d == "Todos os dias" else f"{d} ({int(qtd_dia_mov[d])} itens)"
                        )
                        if dia_mov != "Todos os dias":
                            df_ver = df_ver[df_ver['Dia'] == dia_mov]
                        df_ver = df_ver.sort_values(['_ordem', 'Movimento', 'issue_key']).copy()
                        df_ver['link'] = "https://ddsinfo.atlassian.net/browse/" + df_ver['issue_key'].astype(str)
                        st.dataframe(
                            df_ver[['Dia', 'Movimento', 'issue_key', 'resumo', 'tipo_item', 'responsavel', 'Motivo', 'link']],
                            use_container_width=True, hide_index=True,
                            column_config={
                                'Dia': st.column_config.TextColumn('Dia', width='small'),
                                'issue_key': 'Chave',
                                'resumo': st.column_config.TextColumn('Resumo', width='large'),
                                'tipo_item': 'Tipo',
                                'responsavel': 'Responsável',
                                'Motivo': st.column_config.TextColumn('Motivo', width='medium'),
                                'link': st.column_config.LinkColumn('Jira'),
                            }
                        )

            # ========================================================
            # CHEGADA DE ITENS POR DIA (por que a curva não desce)
            # ========================================================
            # As barras "Incluídos Diários" dizem QUANTO entrou, mas são derivadas do delta do
            # Trabalho Restante -- não sabem QUAIS itens entraram. Aqui a leitura é direta:
            # agrupa pelo campo data_criacao dos itens que estão no escopo da sprint.
            # Sem a fila real: cálculo anterior, pela data de criação dos itens.
            if not usar_fila_real:
                with st.expander("Chegada de itens por dia", expanded=False):
                    _partes_escopo = [
                        d for d in (df_backlog_ativo, df_filtrado_ativo)
                        if d is not None and not d.empty and 'data_criacao' in d.columns
                    ]

                    if not _partes_escopo:
                        st.info("Sem data de criação registrada nos itens desta visão.")
                    else:
                        df_chegada = pd.concat(_partes_escopo, ignore_index=True)
                        # Item pode aparecer nas duas metades (pendente e entregue) em recargas
                        # parciais; sem isso o mesmo ticket contaria duas vezes no dia.
                        if 'issue_key' in df_chegada.columns:
                            df_chegada = df_chegada.drop_duplicates(subset=['issue_key'])

                        df_chegada['_criacao'] = pd.to_datetime(df_chegada['data_criacao'], errors='coerce')
                        df_chegada = df_chegada.dropna(subset=['_criacao'])
                        df_chegada['_criacao'] = df_chegada['_criacao'].dt.date

                        _ini_ch, _fim_ch = data_ini, data_fim
                        dentro_janela = (df_chegada['_criacao'] >= _ini_ch) & (df_chegada['_criacao'] <= _fim_ch)
                        df_novos = df_chegada[dentro_janela].copy()
                        qtd_herdados = int((~dentro_janela).sum())

                        if df_novos.empty:
                            st.info(
                                f"Nenhum item criado dentro da sprint nesta visão. "
                                f"Os {qtd_herdados} itens do escopo são anteriores ao início."
                            )
                        else:
                            df_por_dia = (
                                df_novos.groupby('_criacao')
                                .agg(Itens=('issue_key', 'count'))
                                .reset_index()
                                .rename(columns={'_criacao': 'Data'})
                                .sort_values('Data')
                            )
                            df_por_dia['Dia'] = pd.to_datetime(df_por_dia['Data']).dt.strftime('%d/%m')
                            pico = df_por_dia.loc[df_por_dia['Itens'].idxmax()]
                            media_dia = df_por_dia['Itens'].mean()

                            k1, k2, k3, k4 = st.columns(4)
                            k1.metric("Itens Criados na Sprint", int(df_por_dia['Itens'].sum()))
                            k2.metric("Dia de Maior Entrada", f"{pico['Dia']}", delta=f"{int(pico['Itens'])} itens")
                            k3.metric("Média por Dia de Entrada", f"{media_dia:.1f}")
                            k4.metric("Herdados (criados antes)", qtd_herdados)

                            st.divider()

                            st.write("**Quais itens chegaram**")
                            # Opções ordenadas do dia que mais recebeu para o que menos recebeu, com a
                            # contagem no rótulo -- é o que restou do ranking depois de tirar a tabela.
                            df_rank_dias = df_por_dia.sort_values('Itens', ascending=False)
                            # Opção = só o dia (contagem no texto), para a seleção não se perder ao trocar filtros.
                            qtd_por_dia = dict(zip(df_rank_dias['Dia'], df_rank_dias['Itens']))
                            opcoes_dias = ["Todos os dias"] + df_rank_dias['Dia'].tolist()
                            dia_escolhido = st.selectbox(
                                "Dia de criação:", opcoes_dias, key="select_dia_chegada",
                                format_func=lambda d: d if d == "Todos os dias" else f"{d} ({int(qtd_por_dia[d])} itens)"
                            )

                            df_detalhe_ch = df_novos.copy()
                            df_detalhe_ch['Dia'] = pd.to_datetime(df_detalhe_ch['_criacao']).dt.strftime('%d/%m')
                            if dia_escolhido != "Todos os dias":
                                df_detalhe_ch = df_detalhe_ch[df_detalhe_ch['Dia'] == dia_escolhido]

                            for _col_opc in ('cliente', 'tipo_item', 'status', 'responsavel', 'pontos'):
                                if _col_opc not in df_detalhe_ch.columns:
                                    df_detalhe_ch[_col_opc] = ""

                            df_detalhe_ch['link'] = "https://ddsinfo.atlassian.net/browse/" + df_detalhe_ch['issue_key'].astype(str)
                            df_detalhe_ch = df_detalhe_ch.sort_values(['_criacao', 'issue_key'])

                            st.dataframe(
                                df_detalhe_ch[['Dia', 'issue_key', 'resumo', 'cliente', 'tipo_item', 'status', 'responsavel', 'pontos', 'link']],
                                use_container_width=True, hide_index=True,
                                column_config={
                                    'Dia': st.column_config.TextColumn('Criado em', width='small'),
                                    'issue_key': 'Chave',
                                    'resumo': st.column_config.TextColumn('Resumo', width='large'),
                                    'cliente': 'Cliente',
                                    'tipo_item': 'Tipo',
                                    'status': 'Status',
                                    'responsavel': 'Responsável',
                                    'pontos': st.column_config.NumberColumn('Pontos', format="%.1f"),
                                    'link': st.column_config.LinkColumn('Jira'),
                                }
                            )

        else: st.info("Sem dados suficientes para gerar o Burndown.")
        st.divider()


        # Antes fazia uma query nova por linha, com f-string interpolada direto no SQL
        # (mesmo padrão de injeção que corrigimos antes) e sem usar o campo certo.
        # Agora usa o "Dev Inicial" (campo do Jira, já carregado em df_issues/df_backlog)
        # em vez do RESPONSAVEL atual, e não bate mais no banco pra cada linha.
        _mapa_dev_inicial = {}
        for _df_origem in (df_issues, df_backlog):
            if _df_origem is not None and not _df_origem.empty and 'dev_inicial' in _df_origem.columns:
                for _key, _dev in zip(_df_origem['issue_key'], _df_origem['dev_inicial']):
                    if pd.notnull(_dev) and str(_dev).strip():
                        _mapa_dev_inicial[_key] = str(_dev).strip()

        def buscar_autor_original(issue_key):
            # Campo vazio no Jira (ou item pai não sincronizado) -> fica em branco, não "Não rastreado".
            return _mapa_dev_inicial.get(issue_key, "")

        def extrair_pai_prioritario(resumo):
            todos_codigos = re.findall(r'([A-Za-z]+-\d+)', str(resumo))
            if not todos_codigos: return "Sem Pai"
            for cod in todos_codigos:
                if cod.upper().startswith('STAR'): return cod.upper()
            for cod in todos_codigos:
                if cod.upper().startswith('RC'): return cod.upper()
            return todos_codigos[0].upper()

        st.subheader("Gestão de RN's e Qualidade")

        df_issues_all = df_issues[df_issues['sprint_id'] == id_sprint_selecionada].copy()
        df_backlog_all = df_backlog[df_backlog['sprint_id'] == id_sprint_selecionada].copy()
        
        df_todas_issues = pd.concat([df_issues_all, df_backlog_all], ignore_index=True)

        df_rns = pd.DataFrame()

        # Janela da sprint: o vínculo por sprint_id sozinho traz RN arrastado de sprints anteriores
        # (item que continua no board). Aqui só interessa o RN *gerado* dentro do intervalo da sprint.
        _linha_sprint_rn = df_sprints[df_sprints['nome_exibicao'] == sprint_selecionada]
        rn_dt_ini = rn_dt_fim = None
        if not _linha_sprint_rn.empty:
            _ini = _linha_sprint_rn['data_inicio'].iloc[0]
            _fim = _linha_sprint_rn['data_fim'].iloc[0]
            rn_dt_ini = pd.to_datetime(_ini, errors='coerce')
            rn_dt_fim = pd.to_datetime(_fim, errors='coerce')
            if pd.isna(rn_dt_ini) or pd.isna(rn_dt_fim):
                rn_dt_ini = rn_dt_fim = None

        def _filtrar_criados_na_sprint(df):
            # Sem coluna de criação ou sem datas da sprint -> devolve como está, em vez de zerar o painel.
            if df.empty or 'data_criacao' not in df.columns or rn_dt_ini is None:
                return df
            criacao = pd.to_datetime(df['data_criacao'], errors='coerce')
            # data_criacao ausente/inválida não é descartada silenciosamente: some do recorte só se
            # houver data válida fora da janela.
            dentro = criacao.isna() | ((criacao >= rn_dt_ini) & (criacao <= rn_dt_fim))
            return df[dentro].copy()

        QTD_SPRINTS_TENDENCIA_RN = 5

        def _apurar_rn_sprint(sp_id, dt_ini, dt_fim):
            # Densidade de RN = RNs criados na sprint / customizações concluídas na sprint.
            # Numerador com todos os RNs: a origem (tipo do item pai) só é conhecida em parte deles.
            iss_sp = df_issues[df_issues['sprint_id'] == sp_id]
            tod_sp = pd.concat([iss_sp, df_backlog[df_backlog['sprint_id'] == sp_id]], ignore_index=True)
            if tod_sp.empty:
                return 0, 0
            tipo_tod = tod_sp['tipo_item'].astype(str).str.lower().str.strip()
            rns_sp = tod_sp[tipo_tod.str.contains('retorno negativo', na=False)]
            if dt_ini is not None and not rns_sp.empty and 'data_criacao' in rns_sp.columns:
                criacao = pd.to_datetime(rns_sp['data_criacao'], errors='coerce')
                rns_sp = rns_sp[criacao.isna() | ((criacao >= dt_ini) & (criacao <= dt_fim))]
            tipo_iss = iss_sp['tipo_item'].astype(str).str.lower().str.strip()
            cust_sp = iss_sp[(iss_sp['status'] == '6.0 Concluído') & tipo_iss.str.startswith('customiza')]
            return len(rns_sp), len(cust_sp)

        if not df_todas_issues.empty:
            df_todas_issues['tipo_norm'] = df_todas_issues['tipo_item'].astype(str).str.lower().str.strip()
            df_rns = df_todas_issues[df_todas_issues['tipo_norm'].str.contains('retorno negativo', na=False)].copy()
            df_rns = _filtrar_criados_na_sprint(df_rns)

            qtd_rns, qtd_cust = _apurar_rn_sprint(id_sprint_selecionada, rn_dt_ini, rn_dt_fim)
            taxa = (qtd_rns / qtd_cust * 100) if qtd_cust > 0 else 0

            # Sprints anteriores (df_sprints vem ordenado por data de início, da mais nova para a mais antiga)
            historico_rn = []
            _idx_sprint_rn = df_sprints.index[df_sprints['id'] == id_sprint_selecionada].tolist()
            if _idx_sprint_rn:
                _pos = df_sprints.index.get_loc(_idx_sprint_rn[0])
                for _, sp_row in df_sprints.iloc[_pos: _pos + 1 + QTD_SPRINTS_TENDENCIA_RN].iterrows():
                    _di = pd.to_datetime(sp_row['data_inicio'], errors='coerce')
                    _df = pd.to_datetime(sp_row['data_fim'], errors='coerce')
                    if pd.isna(_di) or pd.isna(_df):
                        _di = _df = None
                    _r, _c = _apurar_rn_sprint(sp_row['id'], _di, _df)
                    historico_rn.append({
                        'Sprint': sp_row['descricao'], 'inicio': sp_row['data_inicio'],
                        'RNs': _r, 'Customizações': _c,
                        'Densidade': round(_r / _c * 100, 1) if _c > 0 else None,
                        'Atual': sp_row['id'] == id_sprint_selecionada,
                    })
            df_hist_rn = pd.DataFrame(historico_rn)
            df_hist_ant = df_hist_rn[~df_hist_rn['Atual']] if not df_hist_rn.empty else pd.DataFrame()

            taxa_anterior = df_hist_ant['Densidade'].iloc[0] if not df_hist_ant.empty else None
            delta_taxa = f"{taxa - taxa_anterior:+.1f} % vs sprint anterior" if taxa_anterior is not None and pd.notnull(taxa_anterior) else None

            rns_abertos = int((df_rns['status'] != '6.0 Concluído').sum()) if not df_rns.empty else 0

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("RNs Gerados", qtd_rns)
            c2.metric("Customizações Concluídas", qtd_cust)
            c3.metric("Densidade de RN", f"{taxa:.1f}%", delta_taxa, delta_color="inverse",
                      help="RNs gerados na sprint / customizações concluídas (6.0 Concluído) na sprint.")
            c4.metric("RNs em Aberto", rns_abertos,
                      help="RNs da sprint ainda fora do status 6.0 Concluído (retrabalho pendente).")

            with st.expander("Tendência da Densidade de RN", expanded=False):
                df_graf_rn = df_hist_rn.dropna(subset=['Densidade']) if not df_hist_rn.empty else pd.DataFrame()
                if df_graf_rn.empty:
                    st.info("Sem customizações concluídas nas sprints do período para calcular a tendência.")
                else:
                    df_graf_rn = df_graf_rn.sort_values('inicio')
                    ordem_sprints_rn = df_graf_rn['Sprint'].tolist()
                    linha_rn = alt.Chart(df_graf_rn).mark_line(point=True, color='#3CD6E7').encode(
                        x=alt.X('Sprint:N', sort=ordem_sprints_rn, title=''),
                        y=alt.Y('Densidade:Q', title='Densidade de RN (%)',
                                scale=alt.Scale(domain=[0, max(20, float(df_graf_rn['Densidade'].max()) * 1.2)])),
                        tooltip=['Sprint', 'RNs', 'Customizações', alt.Tooltip('Densidade:Q', format='.1f', title='Densidade (%)')]
                    )
                    rotulos_linha_rn = linha_rn.mark_text(dy=-10, color='white').encode(text=alt.Text('Densidade:Q', format='.1f'))
                    st.altair_chart((linha_rn + rotulos_linha_rn).properties(height=300),
                                    use_container_width=True, theme="streamlit")
                    st.caption("Base: somente customizações concluídas. A sprint selecionada ainda pode estar em andamento.")


        if not df_rns.empty:
            st.write("---")

            # ---- Resolução do "Dev Inicial" (a primeira coisa a validar) ----
            # Fonte de verdade: campo "Desenvolvedor original" do Jira (customfield_10594),
            # que a extração grava em dev_inicial. Ele vem no PRÓPRIO RN -- a versão anterior
            # só olhava o dev_inicial do item PAI extraído por regex do resumo, e o pai quase
            # nunca existe na base (é um RC-*, projeto que não é sincronizado), então a coluna
            # aparecia vazia em 100% das linhas mesmo quando o RN tinha o campo preenchido.
            SEM_DEV = "Não informado"

            def _limpar(valor):
                if valor is None or (isinstance(valor, float) and pd.isna(valor)):
                    return ""
                texto = str(valor).strip()
                return "" if texto.lower() in ("none", "nan", "") else texto

            if 'dev_inicial' in df_rns.columns:
                df_rns['dev_inicial_rn'] = df_rns['dev_inicial'].apply(_limpar)
            else:
                df_rns['dev_inicial_rn'] = ""

            df_rns['item_origem'] = df_rns['resumo'].apply(extrair_pai_prioritario)
            df_rns['dev_inicial_pai'] = df_rns['item_origem'].apply(buscar_autor_original).apply(_limpar)

            # Cadeia de resolução, do mais confiável para o menos: campo do próprio RN, depois
            # o do item citado no resumo. Alimenta o agrupamento por "Dev Inicial" do gráfico.
            df_rns['dev_inicial_final'] = [
                do_rn or do_pai or SEM_DEV
                for do_rn, do_pai in zip(df_rns['dev_inicial_rn'], df_rns['dev_inicial_pai'])
            ]

            col_left, col_right = st.columns(2)

            with col_left:
                base_ranking = st.radio(
                    "Agrupar RNs por:",
                    ["Dev Inicial (quem originou)", "Responsável atual (quem trata)"],
                    key="radio_base_rn", horizontal=False
                )
                col_ranking = 'dev_inicial_final' if base_ranking.startswith("Dev Inicial") else 'responsavel'

                df_rank = (
                    df_rns.groupby(col_ranking).size().reset_index(name='Qtd_RNs')
                    .rename(columns={col_ranking: 'Dev'})
                    .sort_values(by='Qtd_RNs', ascending=False)
                )
                altura_rank = max(200, len(df_rank) * 32)
                barras_rn = alt.Chart(df_rank).mark_bar().encode(
                    x=alt.X('Qtd_RNs:Q', title='Qtd de RNs', axis=alt.Axis(tickMinStep=1, grid=False)),
                    y=alt.Y('Dev:N', sort='-x', title=''),
                    # "Não informado" em cinza: é ausência de dado, não um dev com muitos RNs.
                    color=alt.condition(
                        alt.datum.Dev == SEM_DEV, alt.value("#7F8C8D"), alt.value("#3CD6E7")
                    ),
                    tooltip=[alt.Tooltip('Dev:N', title='Dev'), alt.Tooltip('Qtd_RNs:Q', title='RNs')]
                )
                rotulos_rn = barras_rn.mark_text(
                    align='left', baseline='middle', dx=4, color='white'
                ).encode(text=alt.Text('Qtd_RNs:Q', format='.0f'))
                st.altair_chart(
                    (barras_rn + rotulos_rn).properties(height=altura_rank),
                    use_container_width=True, theme="streamlit"
                )

            with col_right:
                st.write("**Status dos RNs**")
                df_status = df_rns.groupby('status').size().reset_index(name='Qtd')
                donut = alt.Chart(df_status).mark_arc(innerRadius=50).encode(
                    theta="Qtd:Q",
                    color=alt.Color("status:N", title="Status"),
                    tooltip=[alt.Tooltip('status:N', title='Status'), alt.Tooltip('Qtd:Q', title='RNs')]
                ).properties(height=240)
                st.altair_chart(donut, use_container_width=True)

            with st.expander("Detalhamento de Raiz", expanded=False):
                df_det = df_rns.copy()

                if df_det.empty:
                    st.info("Nenhum RN nesta sprint.")
                else:
                    # Colunas opcionais: nem todo recorte (details x backlog) traz as mesmas.
                    for _c in ('cliente', 'status', 'data_criacao'):
                        if _c not in df_det.columns:
                            df_det[_c] = ""

                    # data_criacao chega com tipos misturados (datetime.date vindo do banco e str
                    # nas linhas sem valor), e sort_values compara os dois direto -> TypeError.
                    # Converter primeiro e ordenar pela coluna convertida resolve os dois casos:
                    # o que não parseia vira NaT e vai para o fim, em vez de derrubar a página.
                    df_det['_criacao_dt'] = pd.to_datetime(df_det['data_criacao'], errors='coerce')
                    df_det['Criado em'] = df_det['_criacao_dt'].dt.strftime('%d/%m/%Y').fillna("—")
                    df_det['issue_key_url'] = "https://ddsinfo.atlassian.net/browse/" + df_det['issue_key'].astype(str)
                    df_det = df_det.sort_values('_criacao_dt', ascending=False, na_position='last')

                    st.dataframe(
                        df_det[['issue_key_url', 'Criado em', 'responsavel', 'status', 'cliente', 'resumo']],
                        use_container_width=True, hide_index=True,
                        column_config={
                            "issue_key_url": st.column_config.LinkColumn(
                                "Ticket RN", display_text=r"https://ddsinfo\.atlassian\.net/browse/(.*)", width="small"
                            ),
                            "Criado em": st.column_config.TextColumn("Criado em", width="small"),
                            "responsavel": "Responsável",
                            "status": "Status",
                            "cliente": "Cliente",
                            "resumo": st.column_config.TextColumn("Resumo", width="large"),
                        }
                    )
        else:
            st.success("Nenhum RN na sprint atual. Fluxo limpo!")
        st.divider()

        st.subheader("Itens por Cliente (Planning)")

        if not df_backlog_filtrado.empty:
            
            if 'data_criacao' not in df_backlog_filtrado.columns:
                df_backlog_filtrado['data_criacao'] = "2000-01-01"

            data_inicio_sprint = df_sprints[df_sprints['nome_exibicao'] == sprint_selecionada]['data_inicio'].iloc[0]

            # Comparava data_criacao (que vem como datetime.date do banco em parte das linhas e
            # como str em outras) direto contra uma string -> TypeError assim que caísse uma date.
            # Converter os dois lados torna a comparação independente do tipo que o driver devolveu.
            _ini_clientes = pd.to_datetime(data_inicio_sprint, errors='coerce')
            _criacao_clientes = pd.to_datetime(df_backlog_filtrado['data_criacao'], errors='coerce')
            if pd.isna(_ini_clientes):
                df_clientes_sprint = df_backlog_filtrado.copy()
            else:
                df_clientes_sprint = df_backlog_filtrado[_criacao_clientes >= _ini_clientes].copy()

            col_cli1, col_cli2 = st.columns([2, 3])

            with col_cli1:
                st.write("**Resumo de Carga por Cliente**")
                
                if not df_clientes_sprint.empty:
                    df_clientes = df_clientes_sprint.groupby('cliente')['issue_key'].count().reset_index()
                    df_clientes.columns = ['Cliente', 'Contagem']
                    df_clientes = df_clientes.sort_values(by='Contagem', ascending=False)
                    
                    total_cli = df_clientes['Contagem'].sum()
                    if total_cli > 0:
                        df_clientes['Porcentagem'] = (df_clientes['Contagem'] / total_cli) * 100
                    else:
                        df_clientes['Porcentagem'] = 0
                    
                    st.dataframe(
                        df_clientes,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Cliente": st.column_config.TextColumn("Cliente", width="medium"),
                            "Contagem": st.column_config.NumberColumn("Qtd", width="small"),
                            "Porcentagem": st.column_config.ProgressColumn(
                                "%",
                                format="%d%%",
                                min_value=0,
                                max_value=100,
                            ),
                        }
                    )
                else:
                    st.info("Nenhum item novo criado para esta sprint até o momento.")
                    df_clientes = pd.DataFrame(columns=['Cliente']) 

            with col_cli2:
                    st.write("**Detalhamento de Tickets**")
                    
                    if not df_clientes_sprint.empty:
                        lista_clientes = ["Todos"] + df_clientes['Cliente'].tolist()
                        cliente_selecionado = st.selectbox("Selecione o Cliente para detalhar:", lista_clientes)

                        if cliente_selecionado != "Todos":
                            df_detalhe_cliente = df_clientes_sprint[df_clientes_sprint['cliente'] == cliente_selecionado].copy()
                        else:
                            df_detalhe_cliente = df_clientes_sprint.copy()

                        df_detalhe_cliente['link'] = "https://ddsinfo.atlassian.net/browse/" + df_detalhe_cliente['issue_key']
                    else:
                        # Sem item criado na sprint não há o que detalhar.
                        df_detalhe_cliente = pd.DataFrame(columns=['issue_key', 'sistema', 'resumo', 'status', 'tipo_item', 'responsavel'])

                    df_detalhe_cliente.columns = df_detalhe_cliente.columns.str.lower()
                    if 'status' not in df_detalhe_cliente.columns:
                        df_detalhe_cliente['status'] = 'aguardando sincronizacao'

                    df_detalhe_cliente['link'] = "https://ddsinfo.atlassian.net/browse/" + df_detalhe_cliente['issue_key']

                    st.dataframe(
                        df_detalhe_cliente[['issue_key', 'sistema', 'resumo', 'status', 'tipo_item', 'responsavel', 'link']], 
                        use_container_width=True, hide_index=True,
                        column_config={
                            "issue_key": "Chave",
                            "sistema": "Sistema",
                            "resumo": st.column_config.TextColumn("Resumo", width="large"),
                            "status": "Status",
                            "tipo_item": "Tipo", 
                            "responsavel": "Responsável", 
                            "link": st.column_config.LinkColumn("Jira")
                        }
                    )


            # ========================================================
            # NOVO PAINEL: ALERTAS DE PRAZO (DATA LIMITE)
            # ========================================================
            # Alertas de Prazo desativado (pedido da gestão). Mantido comentado caso volte.
            # st.markdown("####  Alertas de Prazo (Data Limite)")
            # df_alertas = df_backlog_filtrado.copy()
            # df_alertas['data_limite'] = pd.to_datetime(df_alertas['data_limite'])
            # hoje_ts = pd.Timestamp(datetime.now().date())

            # def definir_status_prazo(row):
            #     if pd.isnull(row['data_limite']): return "⚪ Sem Prazo"
            #     elif row['data_limite'].date() < hoje_ts.date(): return "🔴 Excedido"
            #     elif (row['data_limite'].date() - hoje_ts.date()).days <= 3: return "🟡 Próximo (Até 3 dias)"
            #     else: return "🟢 No Prazo"

            # df_alertas['Alerta'] = df_alertas.apply(definir_status_prazo, axis=1)
            # df_critico = df_alertas[df_alertas['Alerta'].isin(["🔴 Excedido", "🟡 Próximo (Até 3 dias)"])].copy()

            # if not df_critico.empty:
            #     df_critico['Prazo'] = df_critico['data_limite'].dt.strftime('%d/%m/%Y')
                
            #     df_critico['link'] = "https://ddsinfo.atlassian.net/browse/" + df_critico['issue_key']
                
            #     st.dataframe(
            #         df_critico[['Alerta', 'link', 'cliente', 'resumo', 'responsavel', 'Prazo']],
            #         use_container_width=True, hide_index=True,
            #         column_config={
            #             "Alerta": st.column_config.TextColumn("Status", width="small"),
                        
            #             "link": st.column_config.LinkColumn(
            #                 "Chave", 
            #                 display_text="https://ddsinfo.atlassian.net/browse/(.*)"
            #             ),
                        
            #             "cliente": "Cliente",
            #             "resumo": "Tarefa",
            #             "responsavel": "Responsável",
            #             "Prazo": st.column_config.TextColumn("Data Limite", width="small")
            #         }
            #     )
            # else:
            #     st.success("✅ Nenhum item pendente com prazo excedido ou próximo do limite.")

            st.divider()
            st.subheader(" Itens por Sistema")

            # Mesmo padrão do "Itens por Tipo".
            visao_sistema = st.radio(
                "Visão:", ["Geral", "Sprint de Desenvolvimento", "Sprint Backlog 2"],
                horizontal=True, key="radio_visao_sistema"
            )
            filtro_nativa_sistema = {"Sprint de Desenvolvimento": "SIM", "Sprint Backlog 2": "NAO"}.get(visao_sistema)
            if filtro_nativa_sistema and 'sprint_nativa' in df_backlog_filtrado.columns:
                df_sistemas_sprint = df_backlog_filtrado[df_backlog_filtrado['sprint_nativa'] == filtro_nativa_sistema].copy()
            else:
                df_sistemas_sprint = df_backlog_filtrado.copy()

            # Vazio/None/nan viram "Sem Sistema", o mesmo rótulo que a extração grava.
            def _normalizar_sistema(valor):
                if pd.isna(valor) or str(valor).strip() in ["", "None", "nan", "Não preenchido"]:
                    return "Sem Sistema"
                return str(valor).strip()

            if not df_sistemas_sprint.empty:

                if 'sistema' in df_sistemas_sprint.columns:
                    df_sistemas_sprint['sistema'] = df_sistemas_sprint['sistema'].apply(_normalizar_sistema)

                    df_grafico_sistema = df_sistemas_sprint.groupby('sistema').size().reset_index(name='quantidade')
                    df_grafico_sistema = df_grafico_sistema.sort_values(by='quantidade', ascending=False)
                    # Domínio fixo com todos os sistemas do backlog: cada sistema mantém a mesma cor ao trocar de visão.
                    dominio_cores_sistema = sorted(df_backlog_filtrado['sistema'].apply(_normalizar_sistema).unique().tolist())

                    col_sys1, col_sys2 = st.columns([2, 3])

                    with col_sys1:
                        base_pizza = alt.Chart(df_grafico_sistema).encode(
                            theta=alt.Theta("quantidade:Q", stack=True),
                            color=alt.Color("sistema:N", title="Sistema", scale=alt.Scale(scheme="category20", domain=dominio_cores_sistema)),
                            tooltip=[alt.Tooltip("sistema:N", title="Sistema"), alt.Tooltip("quantidade:Q", title="Itens")]
                        )
                        pizza = base_pizza.mark_arc(outerRadius=120)
                        textos = base_pizza.mark_text(radius=145, size=15, color="white").encode(text="quantidade:Q")
                        
                        st.altair_chart((pizza + textos).properties(height=320), use_container_width=True, theme="streamlit")
                        
                    with col_sys2:
                        st.write("**Detalhamento de Volumes por Sistema**")
                        
                        total_sys = df_grafico_sistema['quantidade'].sum()
                        df_grafico_sistema['porcentagem'] = (df_grafico_sistema['quantidade'] / total_sys) * 100
                        
                        st.dataframe(
                            df_grafico_sistema,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "sistema": "Nome do Sistema",
                                "quantidade": "Qtd de Itens",
                                "porcentagem": st.column_config.ProgressColumn(
                                    "% do Total",
                                    format="%d%%",
                                    min_value=0,
                                    max_value=100,
                                ),
                            }
                        )

                    with st.expander(f"Detalhes dos itens por sistema ({visao_sistema})", expanded=False):
                        opcoes_sistema = ["Todos"] + df_grafico_sistema['sistema'].tolist()
                        sistema_selecionado = st.selectbox("Filtrar por sistema:", opcoes_sistema, key="select_detalhe_sistema")

                        df_detalhe_sistema = df_sistemas_sprint.copy()
                        if sistema_selecionado != "Todos":
                            df_detalhe_sistema = df_detalhe_sistema[df_detalhe_sistema['sistema'] == sistema_selecionado]

                        df_detalhe_sistema['sprint'] = df_detalhe_sistema['sprint_nativa'].map(
                            {"SIM": "Desenvolvimento", "NAO": "Backlog 2"}
                        ) if 'sprint_nativa' in df_detalhe_sistema.columns else ""
                        df_detalhe_sistema['tipo'] = df_detalhe_sistema['tipo_item'].fillna("sem tipo").astype(str).str.strip().str.capitalize()
                        df_detalhe_sistema['link'] = "https://ddsinfo.atlassian.net/browse/" + df_detalhe_sistema['issue_key'].astype(str)
                        df_detalhe_sistema = df_detalhe_sistema.sort_values(['sistema', 'issue_key'])

                        st.caption(f"{len(df_detalhe_sistema)} item(ns)")
                        st.dataframe(
                            df_detalhe_sistema[['issue_key', 'sistema', 'tipo', 'sprint', 'resumo', 'status', 'responsavel', 'cliente', 'link']],
                            use_container_width=True, hide_index=True,
                            column_config={
                                "issue_key": "Chave",
                                "sistema": "Sistema",
                                "tipo": "Tipo",
                                "sprint": "Sprint",
                                "resumo": st.column_config.TextColumn("Resumo", width="large"),
                                "status": "Status",
                                "responsavel": "Responsável",
                                "cliente": "Cliente",
                                "link": st.column_config.LinkColumn("Jira")
                            }
                        )
                else:
                    st.warning("Coluna 'sistema' não disponível para montar o gráfico.")
            else:
                st.info("Nenhum item pendente para esta visão.")

            st.divider()
            st.subheader(" Itens por Tipo")

            # Pendentes da sincronização atual: Geral = SIM+NAO, Desenvolvimento = SIM, Backlog 2 = NAO (1218).
            visao_tipo = st.radio(
                "Visão:", ["Geral", "Sprint de Desenvolvimento", "Sprint Backlog 2"],
                horizontal=True, key="radio_visao_tipo"
            )
            filtro_nativa_tipo = {"Sprint de Desenvolvimento": "SIM", "Sprint Backlog 2": "NAO"}.get(visao_tipo)
            if filtro_nativa_tipo and 'sprint_nativa' in df_backlog_filtrado.columns:
                df_tipos = df_backlog_filtrado[df_backlog_filtrado['sprint_nativa'] == filtro_nativa_tipo].copy()
            else:
                df_tipos = df_backlog_filtrado.copy()

            if df_tipos.empty:
                st.info("Nenhum item pendente para esta visão.")
            else:
                df_tipos['tipo'] = df_tipos['tipo_item'].fillna("sem tipo").astype(str).str.strip().str.lower()

                df_grafico_tipo = df_tipos.groupby('tipo').size().reset_index(name='quantidade')
                df_grafico_tipo = df_grafico_tipo.sort_values(by='quantidade', ascending=False)
                df_grafico_tipo['tipo'] = df_grafico_tipo['tipo'].str.capitalize()
                dominio_cores_tipo = sorted(
                    df_backlog_filtrado['tipo_item'].fillna("sem tipo").astype(str).str.strip().str.lower().str.capitalize().unique().tolist()
                )

                # Customização por prefixo (com ou sem acento).
                df_comparativo_tipo = pd.DataFrame({
                    'Tipo': ['Erro', 'Atendimento', 'Customização', 'Ajuste'],
                    'Quantidade': [
                        int((df_tipos['tipo'] == 'erro').sum()),
                        int((df_tipos['tipo'] == 'atendimento').sum()),
                        int(df_tipos['tipo'].str.startswith('customiza').sum()),
                        int((df_tipos['tipo'] == 'ajuste').sum()),
                    ]
                })

                col_tipo1, col_tipo2 = st.columns(2)

                with col_tipo1:
                    st.write("**Distribuição por Tipo**")
                    base_pizza_tipo = alt.Chart(df_grafico_tipo).encode(
                        theta=alt.Theta("quantidade:Q", stack=True),
                        # Domínio fixo com todos os tipos do backlog: cada tipo mantém a mesma cor ao trocar de visão.
                        color=alt.Color("tipo:N", title="Tipo", scale=alt.Scale(scheme="category20", domain=dominio_cores_tipo)),
                        tooltip=[alt.Tooltip("tipo:N", title="Tipo"), alt.Tooltip("quantidade:Q", title="Itens")]
                    )
                    pizza_tipo = base_pizza_tipo.mark_arc(outerRadius=120)
                    textos_tipo = base_pizza_tipo.mark_text(radius=145, size=15, color="white").encode(text="quantidade:Q")

                    st.altair_chart((pizza_tipo + textos_tipo).properties(height=320), use_container_width=True, theme="streamlit")

                with col_tipo2:
                    st.write("**Erro x Atendimento x Customização x Ajuste**")
                    barras_tipo = alt.Chart(df_comparativo_tipo).mark_bar(color='#4CA6FF').encode(
                        x=alt.X('Quantidade:Q', title='Itens', axis=alt.Axis(grid=False, tickMinStep=1),
                                scale=alt.Scale(domain=[0, max(1, int(df_comparativo_tipo['Quantidade'].max() * 1.15))])),
                        y=alt.Y('Tipo:N', sort=None, title=''),
                        tooltip=['Tipo', 'Quantidade']
                    )
                    rotulos_tipo = barras_tipo.mark_text(
                        align='left', baseline='middle', dx=4, color='white'
                    ).encode(text='Quantidade:Q')

                    st.altair_chart((barras_tipo + rotulos_tipo).properties(height=320), use_container_width=True, theme="streamlit")

                with st.expander(f"Detalhes dos itens por tipo ({visao_tipo})", expanded=False):
                    opcoes_tipo = ["Todos"] + df_grafico_tipo['tipo'].tolist()
                    tipo_selecionado = st.selectbox("Filtrar por tipo:", opcoes_tipo, key="select_detalhe_tipo")

                    df_detalhe_tipo = df_tipos.copy()
                    df_detalhe_tipo['tipo'] = df_detalhe_tipo['tipo'].str.capitalize()
                    if tipo_selecionado != "Todos":
                        df_detalhe_tipo = df_detalhe_tipo[df_detalhe_tipo['tipo'] == tipo_selecionado]

                    df_detalhe_tipo['sprint'] = df_detalhe_tipo['sprint_nativa'].map(
                        {"SIM": "Desenvolvimento", "NAO": "Backlog 2"}
                    ) if 'sprint_nativa' in df_detalhe_tipo.columns else ""
                    df_detalhe_tipo['link'] = "https://ddsinfo.atlassian.net/browse/" + df_detalhe_tipo['issue_key'].astype(str)
                    df_detalhe_tipo = df_detalhe_tipo.sort_values(['tipo', 'issue_key'])

                    st.caption(f"{len(df_detalhe_tipo)} item(ns)")
                    st.dataframe(
                        df_detalhe_tipo[['issue_key', 'tipo', 'sprint', 'resumo', 'status', 'responsavel', 'cliente', 'link']],
                        use_container_width=True, hide_index=True,
                        column_config={
                            "issue_key": "Chave",
                            "tipo": "Tipo",
                            "sprint": "Sprint",
                            "resumo": st.column_config.TextColumn("Resumo", width="large"),
                            "status": "Status",
                            "responsavel": "Responsável",
                            "cliente": "Cliente",
                            "link": st.column_config.LinkColumn("Jira")
                        }
                    )

            st.divider()

        st.subheader("Comparativo de Fluxo (Status)")

        # Fluxo pela fila real: status agora x média por status nos dias úteis da sprint anterior.
        # Sem fila para as duas sprints, usa o cálculo anterior (else).
        STATUS_FORA_FLUXO = {"6.0 concluído", "7.0 dispensado"}
        _sid_fx = pd.to_numeric(df_fila_estado['sprint_id'], errors='coerce') if not df_fila_estado.empty else pd.Series(dtype=float)
        fila_fx_atual = df_fila_estado[_sid_fx == id_sprint_selecionada] if not df_fila_estado.empty else df_fila_estado
        _pos_fx = df_sprints.index[df_sprints['id'] == id_sprint_selecionada].tolist()
        _pos_fx = df_sprints.index.get_loc(_pos_fx[0]) if _pos_fx else None
        linha_ant_fx = df_sprints.iloc[_pos_fx + 1] if _pos_fx is not None and _pos_fx + 1 < len(df_sprints) else None
        fila_fx_ant = (df_fila_estado[_sid_fx == int(linha_ant_fx['id'])]
                       if linha_ant_fx is not None and not df_fila_estado.empty else pd.DataFrame())
        usar_fluxo_fila = not fila_fx_atual.empty and not fila_fx_ant.empty

        if usar_fluxo_fila:
            escopo_fluxo = st.radio("Escopo:", ["Sprint Atual", "Sprint Atual + Backlog 2"],
                                    horizontal=True, key="radio_escopo_fluxo")
            st.caption("**Qtd atual** = itens em cada status na última sincronização. **Média da última sprint** = "
                       "média de itens em cada status no fim de cada dia útil da sprint anterior. "
                       "Fora da conta: 6.0 Concluído, 7.0 Dispensado, Bug e Ajuste.")
            agora_fx = pd.Timestamp.now(tz="America/Sao_Paulo").tz_localize(None)

            def _base_fluxo(df):
                tipo = df['tipo_item'].astype(str).str.lower().str.strip()
                d = df[(tipo != 'bug') & (tipo != 'ajuste') & (df['projeto'].isin(projeto))]
                d = d[d['em_sprint_ativa'] == 1] if escopo_fluxo == "Sprint Atual" else d[(d['em_sprint_ativa'] == 1) | (d['em_backlog2'] == 1)]
                return d[~d['status'].astype(str).str.lower().isin(STATUS_FORA_FLUXO)]

            def _itens_em(d, t):
                return d[(d['valido_de'] <= t) & (d['valido_ate'].isna() | (d['valido_ate'] > t))].drop_duplicates('issue_key')

            def _media_por_status(d, ini, fim):
                """Média de itens por status no fim de cada dia útil entre ini e fim (até agora)."""
                contagens = []
                for k in range((fim - ini).days + 1):
                    dia_k = ini + timedelta(days=k)
                    if dia_k.weekday() >= 5 or pd.Timestamp(dia_k) > agora_fx:
                        continue
                    t = min(pd.Timestamp(dia_k) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1), agora_fx)
                    contagens.append(_itens_em(d, t).groupby('status').size())
                if not contagens:
                    return pd.Series(dtype=float), 0
                return pd.concat(contagens, axis=1).fillna(0).mean(axis=1), len(contagens)

            def _datas(linha):
                return pd.to_datetime(linha['data_inicio']).date(), pd.to_datetime(linha['data_fim']).date()

            ini_at, fim_at = _datas(df_sprints.iloc[_pos_fx])
            ini_an, fim_an = _datas(linha_ant_fx)
            base_at, base_an = _base_fluxo(fila_fx_atual), _base_fluxo(fila_fx_ant)
            # "Agora" de uma sprint já encerrada = fim dela.
            t_agora = min(agora_fx, pd.Timestamp(fim_at) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))
            itens_agora = _itens_em(base_at, t_agora)
            media_ant, dias_ant = _media_por_status(base_an, ini_an, fim_an)

            df_fluxo = pd.DataFrame({
                'Qtd atual': itens_agora.groupby('status').size(),
                'Média da última sprint': media_ant,
            }).fillna(0)
            df_fluxo.index.name = 'status'
            df_fluxo = df_fluxo.reset_index().sort_values('status')
            df_fluxo['Qtd atual'] = df_fluxo['Qtd atual'].astype(int)
            df_fluxo['Variação'] = df_fluxo['Qtd atual'] - df_fluxo['Média da última sprint']
            nome_ant = str(linha_ant_fx.get('descricao', 'anterior'))

            col_fx1, col_fx2 = st.columns([3, 3])
            with col_fx1:
                st.markdown(f"**Média da última sprint ({nome_ant}, {dias_ant} dias úteis) x Qtd atual**")
                df_melt_fx = (df_fluxo[['status', 'Média da última sprint', 'Qtd atual']]
                              .melt(id_vars='status', var_name='Série', value_name='Qtd'))
                barras_fx = alt.Chart(df_melt_fx).mark_bar(cornerRadiusEnd=2).encode(
                    y=alt.Y('status:N', sort='ascending', title='', axis=alt.Axis(labelLimit=200)),
                    x=alt.X('Qtd:Q', title='Quantidade de Itens', axis=alt.Axis(grid=False)),
                    color=alt.Color('Série:N', scale=alt.Scale(domain=['Média da última sprint', 'Qtd atual'], range=['#FF9F43', '#4CA6FF']),
                                    legend=alt.Legend(orient='bottom', title=None)),
                    yOffset='Série:N',
                    tooltip=['status', 'Série', alt.Tooltip('Qtd:Q', format='.1f')]
                ).properties(height=max(320, len(df_fluxo) * 35))
                st.altair_chart(barras_fx, use_container_width=True, theme="streamlit")

            with col_fx2:
                st.markdown("**Tabela de Variação**")
                total_agora = df_fluxo['Qtd atual'].sum()
                df_fluxo['% Atual'] = (df_fluxo['Qtd atual'] / total_agora * 100) if total_agora > 0 else 0

                def _fmt_var(v):
                    if round(v, 1) > 0: return f"🟢 +{v:.1f}"
                    if round(v, 1) < 0: return f"🔴 {v:.1f}"
                    return "⚪ 0"

                df_fluxo['Var.'] = df_fluxo['Variação'].apply(_fmt_var)
                st.dataframe(
                    df_fluxo[['status', 'Média da última sprint', 'Qtd atual', 'Var.', '% Atual']],
                    use_container_width=True, hide_index=True,
                    column_config={
                        "status": st.column_config.TextColumn("Fase (Status)", width="medium"),
                        "Média da última sprint": st.column_config.NumberColumn(f"Média {nome_ant}", format="%.1f", width="small"),
                        "Qtd atual": st.column_config.NumberColumn("Qtd atual", width="small"),
                        "Var.": st.column_config.TextColumn("Variação", width="small"),
                        "% Atual": st.column_config.ProgressColumn("% Atual", format="%d%%", min_value=0, max_value=100),
                    }
                )

            st.divider()
            with st.expander("Detalhes dos Itens Atuais", expanded=False):
                _info_fx = (pd.concat([df_backlog, df_issues], ignore_index=True)[['issue_key', 'resumo']]
                            .drop_duplicates(subset=['issue_key'], keep='last'))
                df_aud_fx = itens_agora[['issue_key', 'status', 'tipo_item', 'responsavel']].merge(_info_fx, on='issue_key', how='left')
                df_aud_fx['resumo'] = df_aud_fx['resumo'].fillna("—")
                df_aud_fx['link'] = "https://ddsinfo.atlassian.net/browse/" + df_aud_fx['issue_key'].astype(str)
                status_fx = st.selectbox("Filtrar lista por Status:", ["Todos"] + sorted(df_aud_fx['status'].unique().tolist()),
                                         key="select_status_fluxo")
                if status_fx != "Todos":
                    df_aud_fx = df_aud_fx[df_aud_fx['status'] == status_fx]
                st.dataframe(
                    df_aud_fx.sort_values(['status', 'issue_key'])[['issue_key', 'resumo', 'status', 'tipo_item', 'responsavel', 'link']],
                    use_container_width=True, hide_index=True,
                    column_config={
                        "issue_key": "Chave",
                        "resumo": st.column_config.TextColumn("Resumo", width="large"),
                        "status": "Status",
                        "tipo_item": "Tipo",
                        "responsavel": "Responsável",
                        "link": st.column_config.LinkColumn("Jira", display_text="https://ddsinfo.atlassian.net/browse/(.*)"),
                    }
                )
        else:
            st.caption("Sem a fila reconstruída para esta sprint e a anterior: comparativo pelo cálculo anterior "
                       "(backlog atual x backlog final da sprint anterior).")
            st.markdown("<p style='font-size: 0.9em; color: gray; margin-top:-10px;'>🔵 <b>Sprint Atual</b>.</p>", unsafe_allow_html=True)
            st.markdown("<p style='font-size: 0.9em; color: gray; margin-top:-10px;'>🟠 <b>Sprint Anterior</b>.</p>", unsafe_allow_html=True)

            frames_status = []
            if not df_backlog_filtrado.empty: frames_status.append(df_backlog_filtrado)
            if not df_filtrado.empty: frames_status.append(df_filtrado)

            if frames_status:
                df_status_sprint = pd.concat(frames_status, ignore_index=True)
            
                if 'status' in df_status_sprint.columns:
                    df_status_sprint['status'] = df_status_sprint['status'].fillna("Desconhecido")
                    df_status_sprint = df_status_sprint[df_status_sprint['status'] != '6.0 Concluído']
                
                    df_atual = df_status_sprint.groupby('status').size().reset_index(name='Sprint Atual')
                    df_atual = df_atual.sort_values(by='status', ascending=True)

                    df_anterior = pd.DataFrame(columns=['status', 'Sprint Anterior'])
                    try:
                        idx_atual = df_sprints.index[df_sprints['nome_exibicao'] == sprint_selecionada].tolist()[0]
                        if idx_atual + 1 < len(df_sprints):
                            id_sprint_anterior = df_sprints.iloc[idx_atual + 1]['id']
                            query_ant = f"SELECT STATUS FROM TB_SPRINT_BACKLOG WHERE ID_SPRINT = {id_sprint_anterior} AND STATUS != '6.0 Concluído'"
                            df_dados_ant = conn.query(query_ant)
                        
                            if not df_dados_ant.empty:
                                df_dados_ant['STATUS'] = df_dados_ant['STATUS'].fillna("Desconhecido")
                                df_anterior = df_dados_ant.groupby('STATUS').size().reset_index(name='Sprint Anterior')
                                df_anterior.rename(columns={'STATUS': 'status'}, inplace=True)
                    except Exception as e:
                        pass
                
                    df_comparativo = pd.merge(df_atual, df_anterior, on='status', how='outer').fillna(0)
                    df_comparativo['Sprint Atual'] = df_comparativo['Sprint Atual'].astype(int)
                    df_comparativo['Sprint Anterior'] = df_comparativo['Sprint Anterior'].astype(int)
                    df_comparativo['Diferença'] = df_comparativo['Sprint Atual'] - df_comparativo['Sprint Anterior']
                    df_comparativo = df_comparativo.sort_values(by='status', ascending=True)
                
                    col_st1, col_st2 = st.columns([3, 3])
                
                    with col_st1:
                        st.markdown("**Comparativo Visual (Atual vs Anterior)**")
                        df_melted = df_comparativo[['status', 'Sprint Atual', 'Sprint Anterior']].melt(id_vars='status', var_name='Sprint', value_name='Qtd')
                        altura_status = max(320, len(df_comparativo) * 35)

                        barras_status = alt.Chart(df_melted).mark_bar(cornerRadiusEnd=2).encode(
                            y=alt.Y('status:N', sort='ascending', title='', axis=alt.Axis(labelLimit=200)),
                            x=alt.X('Qtd:Q', title='Quantidade de Itens', axis=alt.Axis(grid=False)),
                            color=alt.Color('Sprint:N', scale=alt.Scale(domain=['Sprint Atual', 'Sprint Anterior'], range=['#4CA6FF', '#FF9F43']), legend=alt.Legend(orient='bottom', title=None)),
                            yOffset='Sprint:N',
                            tooltip=['status', 'Sprint', 'Qtd']
                        ).properties(height=altura_status)
                    
                        st.altair_chart(barras_status, use_container_width=True, theme="streamlit")
                    
                    with col_st2:
                        st.markdown("**Tabela de Variação**")
                        st.markdown("<p style='font-size: 0.85em; color: gray; margin-top:-10px;'>Evolução de volume retido em cada fase.</p>", unsafe_allow_html=True)
                    
                        df_tabela = df_comparativo.copy()
                        total_atual = df_tabela['Sprint Atual'].sum()
                        df_tabela['% Atual'] = (df_tabela['Sprint Atual'] / total_atual) * 100 if total_atual > 0 else 0
                    
                        def formatar_delta(valor):
                            if valor > 0:
                                return f"🟢 +{int(valor)}"
                            elif valor < 0:
                                return f"🔴 {int(valor)}"
                            else:
                                return "⚪ 0"
                            
                        df_tabela['Variação'] = df_tabela['Diferença'].apply(formatar_delta)
                    
                        st.dataframe(
                            df_tabela[['status', 'Sprint Anterior', 'Sprint Atual', 'Variação', '% Atual']],
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "status": st.column_config.TextColumn("Fase (Status)", width="medium"),
                                "Sprint Anterior": st.column_config.NumberColumn("Anterior", width="small"),
                                "Sprint Atual": st.column_config.NumberColumn("Atual", width="small"),
                                "Variação": st.column_config.TextColumn("Variação", width="small"),
                                "% Atual": st.column_config.ProgressColumn("% Atual", format="%d%%", min_value=0, max_value=100)
                            }
                        )
                
                    st.divider()
                
                
                    with st.expander("Detalhes dos Itens Atuais", expanded=False):
                        df_auditoria_status = df_status_sprint.copy()
                        df_auditoria_status['link'] = "https://ddsinfo.atlassian.net/browse/" + df_auditoria_status['issue_key']
                    
                        lista_de_status = ["Todos"] + sorted(df_auditoria_status['status'].unique().tolist())
                        status_selecionado = st.selectbox("Filtrar lista por Status:", lista_de_status)
                    
                        if status_selecionado != "Todos":
                            df_auditoria_status = df_auditoria_status[df_auditoria_status['status'] == status_selecionado]
                    
                        st.dataframe(
                            df_auditoria_status[['issue_key', 'resumo', 'status', 'responsavel', 'link']],
                            use_container_width=True, 
                            hide_index=True,
                            column_config={
                                "issue_key": "Chave",
                                "resumo": st.column_config.TextColumn("Resumo", width="large"),
                                "status": "Status no Banco",
                                "responsavel": "Responsável",
                                "link": st.column_config.LinkColumn("Abrir no Jira", display_text="https://ddsinfo.atlassian.net/browse/(.*)")
                            }
                        )
                else:
                    st.warning("A coluna 'status' não está disponível para gerar o gráfico.")
            else:
                st.info("Nenhum dado encontrado para analisar os status.")

                st.divider()
 
        st.subheader(f"Avaliação da {sprint_selecionada.split(' - ')[0]}")
        
        with st.container(border=True):
            lista_colaboradores_fixa = ["Castellar", "Daniel", "Eder", "Fernando", "Sergio", "Vera", "Victor"]
            
            row_sprint_info = df_sprints[df_sprints['id'] == id_sprint_selecionada].iloc[0]
            dt_fim_sprint = row_sprint_info['data_fim']
            if isinstance(dt_fim_sprint, str):
                dt_fim_sprint = datetime.strptime(dt_fim_sprint, "%Y-%m-%d").date()
            
            hoje = datetime.now().date()
            sprint_encerrada = hoje > dt_fim_sprint

            try:
                df_existente = conn.query(f"SELECT NOME_GESTOR, NOTA FROM TB_SPRINT_AVALIACAO WHERE ID_SPRINT = {id_sprint_selecionada}", ttl=0)
            except Exception:
                df_existente = pd.DataFrame(columns=['NOME_GESTOR', 'NOTA'])

            ja_salvo = not df_existente.empty

            if not sprint_encerrada:
                st.info(f"A avaliação ficará disponível para envio após o encerramento da Sprint ({dt_fim_sprint.strftime('%d/%m')}).")
            elif ja_salvo:
                st.warning("Avaliação consolidada. Alterações não são permitidas neste painel.")
            else:
                st.success("Sprint encerrada. Notas prontas para preenchimento e salvamento.")

            df_template = pd.DataFrame({'Colaborador': lista_colaboradores_fixa})
            
            if ja_salvo:
                df_template = df_template.merge(
                    df_existente.rename(columns={'NOME_GESTOR': 'Colaborador', 'NOTA': 'Nota'}), 
                    on='Colaborador', 
                    how='left'
                ).fillna(0.0)
            else:
                df_template['Nota'] = 0.0

            df_editado = st.data_editor(
                df_template,
                column_config={
                    "Colaborador": st.column_config.TextColumn("Colaborador", disabled=True),
                    "Nota": st.column_config.NumberColumn("Nota", min_value=0.0, max_value=5.0, step=0.1, format="%.1f", disabled=ja_salvo or not sprint_encerrada),
                },
                hide_index=True, use_container_width=True, key=f"editor_notas_{id_sprint_selecionada}"
            )

            pode_salvar = sprint_encerrada and not ja_salvo
            if st.button("Salvar Avaliação Final", use_container_width=True, type="primary", disabled=not pode_salvar):
                try:
                    from sqlalchemy import text
                    with conn.session as s:
                        for index, row in df_editado.iterrows():
                            if row['Nota'] > 0:
                                query_insert = """
                                    INSERT INTO TB_SPRINT_AVALIACAO (ID_SPRINT, NOME_GESTOR, NOTA) 
                                    VALUES (:id, :g, :n)
                                    ON DUPLICATE KEY UPDATE NOTA = VALUES(NOTA)
                                """
                                s.execute(text(query_insert),
                                            {"id": id_sprint_selecionada, "g": row['Colaborador'], "n": row['Nota']})
                        s.commit()
                    st.success("Avaliação salva com sucesso!")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e: 
                    st.error(f"Erro ao salvar: {e}")

            notas_validas = df_editado[df_editado['Nota'] > 0]['Nota']
            if not notas_validas.empty:
                media_atual = notas_validas.mean()
                st.info(f" **Média Consolidada da Sprint: {media_atual:.1f} / 5.0**")

        
        with st.expander("Editar Nota Retroativa"):
            st.warning("Atenção: Use este campo apenas para corrigir erros de digitação em sprints passadas.")
            
            try:
                df_all_notas = conn.query("SELECT DISTINCT NOME_GESTOR FROM TB_SPRINT_AVALIACAO", ttl="10m")
                colaboradores_para_edit = df_all_notas['NOME_GESTOR'].tolist() if not df_all_notas.empty else []
                
                col_ed1, col_ed2, col_ed3 = st.columns([2, 1, 1])
                
                colaborador_edit = col_ed1.selectbox("Colaborador para ajustar:", colaboradores_para_edit, key="sel_colab_edit")
                nova_nota_edit = col_ed2.number_input("Nova Nota:", 0.0, 5.0, 5.0, 0.1, key="num_nota_edit")
                
                col_ed3.write("")
                col_ed3.write("")
                if col_ed3.button("Confirmar Alteração", use_container_width=True):
                    from sqlalchemy import text
                    with conn.session as s:
                        s.execute(text("UPDATE TB_SPRINT_AVALIACAO SET NOTA = :n WHERE ID_SPRINT = :id AND NOME_GESTOR = :g"),
                                    {"n": nova_nota_edit, "id": id_sprint_selecionada, "g": colaborador_edit})
                        s.commit()
                    st.success(f"Nota de {colaborador_edit} atualizada para {nova_nota_edit}!")
                    st.cache_data.clear()
                    st.rerun()
            except Exception:
                st.info("Nenhuma nota encontrada para edição retroativa.")

        
            
        # ========================================================
        #  EVOLUÇÃO DA QUALIDADE (NOTAS DOS GESTORES)
        # ========================================================
        st.divider()

        query_historico_notas = """
            SELECT s.ID_SPRINT as sprint_id, s.DESCRICAO as Sprint, a.NOME_GESTOR as Gestor,
                   a.NOTA as Nota, s.DATA_INICIO as data_inicio
            FROM TB_SPRINT_AVALIACAO a
            JOIN TB_SPRINT s ON a.ID_SPRINT = s.ID_SPRINT
            ORDER BY s.DATA_INICIO ASC
        """
        try:
            df_tendencia_raw = conn.query(query_historico_notas, ttl="10m")
        except Exception as e:
            df_tendencia_raw = pd.DataFrame()
            st.error(f"Erro ao carregar histórico de notas: {e}")

        # Ordem cronológica, a mesma nos dois gráficos (a alfabética quebraria em "Sprint 100").
        if not df_tendencia_raw.empty:
            df_sprints_aval = (
                df_tendencia_raw.groupby(['sprint_id', 'Sprint'], as_index=False)['data_inicio'].first()
                .sort_values('data_inicio')
            )
            ordem_sprints_aval = df_sprints_aval['Sprint'].tolist()
        else:
            df_sprints_aval = pd.DataFrame(columns=['sprint_id', 'Sprint', 'data_inicio'])
            ordem_sprints_aval = []

        # Quantas sprints analisar (as N mais recentes). Vale para os pontos, as notas e a tabela por participante.
        if len(df_sprints_aval) > 1:
            qtd_sprints_aval = st.slider(
                "Quantidade de sprints para análise (mais recentes):",
                min_value=1, max_value=len(df_sprints_aval), value=min(7, len(df_sprints_aval)),
                key="slider_sprints_avaliacao"
            )
            df_sprints_aval = df_sprints_aval.tail(qtd_sprints_aval)
            ordem_sprints_aval = df_sprints_aval['Sprint'].tolist()
            df_tendencia_raw = df_tendencia_raw[df_tendencia_raw['sprint_id'].isin(df_sprints_aval['sprint_id'])]

        # ========================================================
        #  PONTOS ENTREGUES POR SPRINT (desempenho quantitativo)
        # ========================================================
        st.subheader("Pontos Entregues por Sprint")
        st.write("Total de pontos entregues em cada sprint avaliada, para comparar com a nota logo abaixo.")

        if df_sprints_aval.empty or df_issues.empty:
            st.info("Ainda não há sprints avaliadas para comparar os pontos entregues.")
        else:
            # Mesma base do card "Total de Pontos Entregues": TB_SPRINT_DETAILS, filtrado pelos projetos da barra lateral.
            df_pts_aval = df_issues[
                (df_issues['projeto'].isin(projeto)) & (df_issues['sprint_id'].isin(df_sprints_aval['sprint_id']))
            ].copy()
            df_pts_aval['pontos_num'] = pd.to_numeric(df_pts_aval['pontos'], errors='coerce').fillna(0.0)
            df_pts_por_sprint = df_pts_aval.groupby('sprint_id', as_index=False)['pontos_num'].sum()
            df_barras_pts = df_sprints_aval.merge(df_pts_por_sprint, on='sprint_id', how='left').fillna({'pontos_num': 0.0})

            barras_pts = alt.Chart(df_barras_pts).mark_bar(color='#3CD6E7').encode(
                x=alt.X('Sprint:N', sort=ordem_sprints_aval, title=None),
                y=alt.Y('pontos_num:Q', title='Pontos entregues', axis=alt.Axis(grid=False, minExtent=60)),
                tooltip=['Sprint', alt.Tooltip('pontos_num:Q', format='.1f', title='Pontos')]
            )
            rotulos_pts = barras_pts.mark_text(dy=-8, color='white').encode(text=alt.Text('pontos_num:Q', format='.0f'))
            st.altair_chart((barras_pts + rotulos_pts).properties(height=260), use_container_width=True, theme="streamlit")

        # ========================================================
        #  EVOLUÇÃO DA QUALIDADE (NOTAS DOS GESTORES)
        # ========================================================
        st.subheader("Evolução da Qualidade (Média das notas)")
        st.write("Acompanhamento das notas médias atribuída para cada sprint.")

        try:
            if not df_tendencia_raw.empty:
                df_media_sprint = df_tendencia_raw.groupby(['sprint_id', 'Sprint'], as_index=False)['Nota'].mean()
                df_media_sprint.rename(columns={'Nota': 'Media'}, inplace=True)

                # Zoom no eixo para os décimos aparecerem.
                nota_min = float(df_media_sprint['Media'].min())
                nota_max = float(df_media_sprint['Media'].max())
                eixo_min = max(0.0, math.floor((nota_min - 0.2) * 10) / 10)
                eixo_max = min(5.0, math.ceil((nota_max + 0.2) * 10) / 10)

                chart_tendencia = alt.Chart(df_media_sprint).mark_line(
                    color='#4CA6FF',
                    strokeWidth=3,
                    point=alt.OverlayMarkDef(size=80, color='#4CA6FF', fill='white')
                ).encode(
                    x=alt.X('Sprint:N', sort=ordem_sprints_aval, title="Sprints Anteriores"),
                    y=alt.Y('Media:Q', title="Nota Média",
                            scale=alt.Scale(domain=[eixo_min, eixo_max], zero=False),
                            axis=alt.Axis(format='.1f', minExtent=60)),
                    tooltip=['Sprint', alt.Tooltip('Media:Q', format='.2f', title='Nota Média')]
                )
                rotulos_notas = chart_tendencia.mark_text(dy=-14, color='white').encode(
                    text=alt.Text('Media:Q', format='.2f')
                )

                st.altair_chart((chart_tendencia + rotulos_notas).properties(height=350), use_container_width=True, theme="streamlit")
                with st.expander("Ver comparativo detalhado (Notas por participante)"):

                    df_pivot = df_tendencia_raw.pivot_table(
                        index='Gestor',
                        columns='Sprint',
                        values='Nota',
                        aggfunc='first'
                    )
                    df_pivot = df_pivot.reindex(columns=[s for s in ordem_sprints_aval if s in df_pivot.columns])
                    df_pivot.index.name = 'Colaborador'

                    linha_media = df_pivot.mean().round(1)

                    df_pivot = df_pivot.round(1)

                    df_pivot = df_pivot.fillna("-")

                    df_exibicao = df_pivot.copy()
                    df_exibicao.loc['MÉDIA FINAL'] = linha_media

                    df_exibicao = df_exibicao.reset_index()
                    # Tudo como texto (as colunas misturavam número e "-").
                    for _col in df_exibicao.columns[1:]:
                        df_exibicao[_col] = df_exibicao[_col].apply(
                            lambda x: "-" if pd.isna(x) else (f"{x:.1f}" if isinstance(x, (int, float)) else str(x)))

                    st.dataframe(df_exibicao, use_container_width=True, hide_index=True)
                    
            else:
                st.info("Ainda não há avaliações suficientes registradas no banco para gerar o gráfico de evolução.")
                
        except Exception as e:
            st.error(f"Erro ao processar histórico de médias: {e}")
                

    else:
        st.warning("Vá à aba 'Gerenciar Sprints' e adicione a sua primeira Sprint!")