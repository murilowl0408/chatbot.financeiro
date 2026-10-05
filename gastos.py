"""
gastos.py  -  A "cabeça" do bot.

Aqui fica toda a lógica: entender a mensagem, guardar no banco e fazer as somas.
Este arquivo NÃO sabe nada de Telegram. Isso é de propósito: assim dá para testar
a lógica sozinha, e no futuro trocar o Telegram pelo WhatsApp sem mexer aqui.
"""
import re
import shutil
import sqlite3
import unicodedata
from contextlib import closing
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

# O banco fica na mesma pasta deste arquivo, não importa de onde você rode o bot.
DB = Path(__file__).with_name("gastos.db")

# O servidor pode estar em outro fuso; aqui garantimos o horário de Brasília.
FUSO = ZoneInfo("America/Sao_Paulo")

# Formas de pagamento aceitas (sem acento, em minúsculas).
FORMAS = {"credito", "debito", "pix", "dinheiro"}

# Como mostrar cada forma para o usuário (com acento).
NOMES_FORMA = {
    "credito": "crédito",
    "debito": "débito",
    "pix": "pix",
    "dinheiro": "dinheiro",
    None: "não informado",
}

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
         "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


# ----------------------------------------------------------------------
# 1) ENTENDER A MENSAGEM
# ----------------------------------------------------------------------
def tirar_acentos(texto: str) -> str:
    """'Crédito' -> 'Credito'. Facilita comparar palavras."""
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def parece_numero(palavra: str) -> bool:
    """True para '50', '23,90', '1.200,50', 'r$50'."""
    return re.fullmatch(r"(r\$)?\d[\d.,]*", palavra) is not None


def converter_valor(palavra: str) -> int:
    """
    Converte o texto do valor em CENTAVOS (número inteiro).

    Por que centavos? Computadores erram em contas com decimais
    (0.1 + 0.2 dá 0.30000000000000004). Com inteiros, a conta é sempre exata.
    """
    texto = palavra.replace("r$", "")

    if "," in texto:
        # Formato brasileiro: 1.200,50  ->  tira o ponto, troca vírgula por ponto
        texto = texto.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", texto):
        # '1.200' sem vírgula = mil e duzentos (o ponto é separador de milhar)
        texto = texto.replace(".", "")
    # senão, '23.90' fica como está (ponto decimal)

    try:
        reais = Decimal(texto)
    except InvalidOperation:
        raise ValueError("Não consegui entender o valor. Exemplo: comida 50")

    centavos = int((reais * 100).to_integral_value())
    if centavos <= 0:
        raise ValueError("O valor precisa ser maior que zero.")
    return centavos


def entender_mensagem(texto: str):
    """
    Transforma 'uber 23,90 pix' em ('uber', 2390, 'pix').

    Regras:
      - o ÚLTIMO número da mensagem é o valor
      - se aparecer credito/debito/pix/dinheiro, é a forma de pagamento
      - o que sobrar é a categoria
    """
    palavras = tirar_acentos(texto.lower()).split()
    palavras = [p for p in palavras if p != "r$"]   # ignora "r$" solto

    # acha a posição do último número
    posicao_valor = None
    for i, palavra in enumerate(palavras):
        if parece_numero(palavra):
            posicao_valor = i
    if posicao_valor is None:
        raise ValueError("Não achei o valor. Exemplo: comida 50")

    valor = converter_valor(palavras[posicao_valor])

    forma = None
    categoria_palavras = []
    for i, palavra in enumerate(palavras):
        if i == posicao_valor:
            continue
        if palavra in FORMAS:
            forma = palavra
        else:
            categoria_palavras.append(palavra)

    categoria = " ".join(categoria_palavras).strip()
    if not categoria:
        raise ValueError("Faltou a categoria. Exemplo: comida 50")

    return categoria, valor, forma


# ----------------------------------------------------------------------
# 2) BANCO DE DADOS (SQLite: um arquivo só, sem instalar nada)
# ----------------------------------------------------------------------
def _conectar():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row   # permite ler colunas pelo nome
    return con


def criar_tabela():
    """Cria a tabela na primeira vez. Se já existe, não faz nada."""
    with closing(_conectar()) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS gastos (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                data            TEXT    NOT NULL,   -- '2026-10-03 14:30:00'
                categoria       TEXT    NOT NULL,
                valor_centavos  INTEGER NOT NULL,
                forma           TEXT                -- credito/debito/pix/dinheiro/NULL
            )
        """)
        con.commit()


def adicionar(categoria: str, centavos: int, forma):
    agora = datetime.now(FUSO).strftime("%Y-%m-%d %H:%M:%S")
    with closing(_conectar()) as con:
        # Os "?" são preenchidos pelos valores da tupla. NUNCA monte SQL
        # juntando texto na mão: isso abre brecha para ataques (SQL injection).
        con.execute(
            "INSERT INTO gastos (data, categoria, valor_centavos, forma) VALUES (?, ?, ?, ?)",
            (agora, categoria, centavos, forma),
        )
        con.commit()


def mes_atual():
    agora = datetime.now(FUSO)
    return agora.year, agora.month


def _chave_mes(ano: int, mes: int) -> str:
    return f"{ano:04d}-{mes:02d}"        # '2026-10'


# ----------------------------------------------------------------------
# 3) CONSULTAS
# ----------------------------------------------------------------------
def total_do_mes(ano: int, mes: int) -> int:
    with closing(_conectar()) as con:
        linha = con.execute(
            "SELECT COALESCE(SUM(valor_centavos), 0) AS total "
            "FROM gastos WHERE strftime('%Y-%m', data) = ?",
            (_chave_mes(ano, mes),),
        ).fetchone()
        return linha["total"]


def total_por_categoria(ano: int, mes: int):
    with closing(_conectar()) as con:
        linhas = con.execute(
            "SELECT categoria, SUM(valor_centavos) AS total FROM gastos "
            "WHERE strftime('%Y-%m', data) = ? "
            "GROUP BY categoria ORDER BY total DESC",
            (_chave_mes(ano, mes),),
        ).fetchall()
        return [(l["categoria"], l["total"]) for l in linhas]


def total_por_forma(ano: int, mes: int):
    with closing(_conectar()) as con:
        linhas = con.execute(
            "SELECT forma, SUM(valor_centavos) AS total FROM gastos "
            "WHERE strftime('%Y-%m', data) = ? "
            "GROUP BY forma ORDER BY total DESC",
            (_chave_mes(ano, mes),),
        ).fetchall()
        return [(l["forma"], l["total"]) for l in linhas]


def ultimo_gasto():
    with closing(_conectar()) as con:
        linha = con.execute("SELECT * FROM gastos ORDER BY id DESC LIMIT 1").fetchone()
        return dict(linha) if linha else None


def apagar_ultimo():
    """Apaga o último registro e devolve o que foi apagado (ou None)."""
    gasto = ultimo_gasto()
    if gasto is None:
        return None
    with closing(_conectar()) as con:
        con.execute("DELETE FROM gastos WHERE id = ?", (gasto["id"],))
        con.commit()
    return gasto


# ----------------------------------------------------------------------
# 4) FORMATAÇÃO (deixar bonito para mostrar no chat)
# ----------------------------------------------------------------------
def formatar_valor(centavos: int) -> str:
    """123456 -> 'R$ 1.234,56'"""
    reais, resto = divmod(centavos, 100)
    return f"R$ {reais:,}".replace(",", ".") + f",{resto:02d}"


def formatar_data(texto: str) -> str:
    """'2026-10-03 14:30:00' -> '03/10/2026 às 14:30'"""
    return datetime.strptime(texto, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y às %H:%M")


# ----------------------------------------------------------------------
# 5) PERÍODOS (mês e ano) E LIMPEZA
# ----------------------------------------------------------------------
# 'fevereiro' -> 2, 'fev' -> 2, 'marco' -> 3 (já sem acento)
NOME_DO_MES = {}
for _i, _nome in enumerate(MESES, start=1):
    _sem_acento = tirar_acentos(_nome)
    NOME_DO_MES[_sem_acento] = _i
    NOME_DO_MES[_sem_acento[:3]] = _i


def entender_periodo(argumentos):
    """
    Entende o que a pessoa escreveu depois do comando e devolve (ano, mes).

      []                    -> mês atual
      ['2']                 -> fevereiro deste ano
      ['fevereiro']         -> fevereiro deste ano
      ['fev', '2026']       -> fevereiro de 2026
      ['2/2026']            -> fevereiro de 2026
    """
    ano_atual, mes_atual_ = mes_atual()
    ano, mes = None, None

    for arg in argumentos:
        arg = tirar_acentos(arg.lower())
        if "/" in arg:                       # formato 2/2026
            parte_mes, _, parte_ano = arg.partition("/")
            if not (parte_mes.isdigit() and parte_ano.isdigit()):
                raise ValueError("Não entendi o período. Exemplo: /resumo fevereiro 2026")
            mes, ano = int(parte_mes), int(parte_ano)
        elif arg in NOME_DO_MES:
            mes = NOME_DO_MES[arg]
        elif arg.isdigit():
            numero = int(arg)
            if 1 <= numero <= 12:
                mes = numero
            elif 2000 <= numero <= 2100:
                ano = numero
            else:
                raise ValueError("Não entendi o período. Exemplo: /resumo fevereiro 2026")
        else:
            raise ValueError("Não entendi o período. Exemplo: /resumo fevereiro 2026")

    if mes is None and ano is None:
        return ano_atual, mes_atual_
    if mes is None:
        raise ValueError(f"Para ver o ano inteiro use /ano {ano}")
    if not 1 <= mes <= 12:
        raise ValueError("O mês precisa ser de 1 a 12.")
    return (ano or ano_atual), mes


def total_por_mes_do_ano(ano: int):
    """Lista [(mes, total), ...] só dos meses que têm gasto."""
    with closing(_conectar()) as con:
        linhas = con.execute(
            "SELECT CAST(strftime('%m', data) AS INTEGER) AS mes, SUM(valor_centavos) AS total "
            "FROM gastos WHERE strftime('%Y', data) = ? GROUP BY mes ORDER BY mes",
            (f"{ano:04d}",),
        ).fetchall()
        return [(l["mes"], l["total"]) for l in linhas]


def contar_gastos() -> int:
    with closing(_conectar()) as con:
        return con.execute("SELECT COUNT(*) FROM gastos").fetchone()[0]


def limpar_tudo():
    """
    Apaga todos os gastos, mas ANTES salva uma cópia de segurança do banco.
    Devolve (quantos_apagados, nome_do_backup).
    """
    quantidade = contar_gastos()
    if quantidade == 0:
        return 0, None

    carimbo = datetime.now(FUSO).strftime("%Y%m%d_%H%M%S")
    backup = DB.with_name(f"gastos_backup_{carimbo}.db")
    shutil.copy2(DB, backup)

    with closing(_conectar()) as con:
        con.execute("DELETE FROM gastos")
        con.commit()
    return quantidade, backup.name