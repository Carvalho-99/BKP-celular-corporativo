"""O que cada categoria consegue entregar no aparelho conectado.

Separa três coisas que não são a mesma: o que fica preservado no backup, o que
dá para ler em planilha ou relatório, e o que não é acessível.
"""
from dataclasses import dataclass

from . import adb, arquivos, whatsapp
from .leitura import NEGADO, problema

DISPONIVEL = "Disponível"
PARCIAL = "Parcial"
INDISPONIVEL = "Indisponível"

CATEGORIAS = {
    "arquivos": "Arquivos e mídias",
    "whatsapp": "WhatsApp",
    "contatos": "Contatos",
    "sms": "SMS",
    "chamadas": "Chamadas",
    "apps": "Apps e contas",
}

FILTRO_DE_SMS = (
    "Ficam de fora do relatório as mensagens cujo remetente tem letras (como VIVO ou TIM) "
    "ou tem menos de 8 dígitos (números curtos de serviço). A quantidade excluída e a lista "
    "de remetentes excluídos ficam em dados\\sms_filtro.csv; o texto dessas mensagens não é copiado."
)


@dataclass
class Cobertura:
    chave: str
    situacao: str
    resumo: str  # frase curta para a tela
    preservado: str = ""
    legivel: str = ""
    inacessivel: str = ""

    @property
    def nome(self):
        return CATEGORIAS[self.chave]


def _consulta_de_teste(serial, uri):
    """Consulta que não traz nenhuma linha: serve só para saber se o Android deixa ler."""
    resposta = adb.consultar(f'content query --uri {uri} --projection _id --where "_id<0"', serial)
    return problema(resposta)


def _dados(serial, chave, uri, o_que, inacessivel=""):
    ruim = _consulta_de_teste(serial, uri)
    if ruim:
        motivo = "o Android recusou a leitura" if ruim[0] == NEGADO else ruim[1]
        return Cobertura(chave, INDISPONIVEL, f"Sem acesso: {motivo}", inacessivel=f"{o_que}: {motivo}")
    return Cobertura(
        chave, DISPONIVEL, "Leitura liberada pelo aparelho",
        preservado=f"{o_que}, em planilha (CSV)",
        legivel=f"{o_que}, em planilha e no detalhes.pdf",
        inacessivel=inacessivel,
    )


def android(serial):
    """Levanta a cobertura de cada categoria. Erro em uma não impede as outras."""
    levantadas = {}
    for chave, funcao in (
        ("arquivos", _arquivos), ("whatsapp", _whatsapp), ("contatos", _contatos),
        ("sms", _sms), ("chamadas", _chamadas), ("apps", _apps),
    ):
        try:
            levantadas[chave] = funcao(serial)
        except Exception as e:  # noqa: BLE001 - o motivo precisa aparecer na tela
            levantadas[chave] = Cobertura(
                chave, INDISPONIVEL, f"Não foi possível verificar: {e}", inacessivel=str(e)
            )
    return levantadas


def _arquivos(serial):
    pastas = arquivos.origens(serial)
    if not pastas:
        return Cobertura(
            "arquivos", INDISPONIVEL, "O armazenamento não pôde ser lido",
            inacessivel="armazenamento do aparelho",
        )
    total = arquivos.tamanho_de(serial, pastas)
    return Cobertura(
        "arquivos", PARCIAL, f"{len(pastas)} pastas, {total / 1024 ** 3:.1f} GB",
        preservado=(
            "fotos, vídeos, documentos, downloads, músicas e os dados externos dos apps "
            "(Android\\media e Android\\data)"
        ),
        legivel="os arquivos abrem direto no computador",
        inacessivel=(
            "dados internos dos apps (/data/data), bloqueados pelo Android sem root; "
            "Android\\obb (arquivos de jogos) não é copiado"
        ),
    )


def _whatsapp(serial):
    apps = whatsapp.detectar(serial)
    if not apps:
        return Cobertura("whatsapp", INDISPONIVEL, "WhatsApp não instalado", inacessivel="não há WhatsApp no aparelho")
    partes = []
    for app in apps:
        if not app.pasta:
            partes.append(f"{app.nome}: pasta não encontrada")
        elif app.ultimo_backup:
            partes.append(f"{app.nome}: backup local de {app.backup_texto}")
        else:
            partes.append(f"{app.nome}: sem backup local")
    return Cobertura(
        "whatsapp", PARCIAL, "; ".join(partes),
        preservado="mídias (fotos, vídeos, áudios, documentos) e o banco de conversas criptografado",
        legivel="só as mídias. As conversas não: o banco é criptografado",
        inacessivel=(
            "texto das conversas e a chave de criptografia, que fica em área bloqueada. "
            "Para ler, restaure o backup em outro aparelho com o chip da linha"
        ),
    )


def _contatos(serial):
    return _dados(
        serial, "contatos", "content://com.android.contacts/contacts", "nome e número dos contatos",
        "fotos dos contatos e contatos guardados só dentro de apps (como o WhatsApp)",
    )


def _sms(serial):
    cobertura = _dados(
        serial, "sms", "content://sms", "conversas de SMS com pessoas",
        "MMS e mensagens de chat (RCS) não entram nesta leitura; SMS de operadora e serviços são "
        "excluídos pelo filtro, com a quantidade informada",
    )
    if cobertura.situacao == DISPONIVEL:
        cobertura.situacao = PARCIAL
        cobertura.resumo = "Leitura liberada; filtro de operadora ativo"
    return cobertura


def _chamadas(serial):
    return _dados(
        serial, "chamadas", "content://call_log/calls", "histórico de chamadas",
        "chamadas feitas por apps (WhatsApp, Teams) e registros já apagados do aparelho",
    )


def _apps(serial):
    resposta = adb.consultar("pm list packages -3", serial, timeout=120)
    ruim = problema(resposta)
    if ruim:
        return Cobertura("apps", INDISPONIVEL, f"Sem acesso: {ruim[1]}", inacessivel=ruim[1])
    quantidade = sum(1 for linha in resposta.saida.splitlines() if linha.startswith("package:"))
    return Cobertura(
        "apps", PARCIAL, f"{quantidade} apps instalados pelo usuário",
        preservado="lista de apps, datas de instalação, histórico de uso e contas registradas",
        legivel="nome, versão, instalação, último uso e tempo de uso de cada app",
        inacessivel=(
            "dados internos e logins dos apps. App instalado não prova que havia conta conectada nele; "
            "senhas e tokens não são coletados"
        ),
    )
