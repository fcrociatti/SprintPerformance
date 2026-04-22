import streamlit as st
import pandas as pd
import altair as alt
from datetime import timedelta, datetime
from somaCopia import executar_extracao
from somaCopia import limpar_snapshot_sprint 
import os

st.set_page_config(page_title="Sprint Performance - DDS", layout="wide")

conn = st.connection("banco_dds", type="sql")

col_titulo, col_logo = st.columns([5, 1])

with col_titulo:
    st.title("📊 Sprint Performance - DDS")

with col_logo:
    
    caminho_logo = "assets/logo.png" 
    if os.path.exists(caminho_logo):
        st.write("") 
        st.image(caminho_logo, use_container_width=True)
        


# ==========================================
# CARREGAMENTO GLOBAL DOS DADOS 
# ==========================================
@st.cache_data(ttl=600)
def carregar_issues():
    conn.reset()
    query = """
        SELECT ID_SPRINT_DETAILS as id, ISSUE_KEY as issue_key, PROJETO as projeto, 
               RESPONSAVEL as responsavel, TIPO_ITEM as tipo_item, CATEGORIA as categoria, 
               PONTOS as pontos, DATA_CONCLUSAO as data_conclusao, ID_SPRINT as sprint_id, 
               CLIENTE as cliente, RESUMO as resumo
        FROM TB_SPRINT_DETAILS
    """
    return conn.query(query)

@st.cache_data(ttl=600)
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


@st.cache_data(ttl=600)
def carregar_snapshots():
    conn.reset()
    query = """
        SELECT ID_SNAPSHOT as id, ID_SPRINT as sprint_id, FASE as fase, 
               DESCRICAO_CUSTOMIZADA as descricao, QTD_TOTAL as qtd_total, 
               QTD_SUST as qtd_sust, QTD_DESV as qtd_desv, DATA_REGISTRO as data_registro
        FROM TB_SPRINT_SNAPSHOT
        ORDER BY DATA_REGISTRO ASC
    """
    return conn.query(query)

@st.cache_data(ttl=600)
def carregar_backlog():
    conn.reset()
    query = """
        SELECT ID_SPRINT_BACKLOG as id, ID_SPRINT as sprint_id, ISSUE_KEY as issue_key, 
               PROJETO as projeto, RESPONSAVEL as responsavel, PAPEL as papel, 
               TIPO_ITEM as tipo_item, CLIENTE as cliente, RESUMO as resumo, 
               DATA_CRIACAO as data_criacao 
        FROM TB_SPRINT_BACKLOG
    """
    return conn.query(query)

df_issues = carregar_issues()
df_sprints = carregar_sprints()
df_snapshots = carregar_snapshots()
df_backlog = carregar_backlog()

if not df_sprints.empty:
    if 'descricao' not in df_sprints.columns:
        df_sprints['descricao'] = "Sem Descrição"
    else:
        df_sprints['descricao'] = df_sprints['descricao'].fillna("Sem Descrição")
    
    df_sprints['nome_exibicao'] = df_sprints['descricao'] + " - " + df_sprints['nome_sprint']


aba_dashboard,  aba_sincronizacao, aba_historico = st.tabs(["📈 Visão da Sprint",  "⚙️ Gerenciar Sprints", "📊 Histórico & Desempenho"])

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
            devs_selecionados_hist = col_f2.multiselect("2. Filtrar Desenvolvedores:", devs_disp_hist, default=devs_disp_hist)
            
            df_hist = df_hist[df_hist['responsavel'].isin(devs_selecionados_hist)]
            
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
                
                
               
                st.write("**📊 Evolução de Entregas por Desenvolvedor**")
                    
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
                
                st.write("**🏆 Ranking Acumulado no Período**")
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

    # ---------------------------------------------------------
    # PARTE 1: CADASTRAR NOVA SPRINT (Onde entra o "INICIO")
    # ---------------------------------------------------------
    if acao == "Cadastrar Nova Sprint":
        st.write("Defina a identificação e o intervalo da nova Sprint.")
        with st.form("form_sync_nova"):
            descricao_input = st.text_input("Identificação da Sprint", placeholder="Ex: Sprint 44")
            col1, col2 = st.columns(2)
            dt_inicio = col1.date_input("Data de Início da Sprint")
            dt_fim = col2.date_input("Data de Fim da Sprint", value=dt_inicio + timedelta(days=13))
            
            # NOVO CAMPO AQUI TAMBÉM
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
                            else: 
                                st.error(f"❌ Falha: {mensagem}")

    # ---------------------------------------------------------
    # PARTE 2: ATUALIZAR SPRINT (Onde entra o row_sprint e o Checkbox)
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
                        else: st.error(f"❌ Falha: {mensagem}")
        else: st.warning("Nenhuma Sprint cadastrada para atualizar.")

       
        # ---------------------------------------------------------
        # PARTE 3: DETALHES DE ATUALIZAÇÃO E BORRACHA
        # ---------------------------------------------------------
        if 'logs_jira' in st.session_state and len(st.session_state['logs_jira']) > 0:
            st.markdown("<br>", unsafe_allow_html=True)
            with st.expander("📋 Ver detalhamento de tarefas atualizadas no Jira", expanded=True):
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
        st.sidebar.header("Filtros da Sprint")
        
        lista_sprints = df_sprints['nome_exibicao'].tolist()
        sprint_selecionada = st.sidebar.selectbox("Selecione a Sprint Atual", lista_sprints)
        id_sprint_selecionada = df_sprints[df_sprints['nome_exibicao'] == sprint_selecionada]['id'].iloc[0]

        projetos_issues = df_issues['projeto'].unique() if not df_issues.empty else []
        projetos_backlog = df_backlog['projeto'].unique() if not df_backlog.empty else []
        projetos_disponiveis = list(set(list(projetos_issues) + list(projetos_backlog)))
        if not projetos_disponiveis: projetos_disponiveis = ["STAR"]
        projeto = st.sidebar.multiselect("Projeto", projetos_disponiveis, default=projetos_disponiveis)
        
        if not df_issues.empty: df_filtrado = df_issues[(df_issues['projeto'].isin(projeto)) & (df_issues['sprint_id'] == id_sprint_selecionada)]
        else: df_filtrado = pd.DataFrame()
            
        if not df_backlog.empty: df_backlog_filtrado = df_backlog[(df_backlog['projeto'].isin(projeto)) & (df_backlog['sprint_id'] == id_sprint_selecionada)].copy()
        else: df_backlog_filtrado = pd.DataFrame()

        st.subheader(f"📋 Visão Geral da {sprint_selecionada.split(' - ')[0]} (Itens pendentes)")
        
        if not df_backlog_filtrado.empty:
            tipos_sustentacao = ["erro", "atendimento", "retorno negativo (rn)"]
            df_backlog_filtrado['categoria'] = df_backlog_filtrado['tipo_item'].apply(lambda x: "Sustentação" if str(x).lower() in tipos_sustentacao else "Desenvolvimento")

            def obter_qtd(nome_busca):
                return len(df_backlog_filtrado[df_backlog_filtrado['responsavel'].str.contains(nome_busca, case=False, na=False)])

            total_itens = len(df_backlog_filtrado)
            itens_sust = len(df_backlog_filtrado[df_backlog_filtrado['categoria'] == 'Sustentação'])
            itens_desv = len(df_backlog_filtrado[df_backlog_filtrado['categoria'] == 'Desenvolvimento'])

            anderson = obter_qtd("Anderson")
            fernando = obter_qtd("Fernando")
            gustavo = obter_qtd("Gustavo")
            nathan = obter_qtd("Nathan")
            eder = obter_qtd("Eder")
            sergio = obter_qtd("Sergio")
            daniel = obter_qtd("Daniel")

            with st.container(border=True):
               
                c_tit, c_lbl = st.columns([3, 1])
                c_tit.markdown("#### 📌 Marcadores Principais (Pendentes de desenvolvimento)")
                
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
            
            with st.expander("📊 Histórico de itens da Sprint (Planning vs Checkpoint vs Final)", expanded=False):
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
            st.subheader("📊 Matriz Comparativa de Sprints")
            st.write("Analise a evolução de itens e a distribuição da equipe ao longo das Sprints.")
            
            todas_sprints_nomes = df_sprints['nome_sprint'].tolist()
            
            sprints_selecionadas = st.multiselect(
                "Selecione as Sprints para comparar (Colunas):",
                options=todas_sprints_nomes,
                default=todas_sprints_nomes
            )
            
            if sprints_selecionadas:
                linhas_apontadores = [
                    "📦 Total de Itens",
                    "🔧 Sustentação",
                    "💻 Desenvolvimento",
                    " Total Foco Sérgio+Eder",
                    " Sérgio",
                    " Eder",
                    " Daniel",
                    " Total Análise",
                    " Anderson",
                    " Fernando",
                    " Gustavo",
                    " Nathan"
                ]
                
                dados_matriz = {"Apontadores Principais": linhas_apontadores}
                
                for nome_sp in sprints_selecionadas:
                    id_sp = int(df_sprints[df_sprints['nome_sprint'] == nome_sp].iloc[0]['id'])
                    
                    tot, sus, des = 0, 0, 0
                    qtd_sergio, qtd_eder, qtd_daniel = 0, 0, 0
                    tot_foco_se = 0
                    qtd_anderson, qtd_fernando, qtd_gustavo, qtd_nathan = 0, 0, 0, 0
                    tot_analise = 0
                    
                    if 'df_snapshots' in locals() and not df_snapshots.empty:
                        snaps_sp = df_snapshots[df_snapshots['sprint_id'] == id_sp]
                        if not snaps_sp.empty:
                            last_snap = snaps_sp.iloc[-1]
                            tot, sus, des = last_snap['qtd_total'], last_snap['qtd_sust'], last_snap['qtd_desv']
                    
                    if 'df_backlog' in locals() and not df_backlog.empty:
                        col_id = next((col for col in df_backlog.columns if col.lower() in ['id_sprint', 'sprint_id']), None)
                        
                        if col_id:
                            bk_sp = df_backlog[df_backlog[col_id] == id_sp]
                            
                            if not bk_sp.empty:
                                col_resp = next((col for col in bk_sp.columns if col.lower() in ['responsavel', 'assignee', 'responsável']), None)
                                
                                if col_resp:
                                    resps = bk_sp[col_resp].fillna('').str.lower()
                                    
                                    qtd_sergio = resps.str.contains('sergio|sérgio').sum()
                                    qtd_eder = resps.str.contains('eder').sum()
                                    qtd_daniel = resps.str.contains('daniel').sum()
                                    tot_foco_se = qtd_sergio + qtd_eder
                                    
                                    qtd_anderson = resps.str.contains('anderson').sum()
                                    qtd_fernando = resps.str.contains('fernando').sum()
                                    qtd_gustavo = resps.str.contains('gustavo').sum()
                                    qtd_nathan = resps.str.contains('nathan').sum()
                                    tot_analise = qtd_anderson + qtd_fernando + qtd_gustavo + qtd_nathan
                        
                    dados_matriz[nome_sp] = [
                        tot, sus, des,
                        tot_foco_se, qtd_sergio, qtd_eder, qtd_daniel,
                        tot_analise, qtd_anderson, qtd_fernando, qtd_gustavo, qtd_nathan
                    ]
                
                df_matriz = pd.DataFrame(dados_matriz)
                
                for col in sprints_selecionadas:
                    df_matriz[col] = df_matriz[col].astype(int)
                    
                st.dataframe(df_matriz, use_container_width=True, hide_index=True)
            else:
                st.info("⚠️ Selecione pelo menos uma Sprint no filtro acima para visualizar o comparativo.")            
                

            col_eq1, col_eq2 = st.columns(2)

            with col_eq1:
                with st.container(border=True):
                    st.markdown("#### 💼 Composição: Gestão (Foco)")
                    st.metric("Total Foco Sérgio+Eder", sergio + eder)
                    st.divider()

                    nomes_principais = ["Anderson", "Fernando", "Gustavo", "Nathan", "Daniel", "Eder", "Sergio"]
                    df_outros = df_backlog_filtrado[~df_backlog_filtrado['responsavel'].str.contains('|'.join(nomes_principais), case=False, na=False)]
                    todos_os_outros = len(df_outros)

                    c1, c2, c3,  = st.columns(3)
                    c1.metric("Sérgio", sergio)
                    c2.metric("Eder", eder)
                    c3.metric("Daniel", daniel)

                    st.markdown("<br>", unsafe_allow_html=True)
                    df_gest_donut = pd.DataFrame({'categoria': ["Sérgio", "Eder", "Daniel"],'quantidade': [sergio, eder, daniel]})
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

                        with st.expander("📋 Detalhes de itens da Gestão"):
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
                                    df_detalhe[['issue_key', 'responsavel', 'tipo_item', 'link']], 
                                    hide_index=True,
                                    use_container_width=True,
                                    column_config={
                                        "issue_key": "Chave",
                                        "responsavel": "Analista",
                                        "tipo_item": "Tipo",
                                        "link": st.column_config.LinkColumn("Jira")
                                    }
                                )
                            else:
                                st.warning("Nenhuma tarefa pendente para este filtro.")
                    else: st.info("Sem dados de gestão.")

            with col_eq2:
                with st.container(border=True):
                    st.markdown("#### 🔎 Composição: Equipa de Análise")
                    st.metric("Total Análise", anderson + fernando + gustavo + nathan)
                    st.divider()
                    
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Anderson", anderson)
                    c2.metric("Fernando", fernando)
                    c3.metric("Gustavo", gustavo)
                    c4.metric("Nathan", nathan)

                    st.markdown("<br>", unsafe_allow_html=True)
                    df_an_comp = pd.DataFrame({'responsavel': ["Anderson", "Fernando", "Gustavo", "Nathan"],'quantidade': [anderson, fernando, gustavo, nathan]})
                    
                    if not df_an_comp.empty and df_an_comp['quantidade'].sum() > 0:
                        bar_comp = alt.Chart(df_an_comp).mark_bar(color="#37a0d2").encode(
                            x=alt.X('quantidade:Q', title='Qtd de Itens', axis=alt.Axis(grid=False)),
                            y=alt.Y('responsavel:N', sort='-x', title=''),
                            tooltip=['responsavel', 'quantidade']
                        )
                        label_comp = bar_comp.mark_text(align='left', baseline='middle', dx=5, color='white').encode(text='quantidade:Q')
                        st.altair_chart((bar_comp + label_comp).properties(height=200), use_container_width=True, theme="streamlit")
                        
                       
                        with st.expander("📋 Detalhes de itens da Equipe de Análise"):
                            analista_selecionado = st.selectbox(
                                "Filtrar tarefas de:", 
                                ["Todos da Equipe", "Anderson", "Fernando", "Gustavo", "Nathan"],
                                label_visibility="collapsed" 
                            )
                            
                            if analista_selecionado == "Todos da Equipe":
                                df_detalhe = df_backlog_filtrado[df_backlog_filtrado['responsavel'].str.contains("Anderson|Fernando|Gustavo|Nathan", case=False, na=False)].copy()
                            else:
                                df_detalhe = df_backlog_filtrado[df_backlog_filtrado['responsavel'].str.contains(analista_selecionado, case=False, na=False)].copy()
                            
                            if not df_detalhe.empty:
                                df_detalhe['link'] = "https://ddsinfo.atlassian.net/browse/" + df_detalhe['issue_key']
                                st.dataframe(
                                    df_detalhe[['issue_key', 'responsavel', 'tipo_item', 'link']], 
                                    hide_index=True,
                                    use_container_width=True,
                                    column_config={
                                        "issue_key": "Chave",
                                        "responsavel": "Analista",
                                        "tipo_item": "Tipo",
                                        "link": st.column_config.LinkColumn("Jira")
                                    }
                                )
                            else:
                                st.warning("Nenhuma tarefa pendente para este filtro.")
                        
                    else: st.info("Sem dados de análise.")
            with st.expander("🔍 Ver outros colaboradores e lista completa do backlog"):
                if todos_os_outros > 0:
                    st.write("**Resumo dos Outros Colaboradores:**")
                    outros_agrupado = df_outros['responsavel'].value_counts().reset_index()
                    outros_agrupado.columns = ['Responsável', 'Qtd de Itens']
                    st.dataframe(outros_agrupado, hide_index=True)
                
                st.write("**Lista Completa do Backlog:**")
                tabela_backlog = df_backlog_filtrado.copy()
                tabela_backlog['link'] = "https://ddsinfo.atlassian.net/browse/" + tabela_backlog['issue_key']
                st.dataframe(
                    tabela_backlog[['issue_key', 'cliente', 'resumo', 'tipo_item', 'categoria', 'responsavel', 'link']], 
                    use_container_width=True, hide_index=True,
                    column_config={
                        "issue_key": "Chave", "cliente": "Cliente",
                        "resumo": st.column_config.TextColumn("Resumo", width="large"),
                        "tipo_item": "Tipo", "categoria": "Categoria", "responsavel": "Responsável", 
                        "link": st.column_config.LinkColumn("Jira")
                    }
                )
        else:
            st.info("Nenhum item em andamento encontrado.")

        st.divider()

        st.subheader(f"✅ Entregas da {sprint_selecionada.split(' - ')[0]} (Pontos)")

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
                    st.write("🏆 Entregas por Desenvolvedor")
                    
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
                
                tabela_detalhe['link'] = "https://ddsinfo.atlassian.net/browse/" + tabela_detalhe['issue_key']
                
                st.dataframe(
                    tabela_detalhe[['issue_key', 'cliente', 'resumo', 'tipo_item', 'categoria', 'pontos', 'link']], 
                    use_container_width=True, hide_index=True,
                    column_config={
                        "issue_key": "Chave", "cliente": "Cliente",
                        "resumo": st.column_config.TextColumn("Resumo", width="large"),
                        "tipo_item": "Tipo", "categoria": "Categoria", "pontos": "Pontos", 
                        "link": st.column_config.LinkColumn("Jira")
                    }
                )
        else:
            st.info("Nenhuma entrega contabilizada.")

        st.divider()
        st.subheader("📉 Burndown da Sprint")

        if not df_backlog_filtrado.empty or not df_filtrado.empty:
            total_tickets = len(df_backlog_filtrado) + len(df_filtrado)

            data_ini_str = df_sprints[df_sprints['nome_exibicao'] == sprint_selecionada]['data_inicio'].iloc[0]
            data_fim_str = df_sprints[df_sprints['nome_exibicao'] == sprint_selecionada]['data_fim'].iloc[0]
            
            data_ini = data_ini_str if not isinstance(data_ini_str, str) else datetime.strptime(data_ini_str, "%Y-%m-%d").date()
            data_fim = data_fim_str if not isinstance(data_fim_str, str) else datetime.strptime(data_fim_str, "%Y-%m-%d").date()
            
            qtd_dias = (data_fim - data_ini).days + 1
            dias_sprint = [data_ini + timedelta(days=x) for x in range(qtd_dias)]

            df_entregas_bd = df_filtrado.copy()
            entregas_por_dia = {}
            if not df_entregas_bd.empty:
                df_entregas_bd['data_dt'] = pd.to_datetime(df_entregas_bd['data_conclusao']).dt.date
                entregas_por_dia = df_entregas_bd.groupby('data_dt').size().to_dict()

            bd_dados = []
            real_restante = total_tickets
            passo_ideal = total_tickets / (qtd_dias - 1) if qtd_dias > 1 else 0
            hoje = datetime.now().date()

            for i, dia in enumerate(dias_sprint):
                ideal_restante = total_tickets - (passo_ideal * i)

                entregues_hoje = entregas_por_dia.get(dia, 0)
                real_restante = real_restante - entregues_hoje

                linha_real = real_restante if dia <= hoje else None

                bd_dados.append({
                    "Data": dia.strftime("%d/%m"),
                    "Diretriz": round(ideal_restante, 1),
                    "Trabalho Restante": linha_real
                })

            df_burndown = pd.DataFrame(bd_dados)

            base = alt.Chart(df_burndown).encode(
                x=alt.X('Data:O', sort=df_burndown['Data'].tolist(), title="Dias da Sprint")
            )

            linha_ideal = base.mark_line(color='gray', strokeDash=[5, 5]).encode(
                y=alt.Y('Diretriz:Q', title="Tickets Restantes"),
                tooltip=['Data', 'Diretriz']
            )

            linha_real = base.mark_line(color='#4CA6FF', point=True, strokeWidth=3).encode(
                y=alt.Y('Trabalho Restante:Q'),
                tooltip=['Data', 'Trabalho Restante']
            )

            grafico_burndown = (linha_ideal + linha_real).properties(height=350)
            st.altair_chart(grafico_burndown, use_container_width=True, theme="streamlit")
            
        else:
            st.info("Sem dados suficientes para gerar o Burndown.")


        st.divider()
        st.subheader("🏢 Itens por Cliente (Planning)")

        if not df_backlog_filtrado.empty:
            
            if 'data_criacao' not in df_backlog_filtrado.columns:
                df_backlog_filtrado['data_criacao'] = "2000-01-01"

            data_inicio_sprint = df_sprints[df_sprints['nome_exibicao'] == sprint_selecionada]['data_inicio'].iloc[0]
            
            data_ini_str_comp = data_inicio_sprint.strftime("%Y-%m-%d") if not isinstance(data_inicio_sprint, str) else data_inicio_sprint
            df_clientes_sprint = df_backlog_filtrado[df_backlog_filtrado['data_criacao'] >= data_ini_str_comp].copy()

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
                    
                    st.dataframe(
                        df_detalhe_cliente[['issue_key', 'resumo', 'tipo_item', 'responsavel', 'link']], 
                        use_container_width=True, hide_index=True,
                        column_config={
                            "issue_key": "Chave",
                            "resumo": st.column_config.TextColumn("Resumo", width="large"),
                            "tipo_item": "Tipo", 
                            "responsavel": "Responsável", 
                            "link": st.column_config.LinkColumn("Jira")
                        }
                    )
                else:
                    st.write("Sem tickets para detalhar.")
        else:
            st.info("Nenhum item encontrado no backlog para exibir clientes.")

    else:
        st.warning("Vá à aba '⚙️ Gerenciar Sprints' e adicione a sua primeira Sprint!")