"""Regras da tela que não dependem de janela: o que mostrar e o que impede de iniciar.

Fica separado dos componentes para poder ser testado sem abrir nada.
"""
import os
import tempfile
from dataclasses import dataclass

# (chave enviada ao backup, rótulo, placeholder)
CAMPOS = [
    ("funcionario", "Funcionário", "Nome completo"),
    ("setor", "Setor", "Ex.: Administrativo"),
    ("tecnico", "Técnico responsável", ""),
    ("linha", "Número da linha", "(00) 00000-0000"),
    ("imei", "IMEI", "Número de identificação"),
    ("conta_whatsapp", "Conta Google do WhatsApp", "E-mail utilizado no backup"),
    ("observacoes", "Observações", "Informações adicionais sobre o aparelho ou o backup"),
]
OBRIGATORIOS = ("funcionario", "tecnico")
ROTULOS = {chave: rotulo for chave, rotulo, _ in CAMPOS}
# campos que o programa tenta ler do aparelho
CAPTURAVEIS = ("funcionario", "linha", "imei", "conta_whatsapp")

# (chave de executar.Opcoes, título, descrição, ícone), na ordem em que aparecem
OPCOES = [
    ("arquivos", "Arquivos e mídias", "Fotos, vídeos e documentos", "midias"),
    ("whatsapp", "WhatsApp", "Dados disponíveis", "conversa"),
    ("contatos", "Contatos", "Agenda do aparelho", "contatos"),
    ("sms", "SMS", "Somente com pessoas", "mensagem"),
    ("chamadas", "Chamadas", "Histórico de ligações", "telefone"),
    ("apps", "Apps e contas", "Aplicativos, contas e uso", "apps"),
]

AJUDA_CONEXAO = "Conecte o cabo e aceite “Permitir depuração USB” no celular."


@dataclass
class Aparelho:
    # procurando | nenhum | interrompida | escolher | autorizar | sem_resposta | sem_suporte | erro | conectado
    codigo: str
    titulo: str
    selo: str
    tom: str
    ajuda: str
    serial: str = ""
    plataforma: str = ""
    impedimento: str = ""  # por que o backup não pode começar com este aparelho
    origem: object = None  # o conectores.Aparelho correspondente

    @property
    def pronto(self):
        return self.codigo == "conectado"


PROCURANDO = Aparelho("procurando", "Conecte o celular", "Procurando aparelho", "neutro", AJUDA_CONEXAO)


def situacao_do_aparelho(aparelhos, escolhido="", sessao=""):
    """Traduz a lista de conectores.listar() (ou um texto de erro) para o que a tela mostra.

    `escolhido` é o aparelho selecionado quando há mais de um; `sessao` é o aparelho
    cujos dados estão no formulário, para distinguir "nunca conectou" de "saiu do cabo".
    """
    if isinstance(aparelhos, str):
        return Aparelho(
            "erro", "Falha de comunicação", "Falha", "erro", f"O ADB não respondeu: {aparelhos}",
            impedimento="Sem comunicação com o ADB.",
        )
    if not aparelhos:
        if sessao:
            return Aparelho(
                "interrompida", "Conexão interrompida", "Aparelho fora do cabo", "aviso",
                "O aparelho saiu do cabo. Os dados lidos continuam na tela; reconecte para continuar.",
                impedimento="O aparelho saiu do cabo. Reconecte antes de iniciar.",
            )
        return Aparelho("nenhum", "Conecte o celular", "Nenhum aparelho conectado", "aviso", AJUDA_CONEXAO)

    atual = next((a for a in aparelhos if a.id == escolhido), None)
    if atual is None and len(aparelhos) == 1:
        atual = aparelhos[0]
    if atual is None:
        return Aparelho(
            "escolher", f"{len(aparelhos)} aparelhos conectados", "Escolha um aparelho", "aviso",
            "Selecione abaixo qual aparelho será identificado e copiado.",
            impedimento="Escolha qual aparelho será copiado.",
        )

    comum = dict(serial=atual.id, plataforma=atual.plataforma, origem=atual)
    nome = atual.modelo or f"Aparelho {atual.plataforma}"
    if atual.estado == "autorizar":
        return Aparelho(
            "autorizar", f"{nome} detectado", "Aguardando autorização", "aviso",
            "Desbloqueie a tela e toque em “Permitir” na mensagem de depuração USB.",
            impedimento="Falta autorizar a depuração USB no celular.", **comum,
        )
    if atual.estado == "sem_suporte":
        return Aparelho(
            "sem_suporte", f"{nome} detectado", "Backup não suportado", "aviso",
            atual.detalhe, impedimento=atual.detalhe, **comum,
        )
    if atual.estado != "pronto":
        return Aparelho(
            "sem_resposta", f"{nome} sem resposta", "Falha de comunicação", "erro",
            f"Tire e coloque o cabo de novo (estado informado: {atual.detalhe or 'desconhecido'}).",
            impedimento="O celular não está respondendo.", **comum,
        )
    return Aparelho(
        "conectado", nome, "Conectado", "sucesso",
        f"{atual.plataforma}, identificador da conexão {atual.id}", **comum,
    )


def problema_no_destino(destino):
    """Texto do problema, ou "" se dá para gravar na pasta."""
    if not destino:
        return "Escolha a pasta onde o backup será salvo."
    if not os.path.isdir(destino):
        return "A pasta escolhida não existe mais. Escolha outra."
    try:
        with tempfile.TemporaryFile(dir=destino):
            pass
    except OSError:
        return "Sem permissão para gravar nesta pasta. Escolha outra."
    return ""


def validar(dados, opcoes, destino, aparelho):
    """Devolve {onde: mensagem} com tudo que impede o backup; vazio se pode iniciar.

    `onde` é a chave do campo, ou "aparelho", "opcoes", "destino".
    """
    erros = {}
    if not aparelho.pronto or aparelho.impedimento:
        erros["aparelho"] = aparelho.impedimento or "Conecte e autorize o celular antes de iniciar."
    for chave in OBRIGATORIOS:
        if not dados.get(chave, "").strip():
            erros[chave] = f"Informe: {ROTULOS[chave].lower()}."
    if not any(opcoes.values()):
        erros["opcoes"] = "Marque pelo menos um item para copiar."
    problema = problema_no_destino(destino)
    if problema:
        erros["destino"] = problema
    return erros


def verificacoes(erros):
    """As três linhas do cartão Preparação: [(texto, pronto)]."""
    return [
        ("Identificar aparelho", "aparelho" not in erros),
        ("Dados obrigatórios", not any(chave in erros for chave in OBRIGATORIOS)),
        ("Conteúdo e destino", "opcoes" not in erros and "destino" not in erros),
    ]


def o_que_falta(erros):
    """Frase curta de ajuda para o cartão Preparação."""
    if "aparelho" in erros:
        return erros["aparelho"]
    faltando = [ROTULOS[c].lower() for c in OBRIGATORIOS if c in erros]
    if faltando:
        return "Informe " + " e ".join(faltando) + "."
    if "opcoes" in erros:
        return erros["opcoes"]
    if "destino" in erros:
        return erros["destino"]
    return "Tudo pronto para iniciar."


def contador(quantidade):
    if quantidade == 0:
        return "Nenhum selecionado"
    return "1 selecionado" if quantidade == 1 else f"{quantidade} selecionados"


def resumo_do_log(eventos):
    if eventos == 0:
        return "Nenhuma atividade"
    return "1 evento" if eventos == 1 else f"{eventos} eventos"


def tom_da_mensagem(mensagem):
    """Destaque discreto no log: "erro", "aviso" ou ""."""
    texto = mensagem.upper()
    if "FALHOU" in texto or "ERRO" in texto or "[FALHA]" in texto:
        return "erro"
    avisos = ("INCOMPLETO", "CANCELADO", "PARCIAL", "NÃO EXECUTADA", "[ACESSO NEGADO]",
              "[NÃO SUPORTADO]", "[NÃO IMPLEMENTADO]")
    if any(aviso in texto for aviso in avisos):
        return "aviso"
    return ""


def linha_de_leitura(leitura):
    """Como uma leitura aparece em Detalhes da execução."""
    if leitura.coletada:
        return f"[{leitura.situacao}] {leitura.item}: {leitura.valor}  (fonte: {leitura.metodo})"
    return f"[{leitura.situacao}] {leitura.item}: {leitura.motivo}  (método: {leitura.metodo})"


def resumo_da_identificacao(identificacao, preenchidos, mantidos):
    """Frase embaixo do formulário: o que foi preenchido, o que é sugestão e o que faltou.

    `preenchidos` e `mantidos` são listas de rótulos de campos.
    """
    partes = []
    if preenchidos:
        partes.append("Preenchido pelo aparelho: " + ", ".join(preenchidos) + " (confira).")
    if mantidos:
        partes.append("Mantido como você digitou: " + ", ".join(mantidos) + ".")
    if identificacao.conflito:
        partes.append("Há mais de um nome possível para o funcionário; escolha abaixo ou digite.")
    elif not identificacao.candidatos:
        partes.append("O aparelho não forneceu nome de usuário; digite o funcionário.")
    faltas = [l for l in identificacao.nao_obtidas()]
    if faltas:
        contagem = {}
        for leitura in faltas:
            contagem[leitura.situacao] = contagem.get(leitura.situacao, 0) + 1
        resumo = ", ".join(f"{n} {s.lower()}" for s, n in contagem.items())
        partes.append(f"Não obtido: {resumo}. Os motivos estão em Detalhes da execução.")
    return " ".join(partes)


def situacao_da_categoria(etapas):
    """(tom, texto) do resultado de uma categoria depois do backup; None se ela não rodou."""
    if not etapas:
        return None
    ordem = {"Falhou": 0, "Não executada": 1, "Cancelado": 2, "Parcial": 3, "OK": 4}
    pior = min(etapas, key=lambda e: ordem.get(e.situacao, 0))
    tom = {"OK": "sucesso", "Parcial": "aviso", "Não executada": "aviso", "Cancelado": "aviso"}.get(
        pior.situacao, "erro"
    )
    detalhes = "; ".join(e.detalhe if len(etapas) == 1 else f"{e.nome}: {e.detalhe}" for e in etapas)
    return tom, f"{pior.situacao}: {detalhes}"


def resultado(problemas, cancelado, pasta):
    """(tom, situação, explicação) para o fim do backup, conforme o que o backup devolveu."""
    if cancelado:
        return "aviso", "Cancelado", f"Backup interrompido. O que já foi copiado está em {pasta}"
    if problemas:
        lista = "; ".join(f"{e.nome}: {e.detalhe}" for e in problemas)
        return "aviso", "Concluído com pendências", f"{lista}. Pasta: {pasta}"
    return "sucesso", "Backup concluído", f"Salvo em {pasta}"
