"""Gera a documentação do projeto Backup Corporativo em PDF.

Uso: .venv\\Scripts\\python docs\\gerar_documentacao.py saida.pdf pasta_temporaria
"""
import sys
from pathlib import Path

PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJETO))
from PIL import Image  # noqa: E402

from backup.relatorio import _AZUL, _Pdf  # noqa: E402

SAIDA = Path(sys.argv[1])
TEMP = Path(sys.argv[2])
PETROLEO = (12, 116, 130)
CINZA = (102, 119, 138)


class Doc(_Pdf):
    secao = 0

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-12)
        self.set_font(self.fonte, "", 8)
        self.set_text_color(120)
        self.cell(0, 6, self.t(f"Backup Corporativo - Documentação do projeto - página {self.page_no()}"), align="C")
        self.set_text_color(0)

    def capitulo(self, texto):
        self.secao += 1
        if self.will_page_break(60):
            self.add_page()
        self.ln(6)
        self.set_font(self.fonte, "B", 15)
        self.set_text_color(*PETROLEO)
        self.cell(0, 9, self.t(f"{self.secao}. {texto}"), new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*PETROLEO)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.set_draw_color(0)
        self.set_text_color(0)
        self.ln(3)

    def sub(self, texto):
        self.titulo(texto)

    def p(self, texto):
        self.paragrafo(texto)
        self.ln(1.5)

    def itens(self, lista, numerados=False):
        self.set_font(self.fonte, "", 10)
        for i, item in enumerate(lista, start=1):
            marca = f"{i}." if numerados else "-"
            self.set_x(self.l_margin + 3)
            self.cell(7, 5.5, marca)
            self.multi_cell(0, 5.5, self.t(item), new_x="LMARGIN", new_y="NEXT")
        self.ln(1.5)

    def t2(self, linhas, larguras, cabecalho=True):
        self.tabela(linhas, larguras, cabecalho)
        self.ln(2)

    def figura(self, arquivo, legenda, cortar_baixo=0):
        imagem = Image.open(arquivo).convert("RGB")
        # tira só a faixa preta que sobra quando a janela passa da área da tela
        altura_util = imagem.height
        while altura_util > 1 and imagem.getpixel((imagem.width // 2, altura_util - 1)) == (0, 0, 0):
            altura_util -= 1
        imagem = imagem.crop((0, 0, imagem.width, altura_util))
        destino = TEMP / f"doc_{Path(arquivo).stem}.png"
        imagem.save(destino)
        largura = self.w - self.l_margin - self.r_margin
        altura = largura * imagem.height / imagem.width
        if self.will_page_break(altura + 12):
            self.add_page()
        self.set_draw_color(223, 230, 239)
        y = self.get_y()
        self.image(str(destino), x=self.l_margin, y=y, w=largura)
        self.rect(self.l_margin, y, largura, altura)
        self.set_draw_color(0)
        self.set_y(y + altura + 1.5)
        self.set_font(self.fonte, "", 8.5)
        self.set_text_color(*CINZA)
        self.multi_cell(0, 4.5, self.t(legenda), new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0)
        self.ln(3)


pdf = Doc()
pdf.set_title("Backup Corporativo - Documentação do projeto")
pdf.set_author("TI Forest")

# ---------- capa ----------
pdf.add_page()
pdf.set_fill_color(*PETROLEO)
pdf.rect(0, 0, pdf.w, 95, style="F")
pdf.set_fill_color(255, 255, 255)  # senão as tabelas herdam o fundo da capa
pdf.set_y(38)
pdf.set_text_color(255)
pdf.set_font(pdf.fonte, "B", 30)
pdf.cell(0, 14, pdf.t("Backup Corporativo"), new_x="LMARGIN", new_y="NEXT")
pdf.set_font(pdf.fonte, "", 15)
pdf.cell(0, 9, pdf.t("Backup de celulares corporativos no desligamento de funcionários"), new_x="LMARGIN", new_y="NEXT")
pdf.set_text_color(0)
pdf.set_y(112)
pdf.set_font(pdf.fonte, "B", 16)
pdf.set_text_color(*_AZUL)
pdf.cell(0, 9, pdf.t("Documentação do projeto"), new_x="LMARGIN", new_y="NEXT")
pdf.set_text_color(0)
pdf.ln(4)
pdf.t2(
    [
        ["Versão do documento", "1.0"],
        ["Data", "29/09/2026"],
        ["Área", "TI - Grupo Forest"],
        ["Responsável", "Bruno Carvalho"],
        ["Local do projeto", "C:\\dev\\backup-celular"],
        ["Situação", "Android funcionando e validado em aparelho real; iPhone apenas detectado"],
    ],
    (32, 68), cabecalho=False,
)
pdf.ln(4)
pdf.p(
    "Este documento descreve o que o programa é, o que ele faz, como foi construído, o que foi "
    "testado e o que ainda falta. Ele registra o estado do projeto na data acima."
)

# ---------- 1 ----------
pdf.add_page()
pdf.capitulo("Resumo")
pdf.p(
    "O Backup Corporativo é um programa para Windows, usado pelo TI, que copia os dados de um "
    "celular Android da empresa quando o funcionário é desligado. O celular fica ligado ao "
    "computador pelo cabo USB e o computador comanda toda a cópia. Nada é instalado no celular, "
    "e o aparelho não precisa de root."
)
pdf.p(
    "Ao conectar o aparelho, o programa o identifica sozinho, preenche o formulário com o que "
    "conseguiu ler, mostra o que cada categoria permite copiar e, ao final, gera relatórios em "
    "PDF com o resultado real de cada etapa."
)
pdf.t2(
    [
        ["Item", "Situação em 29/09/2026"],
        ["Identificação automática do Android", "Funcionando; validada no Galaxy A16"],
        ["Backup de contatos, SMS, chamadas e apps", "Funcionando; validado no Galaxy A16 pela tela atual"],
        ["Cópia de arquivos, fotos e WhatsApp", "Funcionando; backup completo feito no A16 e no A15 com a versão anterior"],
        ["Conversas do WhatsApp em texto", "Não disponível; exportação automática em estudo"],
        ["iPhone", "Apenas detectado no cabo; backup não implementado"],
        ["Testes automáticos", "69 testes, todos passando"],
    ],
    (42, 58),
)

# ---------- 2 ----------
pdf.capitulo("Objetivo e contexto")
pdf.p(
    "Antes do projeto, o backup dos celulares de funcionários desligados era feito à mão. O "
    "objetivo foi padronizar esse trabalho: o mesmo procedimento, os mesmos arquivos gerados e "
    "um relatório que mostra o que foi copiado e o que não foi."
)
pdf.sub("Premissas")
pdf.itens([
    "Os aparelhos e as linhas são da empresa, cedidos ao funcionário.",
    "O funcionário assina termo de responsabilidade na entrega e termo de devolução, autorizando o TI a fazer backup dos dados.",
    "Os aparelhos são Android, chegam desbloqueados e a empresa não usa MDM.",
    "O backup é gravado em disco local, em uma pasta por funcionário e data.",
    "A operação é por cabo USB, sem instalar aplicativo no celular, sem root e sem jailbreak.",
])

# ---------- 3 ----------
pdf.capitulo("Como funciona")
pdf.itens([
    "O técnico ativa a Depuração USB no celular e liga o cabo.",
    "O celular pergunta se permite a depuração; o técnico aceita.",
    "O programa reconhece o aparelho e o identifica sozinho (cerca de 7 segundos no Galaxy A16).",
    "O formulário é preenchido com o que foi lido. O técnico confere, corrige e digita o que faltou.",
    "Os cartões de \"O que copiar\" mostram o que o aparelho permite em cada categoria.",
    "O técnico escolhe a pasta de destino e clica em Iniciar backup.",
    "O programa pede o backup dentro do WhatsApp e confere se ele foi feito.",
    "Os dados são copiados, os relatórios são gerados e a pasta do backup é aberta.",
], numerados=True)
pdf.sub("Preparação do celular (Samsung)")
pdf.itens([
    "Configurações > Sobre o telefone > Informações do software > tocar 7 vezes em Número de compilação.",
    "Configurações > Opções do desenvolvedor > ligar Depuração USB.",
    "Se a opção estiver cinza: desligar o Bloqueador automático em Segurança e privacidade.",
    "Conectar o cabo com a tela desbloqueada e tocar em Permitir.",
], numerados=True)

# ---------- 4 ----------
pdf.capitulo("Tela do programa")
pdf.p(
    "A tela segue o layout aprovado: faixa do aparelho no topo, dados do desligamento e opções "
    "de cópia à esquerda, destino e preparação à direita, e o registro recolhível no fim. "
    "As imagens abaixo foram feitas com dados fictícios."
)
pdf.figura(PROJETO / "docs" / "tela-aparelho-pronto.png", "Figura 1 - Aparelho identificado e formulário preenchido.")
pdf.figura(PROJETO / "docs" / "tela-nomes-sugeridos.png",
           "Figura 2 - Dois nomes possíveis: o programa mostra as opções com a fonte e não escolhe sozinho.", cortar_baixo=35)
pdf.figura(PROJETO / "docs" / "tela-troca-de-aparelho.png",
           "Figura 3 - Outro aparelho conectado: os dados do anterior não são reaproveitados sem decisão do técnico.")
pdf.figura(PROJETO / "docs" / "tela-opcoes-e-log.png",
           "Figura 4 - Categoria recusada pelo aparelho fica travada com o motivo; abaixo, os detalhes da execução.")
pdf.sub("Situações do aparelho mostradas na tela")
pdf.t2(
    [
        ["Situação", "Quando aparece"],
        ["Nenhum aparelho conectado", "Não há celular no cabo"],
        ["Aguardando autorização", "O celular foi detectado, mas falta aceitar a depuração USB"],
        ["Identificando", "O programa está lendo as informações"],
        ["Pronto", "Aparelho identificado"],
        ["Escolha um aparelho", "Há mais de um celular no cabo"],
        ["Conexão interrompida", "O aparelho saiu do cabo; os dados lidos continuam na tela"],
        ["Falha na identificação", "A leitura falhou; o motivo é mostrado"],
        ["Backup não suportado", "iPhone detectado"],
    ],
    (35, 65),
)

# ---------- 5 ----------
pdf.capitulo("Identificação automática")
pdf.p(
    "Cada informação que o programa tenta ler fica registrada com a situação, a fonte e, quando "
    "não deu certo, o motivo. Nenhuma leitura vira campo vazio sem explicação."
)
pdf.t2(
    [
        ["Situação", "Significado"],
        ["Coletado", "Lido do aparelho"],
        ["Não encontrado", "A consulta funcionou, mas o aparelho não tem o dado"],
        ["Acesso negado", "O sistema recusou a consulta"],
        ["Não suportado", "O aparelho ou a versão não tem o recurso"],
        ["Falha", "Erro de comunicação ou de leitura"],
        ["Não implementado", "O programa ainda não sabe coletar"],
    ],
    (30, 70),
)
pdf.sub("O que é lido")
pdf.t2(
    [
        ["Grupo", "Informações"],
        ["Aparelho", "Fabricante, modelo, versão do Android, atualização de segurança, compilação, número de série, "
                     "identificador da conexão USB, IMEI 1 e 2, armazenamento total e livre, bateria"],
        ["Chips e linha", "Chip de cada compartimento (operadora, físico ou eSIM), operadora e número da linha"],
        ["Usuário e contas", "Nome no perfil, nome do usuário local, nome dado ao aparelho, e-mail corporativo, "
                             "e-mails pessoais e contas registradas (Google, Samsung, Microsoft, OneDrive, WhatsApp e outras)"],
    ],
    (25, 75),
)
pdf.p(
    "Número de série, identificador da conexão e IMEI são tratados como informações diferentes. "
    "O dígito verificador do IMEI confere o formato do número, e a fonte de onde ele veio fica registrada ao lado."
)
pdf.sub("Número da linha")
pdf.p("São quatro fontes, consultadas nesta ordem. A primeira que responder é usada, e as que falharam ficam registradas.")
pdf.itens([
    "Tabela de chips do Android.",
    "Serviço de assinaturas.",
    "Serviço de telefonia.",
    "Tela Configurações > Sobre o telefone. Só é aberta com o celular desbloqueado, e o número só vale se estiver no campo \"Número de telefone\".",
], numerados=True)
pdf.sub("Funcionário: lido, sugerido e confirmado")
pdf.p(
    "O programa separa três coisas: o que foi lido do aparelho, o nome sugerido a partir disso e o "
    "funcionário confirmado pelo técnico. Nome de aparelho (\"A16 de João\") e endereço de e-mail "
    "ajudam a sugerir uma pessoa, mas não comprovam quem usava o celular."
)
pdf.itens([
    "Com um único nome possível, o campo é preenchido como sugestão, com a fonte indicada.",
    "Com nomes conflitantes, o campo fica vazio e a tela mostra as opções para o técnico escolher.",
    "O que o técnico digita ou corrige nunca é substituído.",
    "Ao trocar de aparelho, o técnico decide entre começar uma sessão nova ou manter o que digitou.",
])

# ---------- 6 ----------
pdf.capitulo("O que é copiado")
pdf.t2(
    [
        ["Categoria", "Conteúdo", "Onde fica no backup"],
        ["Arquivos e mídias", "Fotos, vídeos, documentos, downloads, músicas", "arquivos\\"],
        ["Arquivos externos dos apps", "Documentos escaneados e arquivos que os apps guardam fora da área protegida", "arquivos\\Android\\data\\"],
        ["WhatsApp e WhatsApp Business", "Mídias e banco de conversas criptografado", "arquivos\\Android\\media\\"],
        ["Contatos", "Nome e número", "dados\\contatos.csv"],
        ["SMS", "Conversas com pessoas, agrupadas por contato", "dados\\sms.csv e sms.txt"],
        ["Chamadas", "Número, nome, data, duração e tipo", "dados\\chamadas.csv"],
        ["Apps", "Nome, versão, instalação, último uso e tempo de uso", "dados\\apps.csv"],
        ["Contas", "Identificador e tipo de cada conta registrada", "dados\\contas.csv"],
    ],
    (26, 44, 30),
)
pdf.sub("Filtro de SMS")
pdf.p(
    "Ficam de fora as mensagens cujo remetente tem letras (como VIVO ou TIM) ou tem menos de 8 "
    "dígitos (números curtos de serviço). A quantidade excluída e a lista de remetentes ficam em "
    "dados\\sms_filtro.csv; o texto dessas mensagens não é copiado. No Galaxy A16 de teste, de 295 "
    "mensagens, 16 eram de pessoas e 279 foram excluídas pelo filtro."
)

# ---------- 7 ----------
pdf.capitulo("Cobertura e limites")
pdf.p(
    "Antes do backup, cada categoria mostra o que o aparelho conectado permite. Depois, mostra o "
    "resultado real. O relatório separa três colunas por etapa:"
)
pdf.t2(
    [
        ["Coluna", "Significado"],
        ["Preservado", "O que ficou guardado no backup"],
        ["Legível", "O que dá para abrir e ler em planilha ou relatório"],
        ["Não acessível", "O que não foi possível obter"],
    ],
    (25, 75),
)
pdf.p(
    "Copiar um banco criptografado não permite ler as conversas. Listar um aplicativo não copia "
    "os dados internos dele, nem prova que havia conta conectada."
)
pdf.sub("O que o programa não faz")
pdf.t2(
    [
        ["Limite", "Motivo"],
        ["Não lê senhas, tokens ou códigos de autenticação", "Decisão de projeto; para acessar uma conta corporativa, a senha é redefinida no painel de administração"],
        ["Não lê o texto das conversas do WhatsApp", "O banco é criptografado e a chave não sai do aparelho"],
        ["Não lê dados internos dos aplicativos", "Área bloqueada pelo Android sem root"],
        ["Não lê MMS nem mensagens de chat (RCS)", "Não estão na tabela de SMS consultada"],
        ["Não copia Android\\obb", "São arquivos de jogos, sem dado do usuário"],
        ["Não faz backup de iPhone", "Não implementado nesta versão"],
    ],
    (42, 58),
)
pdf.p(
    "O manifesto com SHA-256 permite verificar se um arquivo foi alterado depois do backup. "
    "Sozinho, ele não comprova que todos os dados do celular foram coletados."
)

# ---------- 8 ----------
pdf.capitulo("WhatsApp")
pdf.itens([
    "O programa detecta WhatsApp e WhatsApp Business.",
    "Pede ao técnico que faça o backup dentro do aplicativo e mostra o caminho.",
    "Confere, pela data do arquivo, se o backup novo apareceu.",
    "Copia a pasta inteira do aplicativo.",
    "Registra no relatório o que foi copiado e como restaurar.",
], numerados=True)
pdf.p(
    "Para ler as conversas, o caminho é restaurar o backup em outro aparelho: colocar o chip da "
    "linha, entrar na conta Google do backup, instalar o mesmo aplicativo e tocar em Restaurar. "
    "Como a linha é da empresa, isso é viável."
)
pdf.sub("Pontos de atenção")
pdf.itens([
    "O backup depende do técnico: o programa não aperta o botão sozinho.",
    "A conta Google sugerida é a do aparelho; o WhatsApp não deixa confirmar qual ele usa.",
    "Nos dois backups reais feitos em 29/09, o backup novo não apareceu e foi copiado o backup antigo.",
    "No Galaxy A16, o WhatsApp comum nunca tinha feito backup local: as mídias são copiadas, as conversas não.",
])
pdf.p(
    "Está em estudo a exportação automática das conversas para arquivo de texto, comandando a "
    "tela do celular. O teste depende do aparelho desbloqueado e ainda não foi feito."
)

# ---------- 9 ----------
pdf.capitulo("Arquivos gerados em cada backup")
pdf.p("Cada backup fica em uma pasta própria, com o nome do funcionário e a data, por exemplo: João da Silva - 2026-09-29 14h12.")
pdf.t2(
    [
        ["Arquivo", "Conteúdo"],
        ["relatorio.pdf", "Resumo: situação geral, funcionário, aparelho, sugestões de nome, informações lidas e não obtidas, "
                          "resultado e cobertura de cada etapa, contas e instruções do WhatsApp"],
        ["detalhes.pdf", "Conteúdo por extenso: apps e uso, conversas de SMS, chamadas e contatos"],
        ["manifesto.csv", "SHA-256, tamanho e data de cada arquivo copiado"],
        ["log.txt", "Registro do que o programa fez, com horário"],
        ["dados\\", "Planilhas CSV, sms.txt e o histórico bruto de uso"],
        ["arquivos\\", "Os arquivos copiados do celular, na mesma estrutura de pastas"],
    ],
    (25, 75),
)
pdf.p(
    "Além disso, a trilha de cada identificação fica em registros\\identificacao-AAAA-MM-DD.log, "
    "na pasta do programa."
)

# ---------- 10 ----------
pdf.capitulo("Recursos por plataforma")
pdf.t2(
    [
        ["Recurso", "Android", "iPhone"],
        ["Detectar o aparelho no cabo", "Sim", "Sim"],
        ["Identificar aparelho, chips e contas", "Sim", "Não implementado"],
        ["Arquivos, fotos e vídeos", "Sim", "Não implementado"],
        ["Contatos, SMS e chamadas", "Sim", "Não implementado"],
        ["Apps e histórico de uso", "Sim", "Não implementado"],
        ["WhatsApp: mídias e banco criptografado", "Sim", "Não implementado"],
        ["Conversas do WhatsApp em texto", "Não", "Não implementado"],
        ["Senhas e tokens", "Não coleta", "Não coleta"],
    ],
    (50, 22, 28),
)
pdf.sub("O que falta para o iPhone")
pdf.itens([
    "Instalar o suporte da Apple no Windows (aplicativo Dispositivos Apple ou iTunes).",
    "Instalar a biblioteca de comunicação pymobiledevice3. No Python 3.14 ela não instala completa, porque duas dependências exigem compilador.",
    "Escrever e testar a leitura e o backup com um iPhone real.",
], numerados=True)
pdf.p("Por decisão tomada em 29/09/2026, o projeto segue só com Android por enquanto.")

# ---------- 11 ----------
pdf.capitulo("Arquitetura técnica")
pdf.t2(
    [
        ["Parte", "Tecnologia"],
        ["Linguagem", "Python 3.14"],
        ["Comunicação com o celular", "ADB oficial do Google (platform-tools 37.0.1), dentro da pasta do projeto"],
        ["Interface", "Tkinter com customtkinter 6.0"],
        ["Ícones", "Desenhados pelo próprio programa com Pillow 12.3, sem arquivos nem internet"],
        ["Relatórios em PDF", "fpdf2 2.8"],
        ["Nome comercial dos apps", "Consulta à página pública da Play Store; só o nome do pacote é enviado"],
    ],
    (32, 68),
)
pdf.sub("Organização do código")
pdf.p("O processamento fica separado da tela. A pasta backup\\ não conhece a interface.")
pdf.t2(
    [
        ["Arquivo", "Papel", "Linhas"],
        ["backup\\conectores.py", "Lista aparelhos de todas as plataformas e encaminha ao conector certo", "137"],
        ["backup\\adb.py", "Conversa com o adb.exe", "118"],
        ["backup\\leitura.py", "Situação, método e motivo de cada leitura; registro em arquivo", "103"],
        ["backup\\captura.py", "Identificação do Android", "684"],
        ["backup\\cobertura.py", "O que cada categoria entrega no aparelho", "165"],
        ["backup\\coleta.py", "SMS, contatos, chamadas, apps e contas", "338"],
        ["backup\\arquivos.py", "Cópia em fluxo único com manifesto", "212"],
        ["backup\\whatsapp.py", "Detecção do WhatsApp e do último backup", "68"],
        ["backup\\executar.py", "Sequência do backup e resultado de cada etapa", "464"],
        ["backup\\relatorio.py", "Geração dos PDFs", "355"],
        ["backup\\nomes_apps.py", "Nome comercial dos apps", "68"],
        ["interface\\tema.py", "Cores, fontes e medidas", "94"],
        ["interface\\icones.py", "Ícones", "148"],
        ["interface\\componentes.py", "Botão, campo, cartão, opção, selo e log", "527"],
        ["interface\\estado.py", "Regras da tela e validação", "244"],
        ["interface\\janela.py", "Montagem e ligação com o backup", "920"],
        ["tests\\", "Testes automáticos e celular simulado", "1.296"],
        ["diagnostico.py", "Mostra o que é lido de um aparelho, sem fazer backup", "94"],
    ],
    (30, 58, 12),
)
pdf.sub("Cuidados na cópia")
pdf.itens([
    "A cópia é feita em fluxo único, mais rápida que arquivo por arquivo: 1.898 arquivos (106 MB) em cerca de 12 segundos no teste.",
    "A quantidade copiada é conferida contra a quantidade no celular.",
    "O espaço em disco é verificado antes de copiar.",
    "Nomes de arquivo inválidos no Windows e caminhos longos são tratados.",
    "Se o cabo soltar ou o técnico cancelar, o relatório é gerado assim mesmo, com as categorias restantes marcadas como não executadas.",
    "\"Backup concluído\" e 100% só aparecem quando todas as etapas terminaram sem pendência.",
])

# ---------- 12 ----------
pdf.capitulo("Instalação e uso")
pdf.sub("No computador atual")
pdf.p("Abrir o arquivo iniciar.bat na pasta C:\\dev\\backup-celular.")
pdf.sub("Em outro computador")
pdf.itens([
    "Instalar o Python 3.11 ou mais novo.",
    "Copiar a pasta do projeto.",
    "Criar o ambiente: python -m venv .venv",
    "Instalar as dependências: .venv\\Scripts\\pip install -r requirements.txt",
    "Baixar o platform-tools do Android e extrair em tools\\, de modo que exista tools\\platform-tools\\adb.exe.",
], numerados=True)
pdf.sub("Validar um modelo novo de celular")
pdf.p(
    "Conectar o aparelho e rodar .venv\\Scripts\\python diagnostico.py. Ele mostra o que foi lido, "
    "o que não foi e por quê, com os valores mascarados e sem fazer backup."
)

# ---------- 13 ----------
pdf.capitulo("Testes e validação")
pdf.p(
    "São 69 testes automáticos, todos passando. Eles usam um celular simulado que reproduz também "
    "os casos ruins: acesso negado, tela bloqueada, dado inexistente e queda de conexão. Os testes "
    "da tela abrem a janela de verdade."
)
pdf.t2(
    [
        ["Aparelho", "Versão", "O que foi executado"],
        ["Galaxy A16 (SM-A166M)", "Android 16", "Identificação pela tela atual; backup de contatos, SMS, chamadas e apps; "
                                                 "cópia de uma pasta de Android\\data; backup completo na versão anterior"],
        ["Galaxy A15 (SM-A156M)", "Android 15", "Backup completo na versão anterior"],
        ["iPhone", "-", "Nenhum aparelho real; só a detecção, com dados simulados"],
    ],
    (28, 17, 55),
)
pdf.sub("Números do Galaxy A16")
pdf.t2(
    [
        ["Item", "Resultado"],
        ["Tempo da identificação", "Cerca de 7 segundos"],
        ["Informações lidas", "26 lidas, 2 não obtidas (nome do perfil e nome do usuário local)"],
        ["Contatos", "109"],
        ["SMS", "295 mensagens: 16 com pessoas, 279 excluídas pelo filtro"],
        ["Chamadas", "1.115"],
        ["Apps listados", "74, dos quais 41 instalados pelo usuário"],
        ["Armazenamento a copiar", "14 pastas, 4,4 GB"],
    ],
    (35, 65),
)
pdf.p("Os testes simulados não substituem um backup completo pela tela com aparelho real.")

# ---------- 14 ----------
pdf.capitulo("Histórico do desenvolvimento")
pdf.p("Todo o desenvolvimento descrito aqui ocorreu em 29/09/2026.")
pdf.t2(
    [
        ["Etapa", "O que foi feito"],
        ["1. Definição", "Levantamento da ideia e decisão por um programa no computador via cabo, em vez de aplicativo no celular"],
        ["2. Primeira versão", "Cópia de arquivos, SMS, contatos, chamadas, apps, relatório em PDF e manifesto"],
        ["3. Preenchimento automático", "Leitura de IMEI, linha, conta e nome ao conectar, sem substituir o que foi digitado"],
        ["4. Primeiros testes reais", "Dois backups completos, no Galaxy A16 e no Galaxy A15"],
        ["5. Dados por extenso", "detalhes.pdf, sms.txt, apps com nome e histórico de uso; leitura do número pela tela"],
        ["6. Layout novo", "Tela refeita com customtkinter conforme o layout aprovado"],
        ["7. Identificação e cobertura", "Situação, fonte e motivo de cada leitura; sugestões de funcionário; vários aparelhos; "
                                         "troca de aparelho; cobertura por categoria; detecção de iPhone"],
    ],
    (28, 72),
)
pdf.sub("Defeitos encontrados e corrigidos")
pdf.t2(
    [
        ["Defeito", "Efeito"],
        ["O aviso de \"acesso negado\" do Android era descartado", "Leitura negada aparecia como campo vazio"],
        ["O mesmo ocorria na coleta de SMS, contatos e chamadas", "Uma recusa seria registrada como \"0 mensagens\", com sucesso"],
        ["A leitura pela tela não verificava o bloqueio", "Esperava 10 segundos e falhava sem avisar"],
        ["O nome do funcionário era escolhido sem mostrar a origem", "Um palpite aparecia como fato"],
        ["A troca de aparelho mantinha os dados do anterior", "Risco de backup com dados do funcionário errado"],
        ["Falha inesperada fazia a identificação se repetir", "Nova tentativa a cada 3 segundos"],
        ["O relatório marcava 100% ao gerar o PDF", "Indicava conclusão antes da hora"],
    ],
    (50, 50),
)

# ---------- 15 ----------
pdf.capitulo("Pendências e próximos passos")
pdf.t2(
    [
        ["Pendência", "Como validar"],
        ["Backup completo (com arquivos e WhatsApp) pela tela atual", "Rodar com tudo marcado em um aparelho de teste"],
        ["Galaxy A15 na versão atual", "Conectar e rodar o diagnostico.py"],
        ["Aparelho que não seja Samsung", "Rodar o diagnostico.py; os códigos de IMEI e linha podem mudar"],
        ["Escolha entre dois aparelhos", "Ligar dois celulares ao mesmo tempo"],
        ["Escalas 100% e 150% do Windows", "Trocar a escala e abrir o programa"],
        ["Exportação das conversas do WhatsApp em texto", "Testar com o aparelho desbloqueado"],
        ["Suporte a iPhone", "Ver a seção Recursos por plataforma"],
        ["Controle de versão (git)", "Ainda não configurado"],
    ],
    (50, 50),
)

# ---------- 16 ----------
pdf.capitulo("Segurança e privacidade")
pdf.itens([
    "Senhas, tokens de sessão e códigos de autenticação não são coletados.",
    "O texto das mensagens excluídas pelo filtro de SMS não é gravado.",
    "Os backups contêm dados pessoais (mensagens, contatos, fotos). O acesso à pasta de destino deve ser restrito ao TI.",
    "Se houver conteúdo pessoal do funcionário no aparelho, a LGPD se aplica a ele.",
    "Os arquivos em registros\\ guardam identificadores reais dos aparelhos (IMEI, linha, e-mails) e merecem o mesmo cuidado.",
    "A consulta do nome dos apps envia só o nome do pacote à Play Store e pode ser desligada.",
])

SAIDA.parent.mkdir(parents=True, exist_ok=True)
pdf.output(str(SAIDA))
print("gerado:", SAIDA, "| paginas:", pdf.page_no(), "| bytes:", SAIDA.stat().st_size)
