"""Resultado de cada informação que o programa tenta ler do aparelho.

Uma leitura nunca vira "campo vazio" sem explicação: ela guarda a situação,
o método usado e o motivo quando não deu certo.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

COLETADO = "Coletado"
NAO_ENCONTRADO = "Não encontrado"  # a consulta funcionou, mas o aparelho não tem o dado
NEGADO = "Acesso negado"  # o sistema recusou a consulta
NAO_SUPORTADO = "Não suportado"  # o aparelho ou a versão não tem o recurso
FALHA = "Falha"  # erro de comunicação ou de processamento
NAO_IMPLEMENTADO = "Não implementado"  # o programa ainda não sabe coletar

GRUPO_APARELHO = "Aparelho"
GRUPO_CHIPS = "Chips e linha"
GRUPO_USUARIO = "Usuário e contas"

PASTA_DE_REGISTROS = Path(__file__).resolve().parent.parent / "registros"

_NEGADO = re.compile(
    r"SecurityException|Permission Denial|Permission denied|requires android\.permission|not allowed to",
    re.IGNORECASE,
)
_NAO_SUPORTADO = re.compile(
    r"Can't find service|Unknown command|No such file|inaccessible or not found|"
    r"does not exist|Unknown option|Could not find provider|not found",
    re.IGNORECASE,
)
_ERRO = re.compile(r"\b(Exception|Error)\b")


@dataclass
class Leitura:
    grupo: str
    item: str
    situacao: str
    valor: str = ""
    metodo: str = ""
    motivo: str = ""

    @property
    def coletada(self):
        return self.situacao == COLETADO


def resumir(texto, limite=160):
    """Primeira linha útil de uma mensagem de erro, sem o rastro técnico."""
    for linha in (texto or "").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("at "):
            return linha[:limite]
    return ""


def problema(resposta):
    """(situação, motivo) se a resposta do celular indica recusa ou falta de suporte; senão None."""
    texto = resposta.tudo
    negado = _NEGADO.search(texto)
    if negado:
        linhas = [l.strip() for l in texto.splitlines() if _NEGADO.search(l)]
        return NEGADO, resumir(linhas[0])
    if not resposta.saida.strip() or resposta.codigo != 0:
        if _NAO_SUPORTADO.search(texto):
            return NAO_SUPORTADO, resumir(resposta.erro or resposta.saida)
        if resposta.erro:
            return FALHA, resumir(resposta.erro)
    elif _ERRO.search(resposta.saida[:400]) and "Row:" not in resposta.saida[:400]:
        return FALHA, resumir(resposta.saida)
    return None


@dataclass
class Registro:
    """Trilha da identificação: vai para a tela, para o PDF e para um arquivo em registros\\."""

    aparelho: str
    leituras: list = field(default_factory=list)

    def anotar(self, grupo, item, situacao, valor="", metodo="", motivo=""):
        leitura = Leitura(grupo, item, situacao, str(valor).strip(), metodo, motivo)
        self.leituras.append(leitura)
        return leitura

    def coletado(self, grupo, item, valor, metodo):
        return self.anotar(grupo, item, COLETADO, valor, metodo)

    def gravar(self):
        """Acrescenta a trilha ao arquivo do dia. Devolve o caminho, ou None se não deu para gravar."""
        try:
            PASTA_DE_REGISTROS.mkdir(exist_ok=True)
            caminho = PASTA_DE_REGISTROS / f"identificacao-{datetime.now():%Y-%m-%d}.log"
            with open(caminho, "a", encoding="utf-8") as arquivo:
                arquivo.write(f"\n=== {datetime.now():%d/%m/%Y %H:%M:%S} | {self.aparelho}\n")
                for l in self.leituras:
                    detalhe = l.valor if l.coletada else l.motivo
                    arquivo.write(f"[{l.situacao}] {l.grupo} / {l.item}: {detalhe} | método: {l.metodo}\n")
            return caminho
        except OSError:
            return None
