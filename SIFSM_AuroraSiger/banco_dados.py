"""
banco_dados.py
---------------------------------------------------------------
Camada de acesso a dados do SIFSM (tabelas, campos, registros e CRUD).

* Banco padrão: Oracle (como nas aulas), ativado com a variável de
  ambiente SIFSM_DB=oracle + ORACLE_USER / ORACLE_PASSWORD / ORACLE_DSN.
* Se o Oracle não estiver configurado ou a conexão falhar, o sistema
  usa SQLite (biblioteca padrão do Python, arquivo banco_aurora_siger.db),
  com a MESMA estrutura de tabelas -> o avaliador consegue executar
  o projeto sem precisar de credenciais.

Todas as instruções SQL usam "bind variables" nomeadas (:nome), que
funcionam tanto no oracledb quanto no sqlite3 e evitam SQL injection.
"""

import json
import os
import sqlite3

import pandas as pd

try:                                   # oracledb é opcional
    import oracledb
except ImportError:
    oracledb = None

PASTA = os.path.dirname(os.path.abspath(__file__))
ARQ_SQLITE = os.path.join(PASTA, "banco_aurora_siger.db")
ARQ_JSON = os.path.join(PASTA, "dados_aurora_siger.json")

# Colunas de cada tabela (whitelist usada nas alterações dinâmicas)
COLS_MODULO = ["cod_modulo", "nome", "tipo", "critico", "status", "consumo_nominal_kwh"]
COLS_LEITURA = ["id_leitura", "cod_sensor", "cod_modulo", "sol", "ocupacao",
                "temp_externa_c", "temp_interna_c", "luminosidade_lux", "umidade_pct",
                "opacidade_poeira", "consumo_kwh", "presenca", "falha_sensor"]
COLS_ALERTA = ["id_alerta", "cod_modulo", "sol", "nivel", "prioridade", "descricao", "status"]

TIPOS_MODULO = ["HABITACAO", "AGRICULTURA", "LABORATORIO", "COMUNICACAO",
                "SUPORTE_MEDICO", "ARMAZENAMENTO", "ENERGIA"]
STATUS_MODULO = ["ATIVO", "MANUTENCAO", "INATIVO"]

# DDL equivalente ao script_banco.sql, adaptado para SQLite
DDL_SQLITE = [
    """CREATE TABLE IF NOT EXISTS T_SIFSM_MODULO (
        cod_modulo TEXT PRIMARY KEY,
        nome TEXT NOT NULL,
        tipo TEXT NOT NULL,
        critico INTEGER NOT NULL DEFAULT 0 CHECK (critico IN (0,1)),
        status TEXT NOT NULL DEFAULT 'ATIVO' CHECK (status IN ('ATIVO','MANUTENCAO','INATIVO')),
        consumo_nominal_kwh REAL NOT NULL CHECK (consumo_nominal_kwh > 0))""",
    """CREATE TABLE IF NOT EXISTS T_SIFSM_LEITURA (
        id_leitura INTEGER PRIMARY KEY AUTOINCREMENT,
        cod_sensor TEXT NOT NULL,
        cod_modulo TEXT NOT NULL REFERENCES T_SIFSM_MODULO(cod_modulo),
        sol INTEGER NOT NULL CHECK (sol >= 1),
        ocupacao INTEGER NOT NULL DEFAULT 0,
        temp_externa_c REAL, temp_interna_c REAL, luminosidade_lux REAL,
        umidade_pct REAL CHECK (umidade_pct BETWEEN 0 AND 100),
        opacidade_poeira REAL,
        consumo_kwh REAL NOT NULL CHECK (consumo_kwh >= 0),
        presenca INTEGER DEFAULT 0 CHECK (presenca IN (0,1)),
        falha_sensor INTEGER DEFAULT 0 CHECK (falha_sensor IN (0,1)))""",
    """CREATE TABLE IF NOT EXISTS T_SIFSM_ALERTA (
        id_alerta INTEGER PRIMARY KEY AUTOINCREMENT,
        cod_modulo TEXT NOT NULL REFERENCES T_SIFSM_MODULO(cod_modulo),
        sol INTEGER NOT NULL, nivel TEXT NOT NULL, prioridade INTEGER NOT NULL,
        descricao TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ABERTO')""",
    "CREATE INDEX IF NOT EXISTS IX_LEITURA_MODULO_SOL ON T_SIFSM_LEITURA (cod_modulo, sol)",
    "CREATE INDEX IF NOT EXISTS IX_LEITURA_SENSOR ON T_SIFSM_LEITURA (cod_sensor)",
]


class RegistroNaoEncontrado(Exception):
    """Erro de negócio: o código/ID informado não existe na tabela."""


# ===============================================================
# Validações (erros de entrada viram ValueError com mensagem clara)
# ===============================================================
def validar_modulo(m: dict) -> dict:
    cod = str(m.get("cod_modulo", "")).strip().upper()
    if len(cod) < 3 or len(cod) > 10:
        raise ValueError("Código do módulo deve ter entre 3 e 10 caracteres (ex.: HAB-02).")
    if not str(m.get("nome", "")).strip():
        raise ValueError("Nome do módulo não pode ficar em branco.")
    tipo = str(m.get("tipo", "")).strip().upper()
    if tipo not in TIPOS_MODULO:
        raise ValueError(f"Tipo inválido. Use um destes: {', '.join(TIPOS_MODULO)}.")
    critico = int(m.get("critico", 0))
    if critico not in (0, 1):
        raise ValueError("Campo 'crítico' aceita apenas 0 (não) ou 1 (sim).")
    status = str(m.get("status", "ATIVO")).strip().upper()
    if status not in STATUS_MODULO:
        raise ValueError(f"Status inválido. Use: {', '.join(STATUS_MODULO)}.")
    nominal = float(m.get("consumo_nominal_kwh"))
    if nominal <= 0:
        raise ValueError("Consumo nominal deve ser maior que zero.")
    return {"cod_modulo": cod, "nome": str(m["nome"]).strip(), "tipo": tipo,
            "critico": critico, "status": status, "consumo_nominal_kwh": nominal}


def validar_leitura(l: dict) -> dict:
    v = dict(l)
    v["cod_modulo"] = str(v["cod_modulo"]).strip().upper()
    v["cod_sensor"] = str(v.get("cod_sensor") or f"SNS-{v['cod_modulo']}").strip().upper()
    v["sol"] = int(v["sol"])
    if v["sol"] < 1:
        raise ValueError("O sol (dia marciano) deve ser >= 1.")
    v["ocupacao"] = int(v.get("ocupacao", 0))
    if v["ocupacao"] < 0:
        raise ValueError("Ocupação não pode ser negativa.")
    v["consumo_kwh"] = float(v["consumo_kwh"])
    if v["consumo_kwh"] < 0:
        raise ValueError("Consumo não pode ser negativo.")
    for campo in ["temp_externa_c", "temp_interna_c", "luminosidade_lux",
                  "umidade_pct", "opacidade_poeira"]:
        v[campo] = float(v.get(campo, 0) or 0)
    if not 0 <= v["umidade_pct"] <= 100:
        raise ValueError("Umidade deve estar entre 0 e 100%.")
    v["presenca"] = int(v.get("presenca", 1 if v["ocupacao"] > 0 else 0))
    v["falha_sensor"] = int(v.get("falha_sensor", 0))
    if v["presenca"] not in (0, 1) or v["falha_sensor"] not in (0, 1):
        raise ValueError("Presença e falha do sensor aceitam apenas 0 ou 1.")
    v.pop("id_leitura", None)          # o ID é sempre gerado pelo banco
    return v


# ===============================================================
# Classe de conexão
# ===============================================================
class BancoAurora:
    def __init__(self):
        self.conn = None
        self.tipo = None          # "oracle" ou "sqlite"

    # ---------------- conexão ----------------
    def conectar(self, forcar_sqlite: bool = False) -> str:
        """Tenta Oracle (se configurado); se falhar, usa SQLite."""
        if not forcar_sqlite and os.getenv("SIFSM_DB", "").lower() == "oracle":
            try:
                if oracledb is None:
                    raise ImportError("pacote 'oracledb' não instalado (pip install oracledb)")
                self.conn = oracledb.connect(
                    user=os.environ["ORACLE_USER"],
                    password=os.environ["ORACLE_PASSWORD"],
                    dsn=os.getenv("ORACLE_DSN", "oracle.fiap.com.br:1521/ORCL"))
            except KeyError as e:
                print(f"[BANCO] Variável de ambiente ausente: {e}. Usando SQLite.")
            except Exception as e:                  # rede, senha, servidor...
                print(f"[BANCO] Falha ao conectar no Oracle ({e}). Usando SQLite.")
            else:
                self.tipo = "oracle"
                return self.tipo
        try:
            self.conn = sqlite3.connect(ARQ_SQLITE)
            self.conn.execute("PRAGMA foreign_keys = ON")    # respeita as FKs
            for ddl in DDL_SQLITE:
                self.conn.execute(ddl)
            self.conn.commit()
        except sqlite3.Error as e:
            raise ConnectionError(f"Não foi possível abrir o banco SQLite: {e}")
        self.tipo = "sqlite"
        return self.tipo

    def fechar(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    # ---------------- utilitários ----------------
    def executar(self, sql: str, params: dict | None = None) -> int:
        """INSERT/UPDATE/DELETE com commit; em erro faz rollback e relança."""
        cur = self.conn.cursor()
        try:
            cur.execute(sql, params or {})
        except Exception:
            self.conn.rollback()
            raise
        else:
            self.conn.commit()
            return cur.rowcount
        finally:
            cur.close()

    def consultar(self, sql: str, params: dict | None = None) -> pd.DataFrame:
        """SELECT -> DataFrame do Pandas (como no capítulo de banco de dados)."""
        cur = self.conn.cursor()
        try:
            cur.execute(sql, params or {})
            colunas = [c[0].lower() for c in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=colunas)
        finally:
            cur.close()

    def _inserir_retornando_id(self, sql: str, params: dict, col_id: str) -> int:
        cur = self.conn.cursor()
        try:
            if self.tipo == "oracle":
                novo_id = cur.var(oracledb.NUMBER)
                cur.execute(sql + f" RETURNING {col_id} INTO :novo_id",
                            {**params, "novo_id": novo_id})
                valor = int(novo_id.getvalue()[0])
            else:
                cur.execute(sql, params)
                valor = cur.lastrowid
        except Exception:
            self.conn.rollback()
            raise
        else:
            self.conn.commit()
            return valor
        finally:
            cur.close()

    # ===========================================================
    # CRUD - MÓDULOS
    # ===========================================================
    def cadastrar_modulo(self, dados: dict) -> str:
        m = validar_modulo(dados)
        self.executar("""INSERT INTO T_SIFSM_MODULO (cod_modulo, nome, tipo, critico, status,
                         consumo_nominal_kwh) VALUES (:cod_modulo, :nome, :tipo, :critico,
                         :status, :consumo_nominal_kwh)""", m)
        return m["cod_modulo"]

    def listar_modulos(self) -> pd.DataFrame:
        return self.consultar("SELECT * FROM T_SIFSM_MODULO ORDER BY cod_modulo")

    def buscar_modulo(self, cod: str) -> dict:
        df = self.consultar("SELECT * FROM T_SIFSM_MODULO WHERE cod_modulo = :c",
                            {"c": cod.strip().upper()})
        if df.empty:
            raise RegistroNaoEncontrado(f"Módulo '{cod}' não encontrado.")
        return df.iloc[0].to_dict()

    def alterar_modulo(self, cod: str, novos: dict) -> dict:
        atual = self.buscar_modulo(cod)                     # garante que existe
        mesclado = validar_modulo({**atual, **novos, "cod_modulo": atual["cod_modulo"]})
        sets = ", ".join(f"{c} = :{c}" for c in COLS_MODULO if c != "cod_modulo")
        self.executar(f"UPDATE T_SIFSM_MODULO SET {sets} WHERE cod_modulo = :cod_modulo", mesclado)
        return atual                                        # devolve o "antes" (p/ desfazer)

    def excluir_modulo(self, cod: str) -> dict:
        atual = self.buscar_modulo(cod)
        qtd = self.consultar("SELECT COUNT(*) AS n FROM T_SIFSM_LEITURA WHERE cod_modulo = :c",
                             {"c": atual["cod_modulo"]}).iloc[0]["n"]
        if qtd > 0:
            raise ValueError(f"O módulo {atual['cod_modulo']} possui {qtd} leituras. "
                             "Exclua as leituras ou altere o status para INATIVO.")
        self.executar("DELETE FROM T_SIFSM_ALERTA WHERE cod_modulo = :c", {"c": atual["cod_modulo"]})
        self.executar("DELETE FROM T_SIFSM_MODULO WHERE cod_modulo = :c", {"c": atual["cod_modulo"]})
        return atual

    # ===========================================================
    # CRUD - LEITURAS DE SENSORES
    # ===========================================================
    def cadastrar_leitura(self, dados: dict) -> int:
        l = validar_leitura(dados)
        self.buscar_modulo(l["cod_modulo"])                 # FK amigável
        cols = [c for c in COLS_LEITURA if c in l]
        sql = (f"INSERT INTO T_SIFSM_LEITURA ({', '.join(cols)}) "
               f"VALUES ({', '.join(':' + c for c in cols)})")
        return self._inserir_retornando_id(sql, {c: l[c] for c in cols}, "id_leitura")

    def listar_leituras(self, cod_modulo: str | None = None, sol: int | None = None) -> pd.DataFrame:
        sql = "SELECT * FROM T_SIFSM_LEITURA WHERE 1 = 1"
        params = {}
        if cod_modulo:
            sql += " AND cod_modulo = :m"
            params["m"] = cod_modulo.strip().upper()
        if sol:
            sql += " AND sol = :s"
            params["s"] = int(sol)
        return self.consultar(sql + " ORDER BY sol, cod_modulo", params)

    def buscar_leitura(self, id_leitura: int) -> dict:
        df = self.consultar("SELECT * FROM T_SIFSM_LEITURA WHERE id_leitura = :i",
                            {"i": int(id_leitura)})
        if df.empty:
            raise RegistroNaoEncontrado(f"Leitura {id_leitura} não encontrada.")
        return df.iloc[0].to_dict()

    def alterar_leitura(self, id_leitura: int, novos: dict) -> dict:
        atual = self.buscar_leitura(id_leitura)
        mesclado = validar_leitura({**atual, **novos})
        cols = [c for c in COLS_LEITURA if c != "id_leitura"]
        sets = ", ".join(f"{c} = :{c}" for c in cols)
        params = {c: mesclado[c] for c in cols}
        params["id_leitura"] = int(id_leitura)
        self.executar(f"UPDATE T_SIFSM_LEITURA SET {sets} WHERE id_leitura = :id_leitura", params)
        return atual

    def excluir_leitura(self, id_leitura: int) -> dict:
        atual = self.buscar_leitura(id_leitura)
        self.executar("DELETE FROM T_SIFSM_LEITURA WHERE id_leitura = :i", {"i": int(id_leitura)})
        return atual

    def restaurar_leitura(self, registro: dict):
        """Reinsere uma leitura com o MESMO id (usado pelo 'desfazer')."""
        params = {c: (int(registro[c]) if c in ("id_leitura", "sol", "ocupacao", "presenca",
                                                  "falha_sensor") else registro[c])
                  for c in COLS_LEITURA}
        self.executar(f"INSERT INTO T_SIFSM_LEITURA ({', '.join(COLS_LEITURA)}) "
                      f"VALUES ({', '.join(':' + c for c in COLS_LEITURA)})", params)

    # ===========================================================
    # ALERTAS
    # ===========================================================
    def registrar_alerta(self, cod_modulo, sol, nivel, prioridade, descricao) -> int:
        return self._inserir_retornando_id(
            """INSERT INTO T_SIFSM_ALERTA (cod_modulo, sol, nivel, prioridade, descricao, status)
               VALUES (:m, :s, :n, :p, :d, 'ABERTO')""",
            {"m": cod_modulo, "s": int(sol), "n": nivel, "p": int(prioridade), "d": descricao[:200]},
            "id_alerta")

    def listar_alertas(self) -> pd.DataFrame:
        return self.consultar("SELECT * FROM T_SIFSM_ALERTA ORDER BY prioridade, id_alerta")

    def limpar_alertas(self):
        self.executar("DELETE FROM T_SIFSM_ALERTA")

    # ===========================================================
    # Carga a partir do arquivo estruturado (JSON)
    # ===========================================================
    def carregar_json(self, caminho: str = ARQ_JSON) -> dict:
        """Recarrega a base: apaga leituras/alertas e insere tudo do JSON."""
        try:
            with open(caminho, encoding="utf-8") as f:
                base = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Arquivo de dados não encontrado: {caminho}")
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON inválido (linha {e.lineno}): {e.msg}")

        self.executar("DELETE FROM T_SIFSM_ALERTA")
        self.executar("DELETE FROM T_SIFSM_LEITURA")
        self.executar("DELETE FROM T_SIFSM_MODULO")
        if self.tipo == "sqlite":                    # reinicia a numeração dos IDs
            self.executar("DELETE FROM sqlite_sequence WHERE name IN ('T_SIFSM_LEITURA', 'T_SIFSM_ALERTA')")
        cur = self.conn.cursor()
        try:
            sql_m = ("INSERT INTO T_SIFSM_MODULO (cod_modulo, nome, tipo, critico, status, "
                     "consumo_nominal_kwh) VALUES (:cod_modulo, :nome, :tipo, :critico, "
                     ":status, :consumo_nominal_kwh)")
            cur.executemany(sql_m, [validar_modulo(m) for m in base["modulos"]])
            cols = [c for c in COLS_LEITURA if c != "id_leitura"]
            sql_l = (f"INSERT INTO T_SIFSM_LEITURA ({', '.join(cols)}) "
                     f"VALUES ({', '.join(':' + c for c in cols)})")
            cur.executemany(sql_l, [{c: l[c] for c in cols} for l in base["leituras"]])
        except Exception:
            self.conn.rollback()
            raise
        else:
            self.conn.commit()
        finally:
            cur.close()
        return {"modulos": len(base["modulos"]), "leituras": len(base["leituras"]),
                "conexoes": base.get("conexoes", []), "solicitacoes": base.get("solicitacoes", [])}

    def base_vazia(self) -> bool:
        return self.consultar("SELECT COUNT(*) AS n FROM T_SIFSM_MODULO").iloc[0]["n"] == 0

    def dataframe_analitico(self) -> pd.DataFrame:
        """JOIN leitura x módulo, usado pela simulação, regressão e agentes."""
        return self.consultar("""
            SELECT l.*, m.nome, m.tipo, m.critico, m.status, m.consumo_nominal_kwh
              FROM T_SIFSM_LEITURA l
              JOIN T_SIFSM_MODULO m ON m.cod_modulo = l.cod_modulo
             ORDER BY l.sol, l.cod_modulo""")


def carregar_auxiliares(caminho: str = ARQ_JSON) -> dict:
    """Lê do JSON os dados que não ficam no banco (grafo e solicitações)."""
    try:
        with open(caminho, encoding="utf-8") as f:
            base = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[AVISO] Não foi possível ler {caminho}: {e}")
        return {"conexoes": [], "solicitacoes": []}
    return {"conexoes": base.get("conexoes", []), "solicitacoes": base.get("solicitacoes", [])}
