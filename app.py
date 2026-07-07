import streamlit as st
import pandas as pd
import altair as alt
from datetime import timedelta, datetime
from somaCopia import executar_extracao
from somaCopia import limpar_snapshot_sprint 
import os
import re

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
# ==========================================
# CARREGAMENTO GLOBAL DOS DADOS 
# ==========================================
def carregar_issues():
    conn.reset()
    query = """
        SELECT ID_SPRINT_DETAILS as id, ISSUE_KEY as issue_key, PROJETO as projeto, 
               RESPONSAVEL as responsavel, TIPO_ITEM as tipo_item, CATEGORIA as categoria, 
               PONTOS as pontos, DATA_CONCLUSAO as data_conclusao, ID_SPRINT as sprint_id, 
               CLIENTE as cliente, RESUMO as resumo, STATUS as status, SISTEMA as sistema,
               DATA_LIMITE as data_limite, DATA_CRIACAO as data_criacao
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
               QTD_SUST as qtd_sust, QTD_DESV as qtd_desv, DATA_REGISTRO as data_registro
        FROM TB_SPRINT_SNAPSHOT
        ORDER BY DATA_REGISTRO ASC
    """
    return conn.query(query)

def carregar_backlog():
    conn.reset()
    query = """
        SELECT ID_SPRINT_BACKLOG as id, ID_SPRINT as sprint_id, ISSUE_KEY as issue_key, 
               PROJETO as projeto, RESPONSAVEL as responsavel, PAPEL as papel, 
               TIPO_ITEM as tipo_item, CLIENTE as cliente, RESUMO as resumo, 
               DATA_CRIACAO as data_criacao, STATUS as status, SISTEMA as sistema,
               DATA_LIMITE as data_limite
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
        lista_sprints = df_sprints['nome_exibicao'].tolist()
        sprint_selecionada = st.sidebar.selectbox("Selecione a Sprint Atual", lista_sprints)
        
        # 1. Força o ID a ser número inteiro
        id_sprint_selecionada = int(df_sprints[df_sprints['nome_exibicao'] == sprint_selecionada]['id'].iloc[0])

        # 2. Limpa espaços invisíveis dos projetos (strip) para não quebrar a busca
        projetos_issues = df_issues['projeto'].astype(str).str.strip().unique().tolist() if not df_issues.empty else []
        projetos_backlog = df_backlog['projeto'].astype(str).str.strip().unique().tolist() if not df_backlog.empty else []
        projetos_disponiveis = list(set(projetos_issues + projetos_backlog))
        
        if not projetos_disponiveis: projetos_disponiveis = ["STAR"]
        projeto = st.sidebar.multiselect("Projeto", projetos_disponiveis, default=projetos_disponiveis)
        
        if not projeto: # Trava: se desmarcar tudo sem querer, puxa todos
            projeto = projetos_disponiveis

        # 3. Filtros blindados
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

            def obter_qtd(nome_busca):
                return len(df_backlog_filtrado[df_backlog_filtrado['responsavel'].str.contains(nome_busca, case=False, na=False)])

            total_itens = len(df_backlog_filtrado)
            itens_sust = len(df_backlog_filtrado[df_backlog_filtrado['categoria'] == 'Sustentação'])
            itens_desv = len(df_backlog_filtrado[df_backlog_filtrado['categoria'] == 'Desenvolvimento'])

            fernando = obter_qtd("Fernando")
            jonathan = obter_qtd("Jonathan")
            thiago = obter_qtd("Thiago")
            paulo = obter_qtd("Paulo")
            kaic = obter_qtd("Kaic de Castro")
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

            
            with st.expander("📊 Matriz Comparativa)", expanded=False):
            
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
                        qtd_anderson, qtd_fernando, qtd_gustavo, qtd_jonathan = 0, 0, 0, 0
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
                                        qtd_jonathan = resps.str.contains('jonathan').sum()
                                        tot_analise = qtd_anderson + qtd_fernando + qtd_gustavo + qtd_jonathan
                            
                        dados_matriz[nome_sp] = [
                            tot, sus, des,
                            tot_foco_se, qtd_sergio, qtd_eder, qtd_daniel,
                            tot_analise, qtd_anderson, qtd_fernando, qtd_gustavo, qtd_jonathan
                        ]
                    
                    df_matriz = pd.DataFrame(dados_matriz)
                    
                    for col in sprints_selecionadas:
                        df_matriz[col] = df_matriz[col].astype(int)
                        
                    st.dataframe(df_matriz, use_container_width=True, hide_index=True)
                else:
                    st.info("⚠️ Selecione pelo menos uma Sprint no filtro acima para visualizar o comparativo.")            
                
            st.divider()
            col_eq1, col_eq2 = st.columns(2)

            with col_eq1:
                with st.container(border=True):
                    st.markdown("#### Gestão (Foco)")
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
                                    df_detalhe[['issue_key','resumo',  'responsavel', 'tipo_item', 'link']], 
                                    hide_index=True,
                                    use_container_width=True,
                                    column_config={
                                        "issue_key": "Chave",
                                        "resumo" : "Resumo",
                                        "responsavel": "Gestor",
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
                    st.metric("Total Análise", fernando + jonathan + thiago + paulo + kaic)
                    st.divider()
                    
                    c1, c2, c3, c4, c5 = st.columns(5)
                    c1.metric("Fernando", fernando)
                    c2.metric("Jonathan", jonathan)
                    c3.metric("Thiago", thiago)
                    c4.metric("Paulo", paulo)
                    c5.metric("Kaic", kaic)

                    st.markdown("<br>", unsafe_allow_html=True)
                    df_an_comp = pd.DataFrame({
                        'responsavel': ["Fernando", "Jonathan", "Thiago", "Paulo", "Kaic"],
                        'quantidade': [fernando, jonathan, thiago, paulo, kaic]
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
                                ["Todos da Equipe", "Fernando", "Jonathan", "Thiago Honorato", "Paulo Domingues", "Kaic De Castro"],
                                label_visibility="collapsed" 
                            )
                            
                            if analista_selecionado == "Todos da Equipe":
                                df_detalhe = df_backlog_filtrado[df_backlog_filtrado['responsavel'].str.contains("Fernando|Jonathan|Thiago|Paulo|Kaic", case=False, na=False)].copy()
                            else:
                                df_detalhe = df_backlog_filtrado[df_backlog_filtrado['responsavel'].str.contains(analista_selecionado, case=False, na=False)].copy()
                            
                            if not df_detalhe.empty:
                                df_detalhe['link'] = "https://ddsinfo.atlassian.net/browse/" + df_detalhe['issue_key']
                                st.dataframe(
                                    df_detalhe[['issue_key','resumo' , 'responsavel', 'tipo_item', 'cliente','link']], 
                                    hide_index=True,
                                    use_container_width=True,
                                    column_config={
                                        "issue_key": "Chave",
                                        "resumo" : "Resumo",
                                        "responsavel": "Analista",
                                        "tipo_item": "Tipo",
                                        "cliente": "Cliente",
                                        "link": st.column_config.LinkColumn("Jira")
                                    }
                                )
                            else:
                                st.warning("Nenhuma tarefa pendente para este filtro.")
                        
                    else: 
                        st.info("Sem dados de análise.")

          

            # ========================================================
            # LISTA COMPLETA DO BACKLOG
            # ========================================================
            with st.expander("📋 Ver Lista Completa do Backlog (Todos os itens)"):
                tabela_backlog = df_backlog_filtrado.copy()
                tabela_backlog.columns = tabela_backlog.columns.str.lower()
                if 'status' not in tabela_backlog.columns:
                    tabela_backlog['status'] = 'aguardando sincronizacao'
                
                tabela_backlog['link'] = "https://ddsinfo.atlassian.net/browse/" + tabela_backlog['issue_key']
                st.dataframe(
                    tabela_backlog[['issue_key', 'sistema', 'cliente', 'resumo', 'status', 'tipo_item', 'categoria', 'responsavel', 'link']], 
                    use_container_width=True, hide_index=True,
                    column_config={
                        "issue_key": "Chave", 
                        "sistema": "Sistema", 
                        "cliente": "Cliente",
                        "resumo": st.column_config.TextColumn("Resumo", width="large"),
                        "status": "Status",
                        "tipo_item": "Tipo", "categoria": "Categoria", "responsavel": "Responsável", 
                        "link": st.column_config.LinkColumn("Jira")
                    }
                )            
                        
            

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
        else:
            st.info("Nenhuma entrega contabilizada.")

        st.divider()
        st.subheader("Burndown da Sprint")

        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            num_sprints = st.slider("Qtd de Sprints anteriores para média:", min_value=1, max_value=6, value=5, key="slider_sprints_burndown")
        with col2:
            show_media_entrega = st.checkbox("Média de Entrega Diária", value=True)
        with col3:
            show_media_sprint = st.checkbox("Média por Sprint", value=True)

        if not df_backlog_filtrado.empty or not df_filtrado.empty:
            id_sprint = int(df_sprints[df_sprints['nome_exibicao'] == sprint_selecionada]['id'].iloc[0])
            total_atual_pendentes = len(df_backlog_filtrado)
            tickets_iniciais = total_atual_pendentes + len(df_filtrado)
            
            if 'df_snapshots' in locals() and not df_snapshots.empty:
                snaps_sp = df_snapshots[df_snapshots['sprint_id'] == id_sprint].copy()
                snaps_inicio = snaps_sp[snaps_sp['fase'] == 'INICIO']
                if not snaps_inicio.empty:
                    tickets_iniciais = snaps_inicio.iloc[-1]['qtd_total']

            data_ini_str = df_sprints[df_sprints['nome_exibicao'] == sprint_selecionada]['data_inicio'].iloc[0]
            data_fim_str = df_sprints[df_sprints['nome_exibicao'] == sprint_selecionada]['data_fim'].iloc[0]
            data_ini = data_ini_str if not isinstance(data_ini_str, str) else datetime.strptime(data_ini_str, "%Y-%m-%d").date()
            data_fim = data_fim_str if not isinstance(data_fim_str, str) else datetime.strptime(data_fim_str, "%Y-%m-%d").date()
            
            qtd_dias = (data_fim - data_ini).days + 1
            dias_sprint = [data_ini + timedelta(days=x) for x in range(qtd_dias)]

            media_entrega_por_dia = []
            media_restante_por_dia = [None] * qtd_dias
            historico_restante = {d: None for d in range(qtd_dias)}
            historico_dias_entrega = {d: None for d in range(qtd_dias)}

            try:
                idx_atual = df_sprints.index[df_sprints['id'] == id_sprint].tolist()[0]
                sprints_anteriores = df_sprints.iloc[idx_atual+1 : idx_atual+1+num_sprints]
                ids_sprints_anteriores = sprints_anteriores['id'].tolist()

                historico_restante = {d: [] for d in range(qtd_dias)}

                if 'df_snapshots' in locals() and not df_snapshots.empty:
                    df_snaps_hist = df_snapshots[
                        df_snapshots['sprint_id'].isin(ids_sprints_anteriores)
                    ].copy()
                    df_snaps_hist['qtd_total'] = pd.to_numeric(df_snaps_hist['qtd_total'], errors='coerce')
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
                            .groupby('data_dt')['qtd_total']
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

                if not df_issues.empty and ids_sprints_anteriores:
                    df_issues_hist = df_issues[
                        (df_issues['projeto'].isin(projeto)) &
                        (df_issues['sprint_id'].isin(ids_sprints_anteriores))
                    ].copy()
                    if not df_issues_hist.empty:
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
                dict_real_diario = snaps_sp.sort_values('data_registro').groupby('data_dt')['qtd_total'].last().to_dict()

            dict_concluidos_diario = {}
            if not df_filtrado.empty:
                df_filtrado_copy = df_filtrado.copy()
                df_filtrado_copy['data_conclusao_dt'] = pd.to_datetime(df_filtrado_copy['data_conclusao']).dt.date
                dict_concluidos_diario = df_filtrado_copy.groupby('data_conclusao_dt').size().to_dict()

            bd_dados = []
            passo_ideal = tickets_iniciais / (qtd_dias - 1) if qtd_dias > 1 else 0
            hoje = datetime.now().date()
            ultimo_valor_conhecido = tickets_iniciais
            total_concluidos_acumulado = 0 

            for i, dia in enumerate(dias_sprint):
                ideal_restante = tickets_iniciais - (passo_ideal * i)
                if dia == hoje: ultimo_valor_conhecido = total_atual_pendentes
                elif dia in dict_real_diario: ultimo_valor_conhecido = dict_real_diario[dia]
                concluidos_hoje = dict_concluidos_diario.get(dia, 0)
                if dia <= hoje: total_concluidos_acumulado += concluidos_hoje
                bd_dados.append({
                    "Data": dia.strftime("%d/%m"),
                    "Diretriz": round(ideal_restante, 1),
                    "Trabalho Restante": ultimo_valor_conhecido if dia <= hoje else None,
                    "Concluídos Acumulados": total_concluidos_acumulado if dia <= hoje else None,
                    "Média Entrega Diária": round(media_entrega_por_dia[i], 1) if i < len(media_entrega_por_dia) and media_entrega_por_dia[i] is not None else None,
                    "Média por Sprint": media_restante_por_dia[i] if i < len(media_restante_por_dia) and media_restante_por_dia[i] is not None else None
                })

            df_burndown = pd.DataFrame(bd_dados)
            df_burndown['Média Entrega Diária'] = pd.to_numeric(df_burndown['Média Entrega Diária'], errors='coerce')
            df_burndown['Média por Sprint'] = pd.to_numeric(df_burndown['Média por Sprint'], errors='coerce')

            anotacoes_rows = []

            def _registrar_picos(historico, col_nome, datas_sprint):
                candidatos_max = []  
                candidatos_min = []

                for offset in range(len(datas_sprint)):
                    info = historico.get(offset)
                    if info and isinstance(info, dict):
                        candidatos_max.append((info['max_val'], info['max_sp'], offset))
                        candidatos_min.append((info['min_val'], info['min_sp'], offset))

                if not candidatos_max or not candidatos_min:
                    return

                val_max, sp_max, offset_max = max(candidatos_max, key=lambda x: x[0])
                val_min, sp_min, offset_min = min(candidatos_min, key=lambda x: x[0])

                data_max = datas_sprint[offset_max].strftime("%d/%m")
                data_min = datas_sprint[offset_min].strftime("%d/%m")

                anotacoes_rows.append({
                    'Data': data_max,
                    'Valor': val_max,
                    'Label': f"▲ {val_max:.0f} | {sp_max} | {data_max}",
                    'Tipo': f'Pico Máx — {col_nome}',
                    'Cor': '#2ECC71',
                    'dy': -18,
                })
                anotacoes_rows.append({
                    'Data': data_min,
                    'Valor': val_min,
                    'Label': f"▼ {val_min:.0f} | {sp_min} | {data_min}",
                    'Tipo': f'Pico Mín — {col_nome}',
                    'Cor': '#74B9FF',
                    'dy': 18,
                })

            if show_media_entrega and any(isinstance(historico_dias_entrega.get(o), dict) for o in range(qtd_dias)):
                _registrar_picos(historico_dias_entrega, 'Entrega Diária', dias_sprint)

            if show_media_sprint and any(isinstance(historico_restante.get(o), dict) for o in range(qtd_dias)):
                _registrar_picos(historico_restante, 'Trabalho Rest.', dias_sprint)

            df_anotacoes = pd.DataFrame(anotacoes_rows) if anotacoes_rows else pd.DataFrame()

            

            legenda_itens = [
                '<div><b style="color: gray;">- - -</b> Diretriz Ideal</div>',
                '<div><b style="color: #4CA6FF;">━●━</b> Trabalho Restante</div>',
                '<div><b style="color: #28A745;">━●━</b> Concluídos Acumulados</div>',
            ]
            if show_media_entrega:
                legenda_itens.append('<div><b style="color: #FF9F43;">- - -</b> Média Entrega Diária</div>')
                legenda_itens.append('<div><b style="color: #2ECC71;">◆</b> Pico Máx — Entrega Diária</div>')
                legenda_itens.append('<div><b style="color: #74B9FF;">◆</b> Pico Mín — Entrega Diária</div>')
            if show_media_sprint:
                legenda_itens.append('<div><b style="color: #8E44AD;">- - -</b> Média por Sprint</div>')
                legenda_itens.append('<div><b style="color: #2ECC71;">◆</b> Pico Máx — Trabalho Rest.</div>')
                legenda_itens.append('<div><b style="color: #74B9FF;">◆</b> Pico Mín — Trabalho Rest.</div>')

            st.markdown(
                '<div style="display:flex;flex-wrap:wrap;justify-content:center;gap:20px;font-size:14px;margin-bottom:15px;">'
                + "".join(legenda_itens)
                + '</div>',
                unsafe_allow_html=True
            )

            eixo_x = alt.X('Data:O', sort=None, title="Dias da Sprint")
            eixo_y = alt.Y('Valor:Q', title="Quantidade de Itens")

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
                if c is not None:
                    camadas.append(c)

            if show_media_sprint:
                c = _make_serie(df_burndown, 'Média por Sprint', '#8E44AD', [4, 2], False, 3)
                if c is not None:
                    camadas.append(c)

            if not df_anotacoes.empty:
                for _, ann_row in df_anotacoes.iterrows():
                    df_ann = pd.DataFrame([{'Data': ann_row['Data'],
                                            'Valor': ann_row['Valor'],
                                            'Label': ann_row['Label']}])
                    cor_ann = ann_row['Cor']
                    dy_ann  = int(ann_row['dy'])

                    df_ann['Tipo'] = ann_row['Tipo']
                    ponto = (
                        alt.Chart(df_ann)
                        .mark_point(size=150, color=cor_ann, filled=True, opacity=0.95, shape='diamond')
                        .encode(
                            x=alt.X('Data:O', sort=None),
                            y=alt.Y('Valor:Q'),
                            tooltip=[
                                alt.Tooltip('Tipo:N', title='📌 Marcador'),
                                alt.Tooltip('Label:N', title='Detalhe'),
                                alt.Tooltip('Valor:Q', title='Valor', format='.1f'),
                                alt.Tooltip('Data:O', title='Dia'),
                            ]
                        )
                    )
                    texto = (
                        alt.Chart(df_ann)
                        .mark_text(
                            dy=dy_ann,
                            fontSize=11,
                            fontWeight='bold',
                            color=cor_ann,
                            align='center',
                        )
                        .encode(
                            x=alt.X('Data:O', sort=None),
                            y=alt.Y('Valor:Q'),
                            text=alt.Text('Label:N'),
                        )
                    )
                    camadas.append(ponto)
                    camadas.append(texto)

            if camadas:
                grafico_burndown = alt.layer(*camadas).resolve_scale(y='shared').properties(height=420)
                st.altair_chart(grafico_burndown, use_container_width=True, theme="streamlit")
            else:
                st.info("Sem dados suficientes para renderizar o gráfico de Burndown.")
            
            with st.expander("Itens entregues por dia", expanded=False):
                if not df_filtrado.empty:
                    df_auditoria = df_filtrado.copy()
                    df_auditoria['Data da Entrega'] = pd.to_datetime(df_auditoria['data_conclusao']).dt.strftime('%d/%m/%Y')
                    df_auditoria = df_auditoria.sort_values('data_conclusao')
                    df_auditoria['link'] = "https://ddsinfo.atlassian.net/browse/" + df_auditoria['issue_key']
                    dias_com_entrega = ["Todos os Dias"] + df_auditoria['Data da Entrega'].unique().tolist()
                    dia_selecionado = st.selectbox("Filtrar por dia específico:", dias_com_entrega)
                    if dia_selecionado != "Todos os Dias": df_auditoria = df_auditoria[df_auditoria['Data da Entrega'] == dia_selecionado]
                    st.dataframe(
                        df_auditoria[['Data da Entrega', 'issue_key', 'resumo', 'responsavel', 'pontos', 'link']],
                        use_container_width=True, hide_index=True,
                        column_config={"Data da Entrega": "Data de Conclusão", "issue_key": "Chave", "resumo": st.column_config.TextColumn("Resumo", width="large"), "responsavel": "Dev", "pontos": st.column_config.NumberColumn("Pontos", format="%d"), "link": st.column_config.LinkColumn("Jira")}
                    )
                else: st.info("Nenhum item foi concluído nesta sprint ainda.")
        else: st.info("Sem dados suficientes para gerar o Burndown.")
        st.divider()       


        def buscar_autor_original(issue_key):
            try:
                query = f"SELECT RESPONSAVEL FROM TB_SPRINT_DETAILS WHERE ISSUE_KEY = '{issue_key}' LIMIT 1"
                resultado = conn.query(query)
                if not resultado.empty: return resultado.iloc[0]['RESPONSAVEL']
            except: pass
            return "Não rastreado"

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
        df_concluidos = pd.DataFrame()

        if not df_todas_issues.empty:
            df_todas_issues['tipo_norm'] = df_todas_issues['tipo_item'].astype(str).str.lower().str.strip()
            df_rns = df_todas_issues[df_todas_issues['tipo_norm'].str.contains('retorno negativo', na=False)].copy()
            
            df_concluidos = df_issues_all[df_issues_all['status'] == '6.0 Concluído']
            
            c1, c2, c3 = st.columns(3)
            c1.metric("RNs Gerados", len(df_rns))
            c2.metric("Itens Concluídos", len(df_concluidos))
            taxa = (len(df_rns) / len(df_concluidos) * 100) if len(df_concluidos) > 0 else 0
            c3.metric("Densidade de Falha", f"{taxa:.1f}%")

        if not df_rns.empty:
            st.write("---")
            col_left, col_right = st.columns(2)

            with col_left:
                st.write("**RNs por Desenvolvedor**")
                df_rank = df_rns.groupby('responsavel').size().reset_index(name='Qtd_RNs')
                df_rank = df_rank.sort_values(by='Qtd_RNs', ascending=False)
                bar_chart = alt.Chart(df_rank).mark_bar().encode(
                    x=alt.X('Qtd_RNs:Q', title='Qtd de RNs', axis=alt.Axis(tickMinStep=1)),
                    y=alt.Y('responsavel:N', sort='-x', title=''),
                    color=alt.value("#3CD6E7"),
                    tooltip=['responsavel', 'Qtd_RNs']
                ).properties(height=200)
                st.altair_chart(bar_chart, use_container_width=True)

            with col_right:
                st.write("**Status dos RNs**")
                df_status = df_rns.groupby('status').size().reset_index(name='Qtd')
                donut = alt.Chart(df_status).mark_arc(innerRadius=50).encode(
                    theta="Qtd:Q", color="status:N"
                ).properties(height=200)
                st.altair_chart(donut, use_container_width=True)

            with st.expander(" Detalhamento de Raiz"):
                df_rns['item_origem'] = df_rns['resumo'].apply(extrair_pai_prioritario)
                df_rns['autor_original'] = df_rns['item_origem'].apply(buscar_autor_original)
                st.dataframe(
                    df_rns[['issue_key', 'item_origem', 'autor_original', 'responsavel', 'resumo']],
                    use_container_width=True, hide_index=True,
                    column_config={
                        "issue_key": st.column_config.LinkColumn("Ticket RN", display_text="https://ddsinfo.atlassian.net/browse/(.*)"),
                        "item_origem": st.column_config.LinkColumn("Pai", display_text=r"https://ddsinfo.atlassian.net/browse/(.*)"),
                        "resumo": st.column_config.TextColumn("Resumo", width="large")
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
            st.markdown("####  Alertas de Prazo (Data Limite)")
            df_alertas = df_backlog_filtrado.copy()
            df_alertas['data_limite'] = pd.to_datetime(df_alertas['data_limite'])
            hoje_ts = pd.Timestamp(datetime.now().date())

            def definir_status_prazo(row):
                if pd.isnull(row['data_limite']): return "⚪ Sem Prazo"
                elif row['data_limite'].date() < hoje_ts.date(): return "🔴 Excedido"
                elif (row['data_limite'].date() - hoje_ts.date()).days <= 3: return "🟡 Próximo (Até 3 dias)"
                else: return "🟢 No Prazo"

            df_alertas['Alerta'] = df_alertas.apply(definir_status_prazo, axis=1)
            df_critico = df_alertas[df_alertas['Alerta'].isin(["🔴 Excedido", "🟡 Próximo (Até 3 dias)"])].copy()

            if not df_critico.empty:
                df_critico['Prazo'] = df_critico['data_limite'].dt.strftime('%d/%m/%Y')
                
                df_critico['link'] = "https://ddsinfo.atlassian.net/browse/" + df_critico['issue_key']
                
                st.dataframe(
                    df_critico[['Alerta', 'link', 'cliente', 'resumo', 'responsavel', 'Prazo']],
                    use_container_width=True, hide_index=True,
                    column_config={
                        "Alerta": st.column_config.TextColumn("Status", width="small"),
                        
                        "link": st.column_config.LinkColumn(
                            "Chave", 
                            display_text="https://ddsinfo.atlassian.net/browse/(.*)"
                        ),
                        
                        "cliente": "Cliente",
                        "resumo": "Tarefa",
                        "responsavel": "Responsável",
                        "Prazo": st.column_config.TextColumn("Data Limite", width="small")
                    }
                )
            else:
                st.success("✅ Nenhum item pendente com prazo excedido ou próximo do limite.")
            st.divider()

            st.divider()
            st.subheader(" Itens por Sistema")

            frames = []
            if not df_backlog_filtrado.empty: frames.append(df_backlog_filtrado)
            if not df_filtrado.empty: frames.append(df_filtrado)

            if frames:
                df_sistemas_sprint = pd.concat(frames, ignore_index=True)
                
                if 'sistema' in df_sistemas_sprint.columns:
                    df_sistemas_sprint['sistema'] = df_sistemas_sprint['sistema'].fillna("Não preenchido")
                    df_sistemas_sprint['sistema'] = df_sistemas_sprint['sistema'].apply(lambda x: "Não preenchido" if str(x).strip() in ["", "None", "nan"] else x)
                    
                    df_grafico_sistema = df_sistemas_sprint.groupby('sistema').size().reset_index(name='quantidade')
                    df_grafico_sistema = df_grafico_sistema.sort_values(by='quantidade', ascending=False)
                    
                    col_sys1, col_sys2 = st.columns([2, 3])
                    
                    with col_sys1:
                        base_pizza = alt.Chart(df_grafico_sistema).encode(
                            theta=alt.Theta("quantidade:Q", stack=True),
                            color=alt.Color("sistema:N", title="Sistema", scale=alt.Scale(scheme="category20"))
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
                else:
                    st.warning("Coluna 'sistema' não disponível para montar o gráfico.")
            else:
                st.info("Nenhum dado encontrado para analisar os sistemas.")

            st.divider()
            st.subheader("Itens por Status")

            frames_status = []
            if not df_backlog_filtrado.empty: frames_status.append(df_backlog_filtrado)
            if not df_filtrado.empty: frames_status.append(df_filtrado)

            if frames_status:
                df_status_sprint = pd.concat(frames_status, ignore_index=True)
                
                if 'status' in df_status_sprint.columns:
                    df_status_sprint['status'] = df_status_sprint['status'].fillna("Desconhecido")
                    
                    
                    df_status_sprint = df_status_sprint[df_status_sprint['status'] != '6.0 Concluído']
                    
                    df_grafico_status = df_status_sprint.groupby('status').size().reset_index(name='quantidade')
                    
                    df_grafico_status = df_grafico_status.sort_values(by='status', ascending=True)
                    
                    col_st1, col_st2 = st.columns([3, 2])
                    
                    with col_st1:
                        altura_status = max(320, len(df_grafico_status) * 30)

                        barras_status = alt.Chart(df_grafico_status).mark_bar(color='#4CA6FF', cornerRadiusEnd=4).encode(
                            x=alt.X('quantidade:Q', title='Quantidade de Itens', axis=alt.Axis(grid=False)),
                            y=alt.Y('status:N', sort='ascending', title=''),
                            tooltip=['status', 'quantidade']
                        )
                        
                        textos_status = barras_status.mark_text(align='left', baseline='middle', dx=3, color='white').encode(text='quantidade:Q')
                        
                        st.altair_chart((barras_status + textos_status).properties(height=altura_status), use_container_width=True, theme="streamlit")
                        
                    with col_st2:
                        st.write("**Distribuição do Fluxo**")
                        
                        total_st = df_grafico_status['quantidade'].sum()
                        df_grafico_status['porcentagem'] = (df_grafico_status['quantidade'] / total_st) * 100
                        
                        st.dataframe(
                            df_grafico_status,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "status": "Fase (Status)",
                                "quantidade": "Qtd",
                                "porcentagem": st.column_config.ProgressColumn(
                                    "% do Total",
                                    format="%d%%",
                                    min_value=0,
                                    max_value=100,
                                ),
                            }
                        )
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    with st.expander("Detalhes do Gráfico", expanded=False):
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

           # ========================================================
            # PAINEL DE AVALIAÇÃO: REGRAS DE DATA E BLOQUEIO
            # ========================================================
            st.divider()
            st.subheader(f"Avaliação da {sprint_selecionada.split(' - ')[0]}")
            
            with st.container(border=True):
                lista_colaboradores_fixa = ["Castellar", "Daniel", "Eder", "Fernando", "Sergio", "Victor"]
                
                row_sprint_info = df_sprints[df_sprints['id'] == id_sprint_selecionada].iloc[0]
                dt_fim_sprint = row_sprint_info['data_fim']
                if isinstance(dt_fim_sprint, str):
                    dt_fim_sprint = datetime.strptime(dt_fim_sprint, "%Y-%m-%d").date()
                
                hoje = datetime.now().date()
                sprint_encerrada = hoje > dt_fim_sprint

                try:
                    # CORREÇÃO 1: ttl=0 para garantir leitura em tempo real e evitar falsos positivos do cache
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
                                    # CORREÇÃO 2: ON DUPLICATE KEY UPDATE para evitar o erro de IntegrityError
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

            # ========================================================
            # EXPANDER: EDIÇÃO RETROATIVA (CORREÇÕES)
            # ========================================================
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
            st.subheader("Evolução da Qualidade (Média das notas)")
            st.write("Acompanhamento das notas médias atribuída para cada sprint.")

            try:
                query_historico_notas = """
                    SELECT s.DESCRICAO as Sprint, a.NOME_GESTOR as Gestor, a.NOTA as Nota, s.DATA_INICIO
                    FROM TB_SPRINT_AVALIACAO a
                    JOIN TB_SPRINT s ON a.ID_SPRINT = s.ID_SPRINT
                    ORDER BY s.DATA_INICIO ASC
                """
                df_tendencia_raw = conn.query(query_historico_notas, ttl="10m")

                if not df_tendencia_raw.empty:
                    df_media_sprint = df_tendencia_raw.groupby('Sprint')['Nota'].mean().reset_index()
                    df_media_sprint.rename(columns={'Nota': 'Media'}, inplace=True)

                    chart_tendencia = alt.Chart(df_media_sprint).mark_line(
                        color='#4CA6FF',
                        strokeWidth=3,
                        point=alt.OverlayMarkDef(size=80, color='#4CA6FF', fill='white')
                    ).encode(
                        x=alt.X('Sprint:N', sort=None, title="Sprints Anteriores"),
                        y=alt.Y('Media:Q', title="Nota Média (0-5)", scale=alt.Scale(domain=[0, 5])),
                        tooltip=['Sprint', alt.Tooltip('Media:Q', format='.1f', title='Nota Média')]
                    ).properties(height=350)

                    st.altair_chart(chart_tendencia, use_container_width=True, theme="streamlit")
                    with st.expander("Ver comparativo detalhado (Notas por participante)"):
                        
                        df_pivot = df_tendencia_raw.pivot_table(
                            index='Colaborador',
                            columns='Sprint',
                            values='Nota',
                            aggfunc='first'
                        )

                        linha_media = df_pivot.mean().round(1)

                        df_pivot = df_pivot.round(1)

                        df_pivot = df_pivot.fillna("-")

                        df_exibicao = df_pivot.copy()
                        df_exibicao.loc['MÉDIA FINAL'] = linha_media

                        df_exibicao.loc['MÉDIA FINAL'] = df_exibicao.loc['MÉDIA FINAL'].apply(lambda x: f"{x:.1f}" if isinstance(x, (int, float)) else x)

                        df_exibicao = df_exibicao.reset_index()

                        st.dataframe(df_exibicao, use_container_width=True, hide_index=True)
                        
                else:
                    st.info("Ainda não há avaliações suficientes registradas no banco para gerar o gráfico de evolução.")
                    
            except Exception as e:
                st.error(f"Erro ao processar histórico de médias: {e}")
                    
        else:
            st.info("Nenhum item encontrado no backlog para exibir clientes.")

    else:
        st.warning("Vá à aba 'Gerenciar Sprints' e adicione a sua primeira Sprint!")