"""
estruturas_dados.py
---------------------------------------------------------------
Estruturas de dados aplicadas ao SIFSM e o PORQUÊ de cada uma:

| Estrutura                 | Uso no sistema                              | Por que ela?                                   |
|---------------------------|---------------------------------------------|------------------------------------------------|
| Lista / vetor (NumPy)     | séries de leituras e simulação              | acesso por índice e cálculo vetorizado         |
| Fila FIFO (deque)         | solicitações da tripulação                  | ordem de chegada justa; O(1) nas duas pontas   |
| Fila de prioridade (heap) | alertas gerados pela regra booleana         | o alerta mais grave sai primeiro: O(log n)     |
| Pilha (LIFO)              | histórico de operações + "desfazer"         | a última ação é a primeira a ser desfeita      |
| Tabela hash (própria)     | busca rápida de sensor/módulo por código    | busca média O(1) em vez de varrer a lista      |
| Grafo (lista de adjacência)| rede de energia/dados entre os módulos      | rotas (BFS), impacto de falhas (DFS)           |
"""

import heapq
from collections import deque
from itertools import count


# ===============================================================
# 1) FILA FIFO - solicitações da tripulação / chamados de manutenção
# ===============================================================
class FilaSolicitacoes:
    def __init__(self):
        self._fila = deque()

    def enfileirar(self, solicitacao: dict):
        self._fila.append(solicitacao)            # entra no fim

    def atender(self) -> dict | None:
        return self._fila.popleft() if self._fila else None   # sai do início

    def espiar(self):
        return self._fila[0] if self._fila else None

    def __len__(self):
        return len(self._fila)

    def listar(self) -> list[dict]:
        return list(self._fila)


# ===============================================================
# 2) FILA DE PRIORIDADE (heap mínimo) - alertas operacionais
#    prioridade 1 = mais urgente. Empate -> ordem de chegada.
# ===============================================================
class FilaPrioridadeAlertas:
    def __init__(self):
        self._heap = []
        self._contador = count()                  # desempate estável

    def inserir(self, prioridade: int, alerta: dict):
        heapq.heappush(self._heap, (prioridade, next(self._contador), alerta))

    def remover_mais_urgente(self) -> dict | None:
        return heapq.heappop(self._heap)[2] if self._heap else None

    def __len__(self):
        return len(self._heap)

    def em_ordem(self) -> list[dict]:
        return [a for _, _, a in sorted(self._heap)]


# ===============================================================
# 3) PILHA - histórico de operações CRUD com "desfazer"
# ===============================================================
class PilhaHistorico:
    def __init__(self, limite: int = 50):
        self._pilha = []
        self.limite = limite

    def empilhar(self, operacao: str, dados: dict):
        """operacao: CADASTRO | ALTERACAO | EXCLUSAO; dados: estado ANTERIOR."""
        self._pilha.append({"operacao": operacao, "dados": dados})
        if len(self._pilha) > self.limite:        # evita crescer sem limite
            self._pilha.pop(0)

    def desempilhar(self) -> dict | None:
        return self._pilha.pop() if self._pilha else None

    def topo(self):
        return self._pilha[-1] if self._pilha else None

    def __len__(self):
        return len(self._pilha)

    def listar(self) -> list[dict]:
        return list(reversed(self._pilha))        # topo primeiro


# ===============================================================
# 4) TABELA HASH com encadeamento (implementação própria, como no
#    capítulo de estruturas). Chave = código do sensor/módulo.
# ===============================================================
class TabelaHash:
    def __init__(self, tamanho: int = 17):        # tamanho primo espalha melhor
        self.tamanho = tamanho
        self.baldes = [[] for _ in range(tamanho)]
        self.colisoes = 0

    def _hash(self, chave: str) -> int:
        # hash polinomial simples (base 31) - mesmo princípio usado em C/Java
        h = 0
        for ch in chave:
            h = (h * 31 + ord(ch)) % self.tamanho
        return h

    def inserir(self, chave: str, valor):
        chave = chave.strip().upper()
        balde = self.baldes[self._hash(chave)]
        for par in balde:
            if par[0] == chave:                   # atualiza se já existe
                par[1] = valor
                return
        if balde:
            self.colisoes += 1
        balde.append([chave, valor])

    def buscar(self, chave: str):
        for k, v in self.baldes[self._hash(chave.strip().upper())]:
            if k == chave.strip().upper():
                return v
        return None

    def remover(self, chave: str) -> bool:
        chave = chave.strip().upper()
        balde = self.baldes[self._hash(chave)]
        for i, (k, _) in enumerate(balde):
            if k == chave:
                balde.pop(i)
                return True
        return False

    def ocupacao(self) -> str:
        usados = sum(1 for b in self.baldes if b)
        return f"{usados}/{self.tamanho} baldes usados, {self.colisoes} colisões"


# ===============================================================
# 5) GRAFO não direcionado - rede de energia/dados da colônia
# ===============================================================
class GrafoColonia:
    def __init__(self):
        self.adj: dict[str, list[str]] = {}

    def adicionar_aresta(self, a: str, b: str):
        self.adj.setdefault(a, []).append(b)
        self.adj.setdefault(b, []).append(a)

    def bfs(self, origem: str) -> dict[str, int]:
        """Busca em largura: distância (nº de saltos) da origem a cada módulo.
        Usada para saber a ordem de distribuição de energia a partir da ENE-01."""
        dist = {origem: 0}
        fila = deque([origem])
        while fila:
            atual = fila.popleft()
            for viz in sorted(self.adj.get(atual, [])):
                if viz not in dist:
                    dist[viz] = dist[atual] + 1
                    fila.append(viz)
        return dist

    def caminho(self, origem: str, destino: str) -> list[str] | None:
        """Menor rota (em saltos) entre dois módulos, via BFS com 'pais'."""
        pais = {origem: None}
        fila = deque([origem])
        while fila:
            atual = fila.popleft()
            if atual == destino:
                rota = []
                while atual is not None:
                    rota.append(atual)
                    atual = pais[atual]
                return rota[::-1]
            for viz in sorted(self.adj.get(atual, [])):
                if viz not in pais:
                    pais[viz] = atual
                    fila.append(viz)
        return None

    def dfs(self, origem: str, bloqueado: str | None = None) -> set[str]:
        """Busca em profundidade (iterativa) ignorando um nó com falha."""
        visitados, pilha = set(), [origem]
        while pilha:
            atual = pilha.pop()
            if atual in visitados or atual == bloqueado:
                continue
            visitados.add(atual)
            pilha.extend(v for v in self.adj.get(atual, []) if v not in visitados)
        return visitados

    def impacto_falha(self, no_falho: str, fonte: str = "ENE-01") -> list[str]:
        """Quais módulos perdem conexão com a Central de Energia se 'no_falho' cair?"""
        if no_falho == fonte:
            return sorted(n for n in self.adj if n != fonte)
        alcancados = self.dfs(fonte, bloqueado=no_falho)
        return sorted(n for n in self.adj if n not in alcancados and n != no_falho)

    def pontos_criticos(self, fonte: str = "ENE-01") -> dict[str, list[str]]:
        """Para cada nó, quem fica isolado se ele falhar (análise de resiliência)."""
        return {n: self.impacto_falha(n, fonte) for n in sorted(self.adj)}


def montar_grafo(conexoes: list[list[str]]) -> GrafoColonia:
    g = GrafoColonia()
    for a, b in conexoes:
        g.adicionar_aresta(a, b)
    return g
