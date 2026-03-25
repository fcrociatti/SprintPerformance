import streamlit as st
import pandas as pd
import altair as alt
from supabase import create_client, Client
from datetime import timedelta, datetime
from somaCopia import executar_extracao


SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(layout="wide", page_title="Dashboard de Sprints DDS")
st.title("📊 Sprint Performance  - DDS ")

# ==========================================
# CARREGAMENTO GLOBAL DOS DADOS
# ==========================================
@st.cache_data(ttl=600)
def carregar_issues():
    response = supabase.table("sprint_details").select("*").execute()
    return pd.DataFrame(response.data)

@st.cache_data(ttl=600)
def carregar_sprints():
    response = supabase.table("sprints_master").select("*").order("data_inicio", desc=True).execute()
    return pd.DataFrame(response.data)

@st.cache_data(ttl=600)
def carregar_backlog():
    response = supabase.table("sprint_backlog").select("*").execute()
    return pd.DataFrame(response.data)

df_issues = carregar_issues()
df_sprints = carregar_sprints()
df_backlog = carregar_backlog()

# Tratamento de segurança e criação do Nome de Exibição
if not df_sprints.empty:
    if 'descricao' not in df_sprints.columns:
        df_sprints['descricao'] = "Sem Descrição"
    else:
        df_sprints['descricao'] = df_sprints['descricao'].fillna("Sem Descrição")
    
    df_sprints['nome_exibicao'] = df_sprints['descricao'] + " - " + df_sprints['nome_sprint']


aba_dashboard,  aba_sincronizacao, aba_historico = st.tabs(["📈 Visão da Sprint",  "⚙️ Gerenciar Sprints", "📊 Histórico & Desempenho"])




# ==========================================
# ABA 2: HISTÓRICO E DESEMPENHO (NOVA)
# ==========================================
with aba_historico:
    st.subheader(" Avaliação de Desempenho (Múltiplas Sprints)")
    st.write("Selecione um período para analisar a evolução e a consistência das entregas da equipe.")

    if not df_sprints.empty and not df_issues.empty:
        # Prepara a lista de sprints e sugere as últimas 5 por padrão
        lista_sprints_hist = df_sprints['nome_exibicao'].tolist()
        sprints_padrao = lista_sprints_hist[:5] if len(lista_sprints_hist) >= 5 else lista_sprints_hist
        
        # Filtros Lado a Lado
        col_f1, col_f2 = st.columns(2)
        sprints_selecionadas_hist = col_f1.multiselect("1. Selecione as Sprints:", lista_sprints_hist, default=sprints_padrao)
        
        if sprints_selecionadas_hist:
            ids_sprints_hist = df_sprints[df_sprints['nome_exibicao'].isin(sprints_selecionadas_hist)]['id'].tolist()
            
            # Mescla as issues com as datas da sprint para ordenar corretamente o gráfico
            df_issues_completo = df_issues.merge(df_sprints[['id', 'descricao', 'data_inicio']], left_on='sprint_id', right_on='id')
            df_hist = df_issues_completo[df_issues_completo['sprint_id'].isin(ids_sprints_hist)]
            
            devs_disp_hist = sorted(df_hist['responsavel'].unique())
            devs_selecionados_hist = col_f2.multiselect("2. Filtrar Desenvolvedores:", devs_disp_hist, default=devs_disp_hist)
            
            df_hist = df_hist[df_hist['responsavel'].isin(devs_selecionados_hist)]
            
            if not df_hist.empty:
                # Resumo do Período
                total_periodo = df_hist['pontos'].sum()
                
                # Calcula a média dividindo o total pela quantidade de sprints selecionadas
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
                
                # Gráficos de Evolução e Ranking
                col_graf_evo, col_graf_rank = st.columns([3, 2])
                
                with col_graf_evo:
                    st.write("**📈 Evolução de Pontos por Sprint**")
                    df_linha = df_hist.groupby(['descricao', 'data_inicio', 'responsavel'])['pontos'].sum().reset_index()
                    ordem_cronologica = df_linha.sort_values('data_inicio')['descricao'].unique().tolist()
                    
                    grafico_linha = alt.Chart(df_linha).mark_line(point=True, strokeWidth=3).encode(
                        x=alt.X('descricao:N', sort=ordem_cronologica, title='Sprints', axis=alt.Axis(labelAngle=0)),
                        y=alt.Y('pontos:Q', title='Pontos Entregues'),
                        color=alt.Color('responsavel:N', title='Desenvolvedor', scale=alt.Scale(scheme='category20')),
                        tooltip=['responsavel', 'descricao', 'pontos']
                    ).properties(height=350)
                    
                    st.altair_chart(grafico_linha, use_container_width=True, theme="streamlit")
                
                with col_graf_rank:
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
            btn_sincronizar = st.form_submit_button("🚀 Iniciar Busca no Jira")
            
            if btn_sincronizar:
                if not descricao_input: st.warning("⚠️ Por favor, preencha a identificação da Sprint.")
                elif (dt_fim - dt_inicio).days != 13: st.error(f"❌ Erro: A sprint deve ter exatos 14 dias.")
                else:
                    sobreposicao = False
                    sprint_conflito = ""
                    if not df_sprints.empty:
                        for _, row in df_sprints.iterrows():
                            sp_ini = datetime.strptime(row['data_inicio'], "%Y-%m-%d").date()
                            sp_fim = datetime.strptime(row['data_fim'], "%Y-%m-%d").date()
                            if dt_inicio <= sp_fim and dt_fim >= sp_ini:
                                sobreposicao = True
                                sprint_conflito = row['descricao']
                                break
                    if sobreposicao: st.error(f"❌ Sobreposição detetada com: **{sprint_conflito}**.")
                    else:
                        with st.spinner('A conectar ao Jira...'):
                            sucesso, mensagem = executar_extracao(dt_inicio, dt_fim, descricao_input)
                            if sucesso:
                                st.success(f"✅ Dados importados!")
                                st.cache_data.clear()
                            else: st.error(f"❌ Falha: {mensagem}")

    else:
        st.write("Busque os dados mais recentes de uma Sprint que já está no banco.")
        if not df_sprints.empty:
            sprint_para_atualizar = st.selectbox("Selecione a Sprint para Atualizar", df_sprints['nome_exibicao'].tolist())
            row_sprint = df_sprints[df_sprints['nome_exibicao'] == sprint_para_atualizar].iloc[0]
            with st.form("form_sync_atualiza"):
                st.info(f"O sistema irá consultar o Jira novamente para o período de **{row_sprint['data_inicio']}** até **{row_sprint['data_fim']}**.")
                btn_atualizar = st.form_submit_button("🔄 Atualizar Dados")
                
                if btn_atualizar:
                    dt_inicio_upd = datetime.strptime(row_sprint['data_inicio'], "%Y-%m-%d").date()
                    dt_fim_upd = datetime.strptime(row_sprint['data_fim'], "%Y-%m-%d").date()
                    desc_upd = row_sprint['descricao']
                    with st.spinner(f"Atualizando dados da {sprint_para_atualizar}..."):
                        sucesso, mensagem = executar_extracao(dt_inicio_upd, dt_fim_upd, desc_upd)
                        if sucesso:
                            st.success(f"✅ Dados atualizados!")
                            st.cache_data.clear()
                        else: st.error(f"❌ Falha: {mensagem}")
        else: st.warning("Nenhuma Sprint cadastrada para atualizar.")



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

        # ==========================================
        # SECÇÃO 1: RAIO-X DO BACKLOG
        # ==========================================
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
                st.markdown("#### 📌 Marcadores Principais (Jira)")
                colA, colB, colC = st.columns(3)
                colA.metric("Total de Itens", total_itens)
                colB.metric("Sustentação", itens_sust, f"{(itens_sust/total_itens*100):.1f}%")
                colC.metric("Desenvolvimento", itens_desv, f"{(itens_desv/total_itens*100):.1f}%")

            col_eq1, col_eq2 = st.columns(2)

            with col_eq1:
                with st.container(border=True):
                    st.markdown("#### 💼 Composição: Gestão (Foco)")
                    st.metric("Total Foco Sérgio+Eder", sergio + eder)
                    st.divider()

                    nomes_principais = ["Anderson", "Fernando", "Gustavo", "Nathan", "Daniel", "Eder", "Sergio"]
                    df_outros = df_backlog_filtrado[~df_backlog_filtrado['responsavel'].str.contains('|'.join(nomes_principais), case=False, na=False)]
                    todos_os_outros = len(df_outros)

                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Sérgio", sergio)
                    c2.metric("Eder", eder)
                    c3.metric("Daniel", daniel)
                    c4.metric("Outros", todos_os_outros)

                    st.markdown("<br>", unsafe_allow_html=True)
                    df_gest_donut = pd.DataFrame({'categoria': ["Sérgio", "Eder", "Daniel", "Todos os Outros"],'quantidade': [sergio, eder, daniel, todos_os_outros]})
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
                    if not df_an_comp.empty:
                        bar_comp = alt.Chart(df_an_comp).mark_bar(color='#CC6677').encode(
                            x=alt.X('quantidade:Q', title='Qtd de Itens', axis=alt.Axis(grid=False)),
                            y=alt.Y('responsavel:N', sort='-x', title=''),
                            tooltip=['responsavel', 'quantidade']
                        )
                        label_comp = bar_comp.mark_text(align='left', baseline='middle', dx=5, color='white').encode(text='quantidade:Q')
                        st.altair_chart((bar_comp + label_comp).properties(height=200), use_container_width=True, theme="streamlit")
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

        # ==========================================
        # SECÇÃO 2: ENTREGAS
        # ==========================================
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
                st.write("**🏆 Top 10 Entregas por Desenvolvedor**")
                
                df_ranking = df_filtrado.groupby('responsavel')['pontos'].sum().reset_index()
                df_ranking = df_ranking[df_ranking['pontos'] > 0]
                df_ranking = df_ranking.sort_values(by='pontos', ascending=False).head(10)

                if not df_ranking.empty:
                    grafico_barras = alt.Chart(df_ranking).mark_bar(color='#4CA6FF').encode(
                        x=alt.X('pontos:Q', title='Pontos Entregues', axis=alt.Axis(grid=False)),
                        y=alt.Y('responsavel:N', sort='-x', title=''), 
                        tooltip=['responsavel', 'pontos']
                    )
                    textos = grafico_barras.mark_text(align='left', baseline='middle', dx=5, color='white', fontWeight='bold').encode(text='pontos:Q')
                    grafico_final = (grafico_barras + textos).properties(height=350)
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



        # ==========================================
        # BURNDOWN DA SPRINT (TICKETS)
        # ==========================================
        st.divider()
        st.subheader("📉 Burndown da Sprint")

        if not df_backlog_filtrado.empty or not df_filtrado.empty:
            # 1. Total de tickets da Sprint (Pendentes + Entregues)
            total_tickets = len(df_backlog_filtrado) + len(df_filtrado)

            # 2. Resgatar as datas da Sprint atual
            data_ini_str = df_sprints[df_sprints['nome_exibicao'] == sprint_selecionada]['data_inicio'].iloc[0]
            data_fim_str = df_sprints[df_sprints['nome_exibicao'] == sprint_selecionada]['data_fim'].iloc[0]
            data_ini = datetime.strptime(data_ini_str, "%Y-%m-%d").date()
            data_fim = datetime.strptime(data_fim_str, "%Y-%m-%d").date()
            
            qtd_dias = (data_fim - data_ini).days + 1
            dias_sprint = [data_ini + timedelta(days=x) for x in range(qtd_dias)]

            # 3. Contar quantas entregas aconteceram por dia
            df_entregas_bd = df_filtrado.copy()
            entregas_por_dia = {}
            if not df_entregas_bd.empty:
                # Converte ISO para data simples e conta
                df_entregas_bd['data_dt'] = pd.to_datetime(df_entregas_bd['data_conclusao']).dt.date
                entregas_por_dia = df_entregas_bd.groupby('data_dt').size().to_dict()

            # 4. Construir os dados para o Gráfico
            bd_dados = []
            real_restante = total_tickets
            passo_ideal = total_tickets / (qtd_dias - 1) if qtd_dias > 1 else 0
            hoje = datetime.now().date()

            for i, dia in enumerate(dias_sprint):
                ideal_restante = total_tickets - (passo_ideal * i)

                # Subtrai o que foi entregue neste dia específico
                entregues_hoje = entregas_por_dia.get(dia, 0)
                real_restante = real_restante - entregues_hoje

                # Se o dia ainda não chegou (futuro), não desenhamos a linha azul
                linha_real = real_restante if dia <= hoje else None

                bd_dados.append({
                    "Data": dia.strftime("%d/%m"),
                    "Diretriz": round(ideal_restante, 1),
                    "Trabalho Restante": linha_real
                })

            df_burndown = pd.DataFrame(bd_dados)

            # 5. Desenhar o gráfico com Altair
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


       # ==========================================
        # SECÇÃO 3: ITENS POR CLIENTE (NOVA E ÚLTIMA SECÇÃO)
        # ==========================================
        st.divider()
        st.subheader("🏢 Itens por Cliente (Planning)")

        if not df_backlog_filtrado.empty:
            
            # PREVENÇÃO DE ERRO: Garante que a coluna existe mesmo se você ainda não clicou em "Atualizar" na aba de Gestão
            if 'data_criacao' not in df_backlog_filtrado.columns:
                df_backlog_filtrado['data_criacao'] = "2000-01-01"

            # 1. Descobrir a data de início da Sprint atual
            data_inicio_sprint = df_sprints[df_sprints['nome_exibicao'] == sprint_selecionada]['data_inicio'].iloc[0]
            
            # 2. Filtrar APENAS os itens criados depois ou no mesmo dia do início da Sprint
            df_clientes_sprint = df_backlog_filtrado[df_backlog_filtrado['data_criacao'] >= data_inicio_sprint].copy()

            col_cli1, col_cli2 = st.columns([2, 3])

            with col_cli1:
                st.write("**Resumo de Carga por Cliente**")
                
                if not df_clientes_sprint.empty:
                    # 3. Conta os itens com o DataFrame já filtrado
                    df_clientes = df_clientes_sprint.groupby('cliente')['issue_key'].count().reset_index()
                    df_clientes.columns = ['Cliente', 'Contagem']
                    df_clientes = df_clientes.sort_values(by='Contagem', ascending=False)
                    
                    # Calcula a porcentagem
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
                    df_clientes = pd.DataFrame(columns=['Cliente']) # Evita erro na coluna 2

            with col_cli2:
                st.write("**Detalhamento de Tickets**")
                
                if not df_clientes_sprint.empty:
                    lista_clientes = ["Todos"] + df_clientes['Cliente'].tolist()
                    cliente_selecionado = st.selectbox("Selecione o Cliente para detalhar:", lista_clientes)

                    if cliente_selecionado != "Todos":
                        # Usa a base já filtrada por data (df_clientes_sprint)
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
