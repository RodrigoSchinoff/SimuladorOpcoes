# main.py
# --- garantir que a raiz do projeto está no sys.path ---
import os, sys
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
# -------------------------------------------------------

from services.api import buscar_opcoes_ativo, buscar_detalhes_opcao
from simulacoes.long_straddle import simular_long_straddle
from core.app_core import atualizar_e_screener_ls


# Função de carga para o DB (opcional)
try:
    from etl.carregar_opcoes_db import inserir_opcoes_do_ativo
except Exception:
    inserir_opcoes_do_ativo = None  # caso ainda não tenha criado o módulo


def menu():
    print("\n=== Menu ===")
    print("1 - Buscar opções por ativo")
    print("2 - Buscar detalhes de uma opção específica")
    print("3 - Simular Long Straddle")
    print("4 - Carregar opções por ativo PARA O BANCO (opcoes_do_ativo)")
    print("5 - Screener LS por ticker e vencimento")
    print("0 - Sair")


def input_ticker(prompt: str) -> str:
    t = input(prompt).strip().upper()
    if not t:
        raise ValueError("Ticker não pode ser vazio.")
    return t


def acao_buscar_opcoes():
    ativo_base = input_ticker("Digite o ticker do ativo (ex: PETR4): ")
    try:
        opcoes = buscar_opcoes_ativo(ativo_base)
        if isinstance(opcoes, dict):
            opcoes = [opcoes]
        if not opcoes:
            print("Nenhuma opção retornada.")
            return
        print(f"\nTotal retornado: {len(opcoes)} (mostrando até 50)")
        for i, op in enumerate(opcoes[:50], start=1):
            symbol = op.get("symbol")
            tipo   = op.get("type")
            strike = op.get("strike")
            bid    = op.get("bid")
            print(f"{i:>3}. {symbol} | Tipo: {tipo} | Strike: {strike} | Bid: {bid}")
        if len(opcoes) > 50:
            print("... (resultado truncado)")
    except Exception as e:
        print("Erro ao buscar opções:", e)


def acao_detalhes_opcao():
    symbol_opcao = input_ticker("Digite o código da opção (ex: PETRE100): ")
    try:
        detalhes = buscar_detalhes_opcao(symbol_opcao)
        if not isinstance(detalhes, dict):
            print("Resposta inesperada da API.")
            return
        print("\nDetalhes da opção:")
        for k, v in detalhes.items():
            print(f"- {k}: {v}")
    except Exception as e:
        print("Erro ao buscar detalhes:", e)


def acao_simular_long_straddle():
    try:
        call_symbol = input_ticker("Digite o código da CALL: ")
        put_symbol  = input_ticker("Digite o código da PUT: ")

        call = buscar_detalhes_opcao(call_symbol)
        put  = buscar_detalhes_opcao(put_symbol)

        simular_long_straddle(call, put)  # a função já cuida do gráfico e logs
    except Exception as e:
        print("Erro ao simular:", e)


def acao_carregar_opcoes_db():
    if inserir_opcoes_do_ativo is None:
        print("A função de carga não está disponível. Verifique se criou etl/carregar_opcoes_db.py.")
        return
    ativo_base = input_ticker("Digite o ticker do ativo para carregar no DB (ex: PETR4): ")
    try:
        qtd = inserir_opcoes_do_ativo(ativo_base)
        print(f"✅ Inseridas {qtd} linha(s) na tabela opcoes_do_ativo.")
    except Exception as e:
        print("Erro ao inserir no banco:", e)


def acao_screener_ls_venc():
    import os
    from datetime import datetime

    t = input_ticker("Ticker (ex.: CMIG4): ")
    d = input("Vencimento (YYYY-MM-DD): ").strip()

    # roda: atualiza DB via API e depois screener (lendo só do DB)
    b = atualizar_e_screener_ls(t, d)

    # -------- helpers de formatação --------
    def _fmt_brl(x) -> str:
        try:
            s = f"{float(x):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            return f"R$ {s}"
        except Exception:
            return "R$ 0,00"

    def _pct(x) -> str:
        try:
            return f"{float(x):.2f}%".replace(".", ",")
        except Exception:
            return "0,00%"

    def _linha(r: dict) -> str:
        strike = float(r.get("strike", 0.0))
        be_pct = r.get("be_pct", 0.0)
        be_dn  = float(r.get("be_down", 0.0))
        be_up  = float(r.get("be_up", 0.0))
        spot   = float(r.get("spot", 0.0))
        premio = float(r.get("premium_total", 0.0))  # prêmio por ação

        return (
            f"{r.get('call','?')}/{r.get('put','?')} | "
            f"Strike={strike:.2f} | "
            f"BE%={_pct(be_pct)} | "
            f"BE↓={be_dn:.2f} BE↑={be_up:.2f} | "
            f"Spot={spot:.2f} | "
            f"Prêmio={_fmt_brl(premio)} | "
            f"{r.get('due_date','')}"
        )

    # -------- impressão (mostra até 30 por grupo) --------
    print(f"\n== {t.upper().strip()} / {d} ==")
    MAX_ITENS = 30

    blocos = [
        ("BE ≤ 3,00%", "lt_3"),
        ("3,01% ≤ BE ≤ 5,00%", "btw_3_5"),
        ("BE > 5,00%", "gt_5"),
    ]
    for titulo, chave in blocos:
        itens = b.get(chave, [])
        n_total = len(itens)
        n_show = min(MAX_ITENS, n_total)
        print(f"\n{titulo} — {n_total} pares (mostrando {n_show})")
        for r in itens[:n_show]:
            print(_linha(r))

    # -------- opção de salvar em arquivo texto --------
    salvar = input("\nDeseja salvar o resultado completo em arquivo texto? (S/N): ").strip().upper()
    if salvar == "S":
        # monta conteúdo completo (todos os itens de cada bucket)
        linhas = []
        header = f"Screener Long Straddle — Ticker: {t.upper().strip()} — Vencimento: {d} — Gerado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        linhas.append(header)
        linhas.append("=" * len(header))

        for titulo, chave in blocos:
            itens = b.get(chave, [])
            linhas.append(f"\n{titulo} — {len(itens)} pares")
            for r in itens:
                linhas.append(_linha(r))

        # cria pasta exports/ e grava arquivo
        os.makedirs("exports", exist_ok=True)
        safe_t = t.upper().strip().replace("/", "-")
        fname = f"exports/screener_ls_{safe_t}_{d}_{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
        with open(fname, "w", encoding="utf-8") as f:
            f.write("\n".join(linhas))

        print(f"\n✅ Arquivo salvo em: {fname}")



def main():
    acoes = {
        "1": acao_buscar_opcoes,
        "2": acao_detalhes_opcao,
        "3": acao_simular_long_straddle,
        "4": acao_carregar_opcoes_db,
        "5": acao_screener_ls_venc,
        "0": None,
    }
    while True:
        menu()
        escolha = input("Escolha uma opção: ").strip()
        if escolha == "0":
            print("Saindo...")
            break
        acao = acoes.get(escolha)
        if acao is None:
            print("Opção inválida.")
            continue
        acao()


if __name__ == "__main__":
    main()
