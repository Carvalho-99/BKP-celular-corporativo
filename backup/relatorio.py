"""Relatório em PDF do backup."""
from pathlib import Path

from fpdf import FPDF

from . import cobertura, coleta

_FONTES = Path(r"C:\Windows\Fonts")
_AZUL = (31, 78, 121)


def tamanho_legivel(n):
    for unidade in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unidade}" if unidade == "B" else f"{n:.1f} {unidade}"
        n /= 1024
    return f"{n:.1f} TB"


class _Pdf(FPDF):
    def __init__(self, orientacao="P"):
        super().__init__(orientation=orientacao)
        self.desenhaveis = None
        self.unicode = (_FONTES / "arial.ttf").exists() and (_FONTES / "arialbd.ttf").exists()
        if self.unicode:
            self.add_font("Arial", "", str(_FONTES / "arial.ttf"))
            self.add_font("Arial", "B", str(_FONTES / "arialbd.ttf"))
        self.fonte = "Arial" if self.unicode else "Helvetica"
        self.set_auto_page_break(True, margin=18)
        self.set_margins(15, 15, 15)

    def t(self, texto):
        texto = str(texto)
        if not self.unicode:
            return texto.encode("latin-1", "replace").decode("latin-1")
        if self.desenhaveis is None:
            # emoji e outros sinais que a Arial não tem sairiam como quadradinhos
            self.desenhaveis = set(getattr(self.fonts.get("arial"), "cmap", None) or ())
        if not self.desenhaveis:
            return texto
        return "".join(c for c in texto if ord(c) in self.desenhaveis or c in "\n\t")

    def footer(self):
        self.set_y(-12)
        self.set_font(self.fonte, "", 8)
        self.set_text_color(120)
        self.cell(0, 6, self.t(f"Backup de aparelho corporativo - página {self.page_no()}"), align="C")
        self.set_text_color(0)

    def titulo(self, texto):
        # não deixa o título sozinho no fim da página
        if self.will_page_break(40):
            self.add_page()
        self.ln(4)
        self.set_font(self.fonte, "B", 12)
        self.set_text_color(*_AZUL)
        self.cell(0, 8, self.t(texto), new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0)
        self.set_font(self.fonte, "", 10)

    def paragrafo(self, texto):
        self.set_font(self.fonte, "", 10)
        self.multi_cell(0, 5.5, self.t(texto), new_x="LMARGIN", new_y="NEXT")

    def tabela(self, linhas, larguras, cabecalho=True):
        self.set_font(self.fonte, "", 9)
        with self.table(
            col_widths=larguras,
            first_row_as_headings=cabecalho,
            text_align="LEFT",
            line_height=5.5,
        ) as tabela:
            for linha in linhas:
                celulas = tabela.row()
                for valor in linha:
                    celulas.cell(self.t(valor))


def gerar_detalhes(caminho, resumo):
    """PDF com o conteúdo por extenso: apps, conversas de SMS, chamadas e contatos."""
    dados, aparelho, detalhes = resumo["dados"], resumo["aparelho"], resumo["detalhes"]
    pdf = _Pdf(orientacao="L")
    pdf.add_page()

    pdf.set_font(pdf.fonte, "B", 16)
    pdf.set_text_color(*_AZUL)
    pdf.cell(0, 10, pdf.t("Dados do aparelho por extenso"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)
    pdf.paragrafo(
        f"Funcionário: {dados.funcionario}    |    "
        f"Aparelho: {aparelho['fabricante']} {aparelho['modelo']} (série {aparelho['serial']})    |    "
        f"Backup de {resumo['inicio'].strftime('%d/%m/%Y %H:%M')}"
    )

    if detalhes["apps"]:
        pdf.titulo(f"Aplicativos e histórico de uso ({len(detalhes['apps'])})")
        pdf.paragrafo(
            "Do usado mais recentemente para o nunca usado. O tempo de uso é o total que o "
            "Android tem registrado, que costuma cobrir os últimos meses."
        )
        pdf.ln(1)
        pdf.tabela(
            [["Aplicativo", "Pacote", "Origem", "Versão", "Instalado em", "Último uso", "Tempo de uso"]]
            + [
                [a["nome"], a["pacote"], a["origem"], a["versao"], a["instalado"],
                 a["ultimo_uso"] or "Sem registro", a["tempo_de_uso"] or "-"]
                for a in detalhes["apps"]
            ],
            (22, 24, 13, 9, 12, 12, 8),
        )

    if detalhes["conversas"]:
        total = sum(len(c["mensagens"]) for c in detalhes["conversas"])
        pdf.titulo(f"Conversas por SMS ({len(detalhes['conversas'])} conversas, {total} mensagens)")
        pdf.paragrafo("Mensagens de operadora e de serviços automáticos não entram aqui.")
        for conversa in detalhes["conversas"]:
            if pdf.will_page_break(25):
                pdf.add_page()
            pdf.ln(3)
            pdf.set_font(pdf.fonte, "B", 10)
            pdf.set_fill_color(225, 232, 240)
            pdf.cell(
                0, 7, pdf.t(coleta.titulo_da_conversa(conversa)), fill=True,
                new_x="LMARGIN", new_y="NEXT",
            )
            pdf.set_fill_color(255, 255, 255)  # senão as tabelas seguintes saem com fundo cinza
            for data, tipo, texto in conversa["mensagens"]:
                pdf.set_font(pdf.fonte, "B", 9)
                pdf.cell(0, 5.5, pdf.t(f"{data}  -  {tipo}"), new_x="LMARGIN", new_y="NEXT")
                pdf.set_font(pdf.fonte, "", 9)
                pdf.multi_cell(0, 5, pdf.t(texto or "(sem texto)"), new_x="LMARGIN", new_y="NEXT")
                pdf.ln(1)

    if detalhes["chamadas"]:
        pdf.titulo(f"Histórico de chamadas ({len(detalhes['chamadas'])})")
        pdf.tabela(
            [["Número", "Nome", "Data", "Duração", "Tipo"]] + [list(c) for c in detalhes["chamadas"]],
            (22, 38, 18, 10, 12),
        )

    if detalhes["contatos"]:
        pdf.titulo(f"Contatos ({len(detalhes['contatos'])})")
        pdf.tabela([["Nome", "Número"]] + [list(c) for c in detalhes["contatos"]], (65, 35))

    pdf.output(str(caminho))


def _identificacao(pdf, identificacao):
    """O que foi lido do aparelho, o que é sugestão e o que não foi possível obter."""
    if identificacao is None:
        pdf.titulo("Identificação do aparelho")
        pdf.paragrafo("A identificação automática não foi feita antes deste backup.")
        return

    pdf.titulo("Sugestões de funcionário")
    if identificacao.candidatos:
        pdf.tabela(
            [["Nome sugerido", "De onde veio a sugestão"]]
            + [[c.nome, "; ".join(c.fontes)] for c in identificacao.candidatos],
            (30, 70),
        )
        pdf.ln(2)
    pdf.paragrafo(
        ("Há mais de um nome possível; o técnico escolheu o que consta no início do relatório. "
         if identificacao.conflito else "")
        + "Nome de aparelho e endereço de e-mail ajudam a sugerir uma pessoa, mas não comprovam "
        "quem utilizava o aparelho. Vale o funcionário confirmado pelo técnico."
        if identificacao.candidatos else
        "O aparelho não forneceu nenhum nome. O funcionário foi informado pelo técnico."
    )

    grupos = []
    for leitura in identificacao.coletadas():
        if leitura.grupo not in grupos:
            grupos.append(leitura.grupo)
    for grupo in grupos:
        pdf.titulo(f"Lido do aparelho: {grupo.lower()}")
        pdf.tabela(
            [["Informação", "Valor", "Fonte"]]
            + [[l.item, l.valor, l.metodo] for l in identificacao.coletadas() if l.grupo == grupo],
            (26, 34, 40),
        )
    if any(l.grupo == "Usuário e contas" for l in identificacao.coletadas()):
        pdf.ln(2)
        pdf.paragrafo(
            "Conta registrada indica que existe um cadastro no aparelho, não que ela estava em uso. "
            "Senhas, tokens e códigos de autenticação não são coletados."
        )

    if identificacao.nao_obtidas():
        pdf.titulo("Informações não obtidas")
        pdf.tabela(
            [["Informação", "Situação", "Motivo"]]
            + [[l.item, l.situacao, l.motivo or "-"] for l in identificacao.nao_obtidas()],
            (26, 18, 56),
        )
        pdf.ln(2)
        pdf.paragrafo(
            "Não encontrado: a consulta funcionou, mas o aparelho não tem o dado. "
            "Acesso negado: o sistema recusou a consulta. Não suportado: o aparelho não tem o recurso. "
            "Falha: erro de comunicação ou de leitura."
        )
    pdf.ln(1)
    pdf.paragrafo(f"Identificação feita em {identificacao.quando.strftime('%d/%m/%Y %H:%M')}.")


def gerar(caminho, resumo):
    """`resumo` é o dicionário montado em executar.rodar()."""
    dados, aparelho = resumo["dados"], resumo["aparelho"]
    pdf = _Pdf()
    pdf.add_page()

    pdf.set_font(pdf.fonte, "B", 16)
    pdf.set_text_color(*_AZUL)
    pdf.cell(0, 10, pdf.t("Relatório de backup de aparelho corporativo"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)

    completo = resumo.get("completo", True)
    pdf.set_font(pdf.fonte, "B", 11)
    pdf.set_text_color(*((35, 123, 90) if completo else (139, 98, 13)))
    pdf.multi_cell(
        0, 6,
        pdf.t(
            "Situação: todas as etapas selecionadas terminaram dentro do escopo informado abaixo."
            if completo else
            "Situação: BACKUP COM PENDÊNCIAS. Veja as etapas que não estão como OK."
        ),
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.set_text_color(0)

    pdf.titulo("Desligamento")
    pdf.tabela(
        [
            ["Funcionário (confirmado pelo técnico)", dados.funcionario],
            ["Setor", dados.setor or "-"],
            ["Técnico responsável", dados.tecnico],
            ["Início do backup", resumo["inicio"].strftime("%d/%m/%Y %H:%M")],
            ["Fim do backup", resumo["fim"].strftime("%d/%m/%Y %H:%M")],
            ["Observações", dados.observacoes or "-"],
        ],
        (28, 72),
        cabecalho=False,
    )

    pdf.titulo("Aparelho")
    pdf.tabela(
        [
            ["Marca / modelo", f"{aparelho['fabricante']} {aparelho['modelo']}".strip()],
            ["Android", f"{aparelho['android']} (patch {aparelho['patch'] or '-'})"],
            ["Número de série", aparelho["serial"]],
            ["IMEI (campo da tela)", dados.imei or "Não informado"],
            ["Número da linha (campo da tela)", dados.linha or "Não informado"],
        ],
        (28, 72),
        cabecalho=False,
    )
    pdf.ln(2)
    pdf.paragrafo(
        "IMEI e número da linha acima são os valores do formulário, conferidos ou digitados "
        "pelo técnico. O que o programa leu do aparelho, com a fonte de cada dado, está a seguir."
    )

    _identificacao(pdf, dados.identificacao)

    pdf.titulo("Resultado de cada etapa")
    pdf.tabela(
        [["Etapa", "Situação", "Detalhe"]] + [[e.nome, e.situacao, e.detalhe] for e in resumo["etapas"]],
        (24, 14, 62),
    )

    com_cobertura = [e for e in resumo["etapas"] if e.preservado or e.legivel or e.inacessivel]
    if com_cobertura:
        pdf.titulo("Cobertura de cada etapa")
        pdf.paragrafo(
            "Preservado é o que ficou guardado no backup. Legível é o que dá para abrir e ler. "
            "Copiar um banco criptografado não permite ler as conversas; listar um aplicativo "
            "não copia os dados internos dele."
        )
        pdf.ln(1)
        pdf.tabela(
            [["Etapa", "Preservado no backup", "Legível", "Não acessível"]]
            + [[e.nome, e.preservado or "-", e.legivel or "-", e.inacessivel or "-"] for e in com_cobertura],
            (16, 28, 26, 30),
        )
        if any(e.categoria == "sms" for e in com_cobertura):
            pdf.ln(2)
            pdf.paragrafo("Filtro de SMS: " + cobertura.FILTRO_DE_SMS)

    if resumo["copias"]:
        pdf.titulo("Arquivos copiados")
        linhas = [["Pasta no celular", "No celular", "Copiados", "Tamanho"]]
        for c in resumo["copias"]:
            linhas.append([c.origem, c.esperados, c.arquivos, tamanho_legivel(c.bytes)])
        linhas.append(
            [
                "TOTAL",
                sum(c.esperados for c in resumo["copias"]),
                sum(c.arquivos for c in resumo["copias"]),
                tamanho_legivel(sum(c.bytes for c in resumo["copias"])),
            ]
        )
        pdf.tabela(linhas, (52, 16, 16, 16))
        pdf.ln(2)
        pdf.paragrafo(
            "O arquivo manifesto.csv traz o SHA-256 de cada arquivo copiado. Ele permite verificar "
            "se um arquivo foi alterado depois do backup; sozinho, não comprova que todos os dados "
            "do celular foram coletados."
        )

    if resumo["contas"]:
        pdf.titulo("Contas encontradas no aparelho")
        pdf.tabela([["Conta", "Tipo"]] + [list(c) for c in resumo["contas"]], (55, 45))
        pdf.ln(2)
        pdf.paragrafo(
            "As senhas não ficam neste relatório. Para acessar uma conta corporativa, "
            "redefina a senha pelo painel de administração."
        )

    if resumo["whatsapp"]:
        pdf.titulo("WhatsApp")
        linhas = [["Aplicativo", "Último backup local", "Pasta copiada"]]
        for app in resumo["whatsapp"]:
            linhas.append([app.nome, app.backup_texto, app.pasta or "Pasta não encontrada"])
        pdf.tabela(linhas, (24, 26, 50))
        pdf.ln(2)
        pdf.paragrafo(
            f"Número da linha: {dados.linha or 'não informado'}\n"
            f"Conta Google do backup: {dados.conta_whatsapp or 'não informada'}\n\n"
            "Para ler as conversas:\n"
            "1. Coloque o chip desta linha em um aparelho Android e entre na conta Google acima.\n"
            "2. Instale o mesmo aplicativo (WhatsApp ou WhatsApp Business).\n"
            "3. Confirme o número pelo SMS e toque em RESTAURAR quando o backup for encontrado.\n"
            "4. Sem internet ou sem o backup na nuvem: copie a pasta do WhatsApp deste backup "
            "para o mesmo lugar no aparelho novo antes de abrir o aplicativo.\n"
            "5. Se o backup estiver com criptografia de ponta a ponta, será pedida a senha "
            "ou a chave de 64 dígitos definida no aparelho original."
        )

    pdf.titulo("Onde está o backup")
    pdf.paragrafo(str(resumo["pasta"]))
    pdf.ln(1)
    pdf.tabela(
        [
            ["detalhes.pdf", "Apps com histórico de uso, conversas de SMS, chamadas e contatos por extenso"],
            ["dados\\sms.txt", "Conversas de SMS em texto, para abrir no Bloco de Notas"],
            ["dados\\*.csv", "As mesmas listas em planilha (abre no Excel)"],
            ["arquivos\\", "Fotos, vídeos, documentos e pastas do WhatsApp"],
            ["manifesto.csv", "SHA-256 de cada arquivo copiado"],
        ],
        (25, 75),
        cabecalho=False,
    )

    pdf.output(str(caminho))
