"""Reprocessa a fila real (TB_SPRINT_FILA_ESTADO) pelo histórico do Jira.

Uso (na pasta do projeto):
    python reprocessar_fila.py              -> as 7 sprints mais recentes (atual + 6 anteriores, para as médias)
    python reprocessar_fila.py 10           -> as 10 mais recentes
    python reprocessar_fila.py "Sprint 58"  -> só a sprint com essa descrição

Só LÊ do Jira. No banco, apaga e regrava apenas TB_SPRINT_FILA_ESTADO das sprints processadas.
Não gera snapshot e não atualiza nada no Jira (diferente da sincronização de "Gerenciar Sprints").
"""
import sys
import pandas as pd
from sqlalchemy import text
import somaCopia

arg = sys.argv[1] if len(sys.argv) > 1 else "7"

with somaCopia.conn.session as s:
    if arg.isdigit():
        linhas = s.execute(text(
            "SELECT ID_SPRINT, DESCRICAO, DATA_INICIO, DATA_FIM FROM TB_SPRINT ORDER BY DATA_INICIO DESC LIMIT :n"
        ), {"n": int(arg)}).fetchall()
    else:
        linhas = s.execute(text(
            "SELECT ID_SPRINT, DESCRICAO, DATA_INICIO, DATA_FIM FROM TB_SPRINT WHERE DESCRICAO = :d"
        ), {"d": arg}).fetchall()
sprints = pd.DataFrame(linhas, columns=["id", "descricao", "inicio", "fim"])

if sprints.empty:
    print(f"Nenhuma sprint encontrada para '{arg}'.")

for _, sp in sprints.iterrows():
    inicio = pd.to_datetime(sp["inicio"]).date()
    fim = pd.to_datetime(sp["fim"]).date()
    print(f"{sp['descricao']} ({inicio:%d/%m} a {fim:%d/%m})... ", end="", flush=True)
    try:
        ok, msg = somaCopia.reconstruir_fila_sprint(int(sp["id"]), inicio, fim)
        print(msg)
    except Exception as e:
        print(f"ERRO: {e}")
