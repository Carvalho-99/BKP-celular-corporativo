"""Janela principal: monta a tela e liga os componentes às rotinas de identificação e backup."""
import ctypes
import json
import os
import queue
import threading
from ctypes import wintypes
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from backup import adb, cobertura, conectores, executar, whatsapp

from . import estado, icones, tema
from .componentes import Botao, Campo, Cartao, Opcao, PainelDeLog, Selo, Verificacao, texto
from .icones import icone

CONFIG = Path(__file__).resolve().parent.parent / "config.json"
_BARRA_DE_ROLAGEM = 18
_MOLDURA_DA_JANELA = 40  # barra de título e bordas, que o Windows soma à altura pedida
_CONSULTAS_POR_IPHONE = 3  # a busca por iPhone é mais pesada: roda a cada 3 consultas do Android
_DADOS_DE_OUTRO_APARELHO = (
    "Os dados na tela são de outro aparelho. Escolha como continuar no aviso do aparelho."
)


def ler_config():
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def espacado(frase):
    """Letras levemente afastadas (o Tk não tem espaçamento entre letras)."""
    return "   ".join(" ".join(palavra) for palavra in frase.split())


class Janela(executar.Tela):
    def __init__(self, raiz):
        self.raiz = raiz
        self.fila = queue.Queue()
        self.cancelar = threading.Event()
        self.trabalhando = False
        self.identificando = False
        self.aparelho = estado.PROCURANDO
        self.aparelhos = []  # tudo que está no cabo agora
        self.iphones = []
        self.consultas = 0
        self.escolhido = ""  # aparelho selecionado quando há mais de um
        self.sessao = ""  # aparelho cujos dados estão no formulário
        self.identificacao = None  # o que foi lido do aparelho da sessão
        self.tentados = set()  # aparelhos já identificados sozinhos desde que entraram no cabo
        self.falha_na_identificacao = ""
        self.troca_pendente = False
        self.automatico = {}  # o que o programa preencheu sozinho, para não pisar no que foi digitado
        self.config = ler_config()
        self.destino = self.config.get("destino", "")
        self.resultado_na_tela = False
        self.fracao = 0
        self.disposicao = None
        self.largura_do_aviso = 600

        ctk.set_appearance_mode("light")
        tema.reiniciar()
        icones.reiniciar()
        raiz.title("Backup corporativo")
        raiz.configure(fg_color=tema.FUNDO)
        raiz.minsize(*tema.JANELA_MINIMA)
        self._montar()
        self._dimensionar()
        self._pintar_aparelho()
        self._atualizar()

        raiz.bind("<Configure>", self._redimensionou)
        self._procurar_aparelho()
        raiz.after(100, self._ler_fila)

    # ---------- montagem ----------

    def _montar(self):
        self._montar_barra_superior()
        self.rolagem = ctk.CTkScrollableFrame(
            self.raiz, fg_color=tema.FUNDO, corner_radius=0,
            scrollbar_button_color=tema.BORDA, scrollbar_button_hover_color=tema.TEXTO_APAGADO,
        )
        self.rolagem.pack(fill="both", expand=True)
        self.rolagem.grid_columnconfigure(0, weight=1)

        self.pagina = ctk.CTkFrame(self.rolagem, fg_color="transparent")
        self.pagina.grid(row=0, column=0, sticky="nsew", padx=(tema.MARGEM, tema.MARGEM - 8), pady=tema.MARGEM)
        self.pagina.grid_columnconfigure(0, weight=1)

        self._montar_cabecalho()
        self._montar_aparelho()
        self.esquerda = ctk.CTkFrame(self.pagina, fg_color="transparent")
        self.esquerda.grid_columnconfigure(0, weight=1)
        self.direita = ctk.CTkFrame(self.pagina, fg_color="transparent")
        self.direita.grid_columnconfigure(0, weight=1)
        # garante a largura da coluna direita mesmo com textos curtos
        ctk.CTkFrame(self.direita, fg_color="transparent", height=0, width=tema.LARGURA_COLUNA_DIREITA).grid(
            row=9, column=0
        )
        self._montar_dados()
        self._montar_opcoes()
        self._montar_destino()
        self._montar_preparacao()
        self.painel_log = PainelDeLog(self.pagina)

    def _montar_barra_superior(self):
        barra = ctk.CTkFrame(
            self.raiz, height=tema.ALTURA_BARRA_SUPERIOR, corner_radius=0, fg_color=tema.SUPERFICIE
        )
        barra.pack(fill="x")
        barra.pack_propagate(False)
        marca = ctk.CTkFrame(barra, width=32, height=32, corner_radius=8, fg_color=tema.PRINCIPAL)
        marca.pack(side="left", padx=(tema.MARGEM, 12))
        marca.pack_propagate(False)
        texto(marca, image=icone("arquivo", tema.SOBRE_PRINCIPAL, 18), anchor="center").pack(expand=True)
        texto(barra, "Backup corporativo", "marca", height=24).pack(side="left")
        ctk.CTkFrame(self.raiz, height=1, corner_radius=0, fg_color=tema.BORDA).pack(fill="x")

    def _montar_cabecalho(self):
        cabecalho = ctk.CTkFrame(self.pagina, fg_color="transparent")
        cabecalho.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(4, tema.ENTRE_BLOCOS))
        cabecalho.grid_columnconfigure(0, weight=1)
        texto(cabecalho, espacado("GESTÃO DE DISPOSITIVOS"), "sobretitulo", tema.DESTAQUE, height=16).grid(
            row=0, column=0, sticky="w"
        )
        texto(cabecalho, "Novo backup", "titulo", height=40).grid(row=1, column=0, sticky="w")
        texto(
            cabecalho, "Organize os dados do aparelho antes do desligamento.", "subtitulo",
            tema.TEXTO_SECUNDARIO, height=22,
        ).grid(row=2, column=0, sticky="w")
        self.conexao = texto(
            cabecalho, "  Conexão USB", "normal", tema.TEXTO_SECUNDARIO,
            image=icone("usb", tema.TEXTO_SECUNDARIO, 17), compound="left",
        )
        self.conexao.grid(row=1, column=1, sticky="e")

    def _montar_aparelho(self):
        cartao = ctk.CTkFrame(
            self.pagina, corner_radius=tema.RAIO_CARTAO, border_width=1,
            border_color=tema.BORDA, fg_color=tema.SUPERFICIE,
        )
        cartao.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, tema.ENTRE_BLOCOS))
        cartao.grid_columnconfigure(1, weight=1)
        ctk.CTkFrame(cartao, width=4, corner_radius=2, fg_color=tema.DESTAQUE).place(
            x=0, rely=0.5, relheight=0.76, anchor="w"
        )

        figura = ctk.CTkFrame(cartao, width=48, height=48, corner_radius=10, fg_color=tema.DESTAQUE_SUAVE)
        figura.grid(row=0, column=0, padx=(22, 16), pady=18, sticky="n")
        figura.pack_propagate(False)
        texto(figura, image=icone("celular", tema.DESTAQUE, 25), anchor="center").pack(expand=True)

        centro = ctk.CTkFrame(cartao, fg_color="transparent")
        centro.grid(row=0, column=1, sticky="ew", pady=16)
        centro.grid_columnconfigure(0, weight=1)
        # título e selo em um quadro próprio, para o texto de ajuda não afastar um do outro
        linha = ctk.CTkFrame(centro, fg_color="transparent")
        linha.grid(row=0, column=0, sticky="w")
        self.aparelho_titulo = texto(linha, fonte="aparelho", height=24)
        self.aparelho_titulo.grid(row=0, column=0, sticky="w")
        self.aparelho_selo = Selo(linha)
        self.aparelho_selo.grid(row=0, column=1, padx=(10, 0), sticky="w")
        self.aparelho_ajuda = texto(centro, fonte="normal", cor=tema.TEXTO_SECUNDARIO)
        self.aparelho_ajuda.grid(row=1, column=0, sticky="w", pady=(4, 0))

        # só aparece com mais de um aparelho no cabo
        self.seletor = ctk.CTkOptionMenu(
            centro, values=[""], command=self._escolheu_aparelho, height=34, width=320,
            corner_radius=tema.RAIO_CAMPO, font=tema.fonte("normal"), dropdown_font=tema.fonte("normal"),
            fg_color=tema.SUAVE, button_color=tema.BORDA, button_hover_color=tema.TEXTO_APAGADO,
            text_color=tema.TEXTO, dropdown_fg_color=tema.SUPERFICIE, dropdown_text_color=tema.TEXTO,
            dropdown_hover_color=tema.SELECIONADO,
        )

        # só aparece quando outro aparelho entra e o formulário ainda tem dados do anterior
        self.aviso_troca = ctk.CTkFrame(centro, corner_radius=8, fg_color=tema.AVISO_FUNDO)
        self.aviso_troca.grid_columnconfigure(0, weight=1)
        self.texto_troca = texto(self.aviso_troca, fonte="ajuda", cor=tema.AVISO)
        self.texto_troca.grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 6))
        botoes = ctk.CTkFrame(self.aviso_troca, fg_color="transparent")
        botoes.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 10))
        Botao(
            botoes, "Nova sessão (limpar formulário)", lambda: self._nova_sessao(limpar_tudo=True),
            "neutro", altura=32, largura=240,
        ).grid(row=0, column=0, padx=(0, 8))
        Botao(
            botoes, "Manter o que digitei", lambda: self._nova_sessao(limpar_tudo=False),
            "neutro", altura=32, largura=180,
        ).grid(row=0, column=1)

        self.botao_identificar = Botao(
            cartao, "Identificar", self._identificar, "secundario", icone_esquerda="identificar", largura=204
        )
        self.botao_identificar.grid(row=0, column=2, padx=(12, 20), pady=20, sticky="n")

    def _montar_dados(self):
        cartao = Cartao(self.esquerda, "Dados do desligamento", "pessoa", "* Obrigatórios")
        cartao.grid(row=0, column=0, sticky="ew", pady=(0, tema.ENTRE_BLOCOS))
        self.quadro_campos = cartao.corpo
        self.campos = {}
        for chave, rotulo, dica in estado.CAMPOS:
            campo = Campo(
                cartao.corpo, rotulo, dica, chave in estado.OBRIGATORIOS,
                linhas=3 if chave == "observacoes" else 1,
            )
            campo.ao_mudar(self._editou)
            self.campos[chave] = campo
        self.campos["tecnico"].definir(self.config.get("tecnico", ""))
        self.aviso_captura = texto(cartao.corpo, fonte="ajuda", cor=tema.DESTAQUE)
        self.quadro_candidatos = ctk.CTkFrame(cartao.corpo, fg_color="transparent")

    def _montar_opcoes(self):
        self.cartao_opcoes = Cartao(self.esquerda, "O que copiar", "copiar")
        self.cartao_opcoes.grid(row=1, column=0, sticky="ew")
        self.quadro_opcoes = self.cartao_opcoes.corpo
        self.opcoes = {
            chave: Opcao(self.quadro_opcoes, titulo, descricao, figura, self._editou)
            for chave, titulo, descricao, figura in estado.OPCOES
        }
        self.erro_opcoes = texto(self.quadro_opcoes, fonte="pequena", cor=tema.ERRO)

    def _montar_destino(self):
        cartao = Cartao(self.direita, "Destino do backup", "pasta")
        cartao.grid(row=0, column=0, sticky="ew", pady=(0, tema.ENTRE_BLOCOS))
        texto(cartao.corpo, "Salvar em", "rotulo").grid(row=0, column=0, sticky="w", pady=(0, 8))

        caixa = ctk.CTkFrame(cartao.corpo, corner_radius=8, fg_color=tema.SUAVE)
        caixa.grid(row=1, column=0, sticky="ew")
        caixa.grid_columnconfigure(1, weight=1)
        texto(caixa, height=22, width=20, image=icone("pasta", tema.DESTAQUE, 19)).grid(
            row=0, column=0, padx=(14, 10), pady=(14, 0), sticky="n"
        )
        self.destino_nome = texto(caixa, fonte="forte", wraplength=190)
        self.destino_nome.grid(row=0, column=1, sticky="w", pady=(14, 0), padx=(0, 12))
        self.destino_caminho = texto(caixa, fonte="pequena", cor=tema.TEXTO_SECUNDARIO, wraplength=190)
        self.destino_caminho.grid(row=1, column=1, sticky="w", pady=(2, 14), padx=(0, 12))

        self.erro_destino = texto(cartao.corpo, fonte="pequena", cor=tema.ERRO, wraplength=250)
        self.botao_destino = Botao(
            cartao.corpo, "Alterar pasta", self._escolher_destino, "neutro", icone_esquerda="pasta"
        )
        self.botao_destino.grid(row=3, column=0, sticky="ew", pady=(14, 0))

    def _montar_preparacao(self):
        cartao = Cartao(self.direita, "Preparação", "preparar")
        cartao.grid(row=1, column=0, sticky="ew")
        corpo = cartao.corpo
        self.verificacoes = []
        for linha, (rotulo, _) in enumerate(estado.verificacoes({})):
            item = Verificacao(corpo, rotulo)
            item.grid(row=linha, column=0, sticky="ew", pady=(0, 12))
            self.verificacoes.append(item)

        situacao = ctk.CTkFrame(corpo, fg_color="transparent")
        situacao.grid(row=3, column=0, sticky="ew", pady=(10, 8))
        situacao.grid_columnconfigure(0, weight=1)
        self.situacao = texto(situacao, fonte="normal", wraplength=200)
        self.situacao.grid(row=0, column=0, sticky="w")
        self.percentual = texto(situacao, fonte="forte", cor=tema.DESTAQUE, anchor="e")
        self.percentual.grid(row=0, column=1, sticky="e")

        self.barra = ctk.CTkProgressBar(
            corpo, height=tema.ALTURA_PROGRESSO, corner_radius=3, fg_color=tema.BORDA,
            progress_color=tema.PRINCIPAL, border_width=0,
        )
        self.barra.set(0)
        self.barra.grid(row=4, column=0, sticky="ew")
        self.ajuda = texto(corpo, fonte="ajuda", cor=tema.TEXTO_SECUNDARIO, wraplength=250)
        self.ajuda.grid(row=5, column=0, sticky="ew", pady=(10, 16))

        self.botao_iniciar = Botao(
            corpo, "Iniciar backup", self._iniciar, "principal", icone_esquerda="baixar",
            icone_direita="seta", altura=tema.ALTURA_BOTAO_PRINCIPAL, espalhado=True,
        )
        self.botao_iniciar.grid(row=6, column=0, sticky="ew")
        self.botao_cancelar = Botao(corpo, "Cancelar", self._cancelar, "discreto", altura=36)
        self.botao_cancelar.grid(row=7, column=0, sticky="ew", pady=(6, 0))
        self.botao_cancelar.ligar(False)

    # ---------- tamanho e adaptação ----------

    def _dimensionar(self):
        """Abre perto de 1100 x 820, sem passar da área livre do monitor."""
        self.raiz.update_idletasks()
        escala = self.raiz._get_window_scaling()
        area = wintypes.RECT()
        try:
            ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(area), 0)
            livre = (area.right - area.left, area.bottom - area.top)
        except (AttributeError, OSError):
            area.left = area.top = 0
            livre = (self.raiz.winfo_screenwidth(), self.raiz.winfo_screenheight() - 60)
        largura = int(min(tema.JANELA[0], livre[0] / escala - 16))
        altura = int(min(tema.JANELA[1], livre[1] / escala - _MOLDURA_DA_JANELA))
        x = area.left + max(0, (livre[0] - largura * escala) / 2)
        y = area.top + max(0, (livre[1] - (altura + _MOLDURA_DA_JANELA) * escala) / 2)
        self.raiz.geometry(f"{largura}x{altura}+{int(x)}+{int(y)}")
        self._organizar(largura)
        # a área de rolagem abre um pouco abaixo do topo enquanto a janela ainda está se ajustando
        for espera in (150, 700):
            self.raiz.after(espera, lambda: self.rolagem._parent_canvas.yview_moveto(0))

    def _redimensionou(self, evento):
        if evento.widget is self.raiz:
            self._organizar(evento.width / self.raiz._get_window_scaling())

    def _organizar(self, largura_da_janela):
        util = largura_da_janela - 2 * tema.MARGEM - _BARRA_DE_ROLAGEM
        duas_colunas = util >= tema.LARGURA_UMA_COLUNA
        largura_esquerda = util - (tema.LARGURA_COLUNA_DIREITA + tema.ENTRE_COLUNAS if duas_colunas else 0)
        empilhado = largura_esquerda < tema.LARGURA_CAMPOS_EMPILHADOS
        nova = (duas_colunas, empilhado)
        if nova != self.disposicao:
            self.disposicao = nova
            self._posicionar_colunas(duas_colunas)
            self._posicionar_campos(empilhado)
            self._posicionar_opcoes(empilhado)
            self.conexao.grid() if util >= 520 else self.conexao.grid_remove()

        self.aparelho_ajuda.configure(wraplength=max(180, util - 290))
        self.texto_troca.configure(wraplength=max(180, util - 400))
        self.largura_do_aviso = max(200, largura_esquerda - 50)
        self.aviso_captura.configure(wraplength=self.largura_do_aviso)
        self.erro_opcoes.configure(wraplength=max(200, largura_esquerda - 50))
        largura_da_opcao = largura_esquerda - 40 if empilhado else (largura_esquerda - 54) / 2
        for opcao in self.opcoes.values():
            opcao.descricao.configure(wraplength=max(140, largura_da_opcao - 110))
        largura_direita = tema.LARGURA_COLUNA_DIREITA if duas_colunas else util
        miolo = largura_direita - 2 * tema.PADDING_CARTAO - 4
        self.destino_nome.configure(wraplength=miolo - 60)
        self.destino_caminho.configure(wraplength=miolo - 60)
        self.erro_destino.configure(wraplength=miolo)
        self.ajuda.configure(wraplength=miolo)
        self.situacao.configure(wraplength=miolo - 50)

    def _posicionar_colunas(self, duas_colunas):
        if duas_colunas:
            self.pagina.grid_columnconfigure(1, weight=0)
            self.esquerda.grid(row=2, column=0, columnspan=1, sticky="new", padx=(0, tema.ENTRE_COLUNAS), pady=0)
            self.direita.grid(row=2, column=1, sticky="new", pady=0)
            self.painel_log.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(tema.ENTRE_BLOCOS, 0))
        else:
            self.esquerda.grid(row=2, column=0, columnspan=2, sticky="new", padx=0, pady=0)
            self.direita.grid(row=3, column=0, columnspan=2, sticky="new", pady=(tema.ENTRE_BLOCOS, 0))
            self.painel_log.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(tema.ENTRE_BLOCOS, 0))

    def _posicionar_campos(self, empilhado):
        quadro = self.quadro_campos
        quadro.grid_columnconfigure(0, weight=1, uniform="" if empilhado else "campos")
        quadro.grid_columnconfigure(1, weight=0 if empilhado else 1, uniform="" if empilhado else "campos")
        chaves = [chave for chave, _, _ in estado.CAMPOS]
        linha = 0
        for posicao, chave in enumerate(chaves):
            campo = self.campos[chave]
            inteiro = empilhado or chave == "observacoes"
            if inteiro:
                campo.grid(row=linha, column=0, columnspan=2, sticky="ew", padx=0, pady=(0, tema.ENTRE_CAMPOS))
                linha += 1
            else:
                coluna = posicao % 2
                campo.grid(
                    row=linha, column=coluna, columnspan=1, sticky="new",
                    padx=(0, 8) if coluna == 0 else (8, 0), pady=(0, tema.ENTRE_CAMPOS),
                )
                linha += coluna
        self.linha_do_aviso = linha

    def _posicionar_opcoes(self, empilhado):
        quadro = self.quadro_opcoes
        quadro.grid_columnconfigure(0, weight=1, uniform="" if empilhado else "opcoes")
        quadro.grid_columnconfigure(1, weight=0 if empilhado else 1, uniform="" if empilhado else "opcoes")
        for posicao, opcao in enumerate(self.opcoes.values()):
            if empilhado:
                opcao.grid(row=posicao, column=0, columnspan=2, sticky="ew", padx=0, pady=(0, 10))
            else:
                coluna = posicao % 2
                opcao.grid(
                    row=posicao // 2, column=coluna, columnspan=1, sticky="nsew",
                    padx=(0, 7) if coluna == 0 else (7, 0), pady=(0, 10),
                )

    # ---------- o que a tela mostra ----------

    def _dados(self):
        return {chave: campo.obter() for chave, campo in self.campos.items()}

    def _selecionadas(self):
        return {chave: opcao.marcada for chave, opcao in self.opcoes.items()}

    def _formulario_tem_dados(self):
        return any(campo.obter() for chave, campo in self.campos.items() if chave != "tecnico")

    def _identificacao_do_aparelho(self):
        """A identificação só vale para o aparelho de que foi lida."""
        if self.identificacao is not None and self.identificacao.serial == self.aparelho.serial:
            return self.identificacao
        return None

    def _editou(self):
        """Algo mudou no formulário: some a mensagem do backup anterior e refaz as verificações."""
        self.resultado_na_tela = False
        self._mostrar_candidatos()
        self._atualizar()

    def _atualizar(self):
        selecionadas = self._selecionadas()
        self.cartao_opcoes.lateral.configure(text=estado.contador(sum(selecionadas.values())))
        self._mostrar_destino()
        if self.trabalhando:
            return
        erros = estado.validar(self._dados(), selecionadas, self.destino, self.aparelho)
        for item, (_, pronto) in zip(self.verificacoes, estado.verificacoes(erros)):
            item.mostrar(pronto)
        # erros já mostrados somem assim que o problema é resolvido
        for chave, campo in self.campos.items():
            if campo.com_erro and chave not in erros:
                campo.erro()
        if "opcoes" not in erros:
            self._erro_em(self.erro_opcoes, "", linha=3)
        if "destino" not in erros:
            self._erro_em(self.erro_destino, "", linha=2)
        if self.resultado_na_tela:
            return
        self.situacao.configure(
            text="Aguardando preparação" if erros else "Pronto para iniciar", text_color=tema.TEXTO
        )
        self.percentual.configure(text="0%")
        self._barra(0)
        self.ajuda.configure(text=estado.o_que_falta(erros), text_color=tema.TEXTO_SECUNDARIO)

    def _erro_em(self, rotulo, mensagem, linha):
        rotulo.configure(text=mensagem)
        if mensagem:
            rotulo.grid(row=linha, column=0, columnspan=2, sticky="w", pady=(8, 0))
        else:
            rotulo.grid_remove()

    def _mostrar_destino(self):
        if self.destino:
            nome = os.path.basename(self.destino.rstrip("\\/")) or self.destino
            self.destino_nome.configure(text=nome)
            self.destino_caminho.configure(text=self.destino)
        else:
            self.destino_nome.configure(text="Nenhuma pasta escolhida")
            self.destino_caminho.configure(text="Use “Alterar pasta” para escolher.")

    def _barra(self, fracao):
        """fracao None = andamento sem total conhecido; número = parte já copiada."""
        if fracao is None:
            if self.barra.cget("mode") != "indeterminate":
                self.barra.configure(mode="indeterminate")
                self.barra.start()
            return
        if self.barra.cget("mode") != "determinate":
            self.barra.stop()
            self.barra.configure(mode="determinate")
        self.barra.set(max(0, min(1, fracao)))

    def _pintar_aparelho(self):
        """Cartão do aparelho: situação da conexão, mais o andamento da identificação."""
        aparelho = self.aparelho
        titulo, selo, tom, ajuda = aparelho.titulo, aparelho.selo, aparelho.tom, aparelho.ajuda
        identificacao = self._identificacao_do_aparelho()
        if aparelho.codigo in ("conectado", "sem_suporte") and not self.troca_pendente:
            if self.identificando:
                selo, tom = "Identificando", "andamento"
                ajuda = "Lendo as informações do aparelho. Deixe a tela do celular desbloqueada."
            elif identificacao is not None and aparelho.pronto:
                titulo, selo, tom = identificacao.titulo, "Pronto", "sucesso"
                ajuda = (
                    f"{len(identificacao.coletadas())} informações lidas, "
                    f"{len(identificacao.nao_obtidas())} não obtidas. {aparelho.ajuda}."
                )
            elif self.falha_na_identificacao and aparelho.pronto:
                selo, tom = "Falha na identificação", "erro"
                ajuda = f"{self.falha_na_identificacao} Use Identificar para tentar de novo."
        self.aparelho_titulo.configure(text=titulo)
        self.aparelho_selo.mostrar(selo, tom)
        self.aparelho_ajuda.configure(
            text=ajuda, text_color=tema.ERRO if tom == "erro" else tema.TEXTO_SECUNDARIO
        )
        if self.troca_pendente:
            self.texto_troca.configure(
                text=f"Outro aparelho foi conectado ({aparelho.titulo}). O formulário ainda tem os dados "
                "do aparelho anterior, e eles não serão usados neste sem a sua decisão."
            )
            self.aviso_troca.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        else:
            self.aviso_troca.grid_remove()

    def _mostrar_seletor(self):
        if len(self.aparelhos) > 1:
            rotulos = ["Escolha o aparelho"] + [a.rotulo for a in self.aparelhos]
            self.seletor.configure(values=rotulos[1:])
            atual = next((a.rotulo for a in self.aparelhos if a.id == self.escolhido), rotulos[0])
            self.seletor.set(atual)
            self.seletor.configure(state="disabled" if self.trabalhando else "normal")
            self.seletor.grid(row=2, column=0, sticky="w", pady=(10, 0))
        else:
            self.seletor.grid_remove()

    def _escolheu_aparelho(self, rotulo):
        escolhido = next((a for a in self.aparelhos if a.rotulo == rotulo), None)
        if escolhido is None or self.trabalhando:
            return
        self.escolhido = escolhido.id
        self._recebeu_aparelhos(self.aparelhos)

    # ---------- destino ----------

    def _escolher_destino(self):
        pasta = filedialog.askdirectory(
            parent=self.raiz, title="Onde salvar os backups", initialdir=self.destino or None
        )
        if pasta:  # cancelar a escolha mantém o destino anterior
            self.destino = os.path.normpath(pasta)
            self._editou()

    # ---------- aparelho ----------

    def _procurar_aparelho(self):
        if not self.trabalhando:
            threading.Thread(target=self._consultar_aparelhos, daemon=True).start()
        self.raiz.after(3000, self._procurar_aparelho)

    def _consultar_aparelhos(self):
        try:
            aparelhos = conectores.listar(com_iphone=False)
            if self.consultas % _CONSULTAS_POR_IPHONE == 0:
                self.iphones = conectores.listar_iphones()
            self.consultas += 1
            self.fila.put(("aparelhos", aparelhos + self.iphones))
        except adb.AdbErro as e:
            self.fila.put(("aparelhos", str(e)))

    def _recebeu_aparelhos(self, aparelhos):
        if not isinstance(aparelhos, str):
            self.aparelhos = aparelhos
            presentes = {a.id for a in aparelhos}
            if self.escolhido not in presentes:
                self.escolhido = ""
            self.tentados &= presentes  # quem saiu do cabo é identificado de novo quando voltar
            self._mostrar_seletor()
        self.aparelho = estado.situacao_do_aparelho(aparelhos, self.escolhido, self.sessao)

        self.troca_pendente = False
        if self.aparelho.codigo in ("conectado", "sem_suporte"):
            outro = self.sessao and self.sessao != self.aparelho.serial
            if outro and self._formulario_tem_dados():
                self.troca_pendente = True
                self.aparelho.impedimento = _DADOS_DE_OUTRO_APARELHO
            elif self.aparelho.serial not in self.tentados and self._identificacao_do_aparelho() is None:
                if outro:
                    self._esquecer_sessao()
                self._identificar()
        self._pintar_aparelho()
        self._atualizar()

    def _esquecer_sessao(self):
        self.sessao = ""
        self.identificacao = None
        self.automatico = {}
        self.falha_na_identificacao = ""
        for opcao in self.opcoes.values():
            opcao.disponibilidade(True)
            opcao.informar()
        self._aviso_captura("")
        self._mostrar_candidatos()

    def _nova_sessao(self, limpar_tudo):
        """Decisão do técnico quando troca de aparelho com dados do anterior na tela."""
        if self.trabalhando or self.identificando:
            return
        for chave, campo in self.campos.items():
            if chave == "tecnico":
                continue
            if limpar_tudo or campo.obter() == self.automatico.get(chave):
                campo.definir("")
                campo.erro()
        self.painel_log.escrever(
            "Nova sessão: formulário limpo para o novo aparelho." if limpar_tudo
            else "Novo aparelho: os campos preenchidos pelo aparelho anterior foram limpos; os digitados ficaram."
        )
        self._esquecer_sessao()
        self.troca_pendente = False
        self.aparelho.impedimento = ""
        self._identificar()
        self._pintar_aparelho()
        self._atualizar()

    def _identificar(self):
        if self.trabalhando or self.identificando:
            return
        if self.troca_pendente:
            self._nova_sessao(limpar_tudo=False)
            return
        if self.aparelho.codigo not in ("conectado", "sem_suporte"):
            # sem aparelho autorizado: procura de novo na hora, em vez de esperar a próxima consulta
            self.consultas = 0
            threading.Thread(target=self._consultar_aparelhos, daemon=True).start()
            return
        self.identificando = True
        self.falha_na_identificacao = ""
        self.tentados.add(self.aparelho.serial)
        self.botao_identificar.rotular("Identificando…")
        self.botao_identificar.ligar(False)
        self._aviso_captura("Lendo os dados do aparelho…")
        self._pintar_aparelho()
        threading.Thread(target=self._capturar, args=(self.aparelho.origem,), daemon=True).start()

    def _capturar(self, aparelho):
        try:
            self.fila.put(("captura", (aparelho.id, conectores.identificar(aparelho), "")))
        except Exception as e:  # noqa: BLE001 - o motivo aparece na tela e no log
            self.fila.put(("captura", (aparelho.id, None, f"{type(e).__name__}: {e}")))
            return
        try:
            self.fila.put(("cobertura", (aparelho.id, conectores.levantar_cobertura(aparelho))))
        except Exception as e:  # noqa: BLE001
            self.fila.put(("log", f"ERRO ao verificar o que o aparelho permite copiar: {e}"))

    def _aviso_captura(self, mensagem):
        self.aviso_captura.configure(text=mensagem)
        if mensagem:
            self.aviso_captura.grid(row=self.linha_do_aviso + 1, column=0, columnspan=2, sticky="w")
        else:
            self.aviso_captura.grid_remove()

    def _preencher(self, serial, identificacao, motivo):
        """Preenche só campo vazio ou que o próprio programa tinha preenchido antes."""
        self.identificando = False
        self.botao_identificar.rotular("Identificar novamente" if identificacao else "Identificar")
        self.botao_identificar.ligar(not self.trabalhando)
        if identificacao is None:
            self.falha_na_identificacao = f"A identificação falhou: {motivo}."
            self.painel_log.escrever(f"ERRO ao identificar o aparelho {serial}: {motivo}")
            self._aviso_captura("Não foi possível ler os dados do aparelho. Preencha os campos à mão.")
            self._pintar_aparelho()
            self._atualizar()
            return

        self.sessao = serial
        self.identificacao = identificacao
        self.painel_log.escrever(f"Identificação de {identificacao.titulo} ({identificacao.plataforma}, {serial}):")
        for leitura in identificacao.leituras:
            self.painel_log.escrever("  " + estado.linha_de_leitura(leitura))
        for candidato in identificacao.candidatos:
            self.painel_log.escrever(
                f"  Sugestão de funcionário: {candidato.nome} (por {'; '.join(candidato.fontes)})"
            )
        if identificacao.registro_em:
            self.painel_log.escrever(f"  Registro da identificação gravado em {identificacao.registro_em}")

        preenchidos, mantidos = [], []
        for chave in estado.CAPTURAVEIS:
            atual = self.campos[chave].obter()
            sugestao = identificacao.campos.get(chave)
            if atual and atual != self.automatico.get(chave):
                if sugestao and sugestao.valor != atual:
                    mantidos.append(estado.ROTULOS[chave])
                continue  # digitado pelo técnico
            valor = sugestao.valor if sugestao else ""
            self.campos[chave].definir(valor)
            self.automatico[chave] = valor
            if valor:
                preenchidos.append(estado.ROTULOS[chave])
        self._aviso_captura(estado.resumo_da_identificacao(identificacao, preenchidos, mantidos))
        self._pintar_aparelho()
        self._editou()

    def _mostrar_candidatos(self):
        """Nomes sugeridos pelo aparelho, com a fonte. O técnico escolhe; nada é decidido sozinho."""
        for antigo in self.quadro_candidatos.winfo_children():
            antigo.destroy()
        identificacao = self.identificacao
        atual = self.campos["funcionario"].obter()
        candidatos = identificacao.candidatos if identificacao else []
        if not candidatos or (not identificacao.conflito and atual == candidatos[0].nome):
            self.quadro_candidatos.grid_remove()
            return
        texto(
            self.quadro_candidatos,
            "Nomes sugeridos pelo aparelho (não comprovam quem usava o celular):",
            "ajuda", tema.TEXTO_SECUNDARIO,
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))
        for linha, candidato in enumerate(candidatos, start=1):
            quadro = ctk.CTkFrame(self.quadro_candidatos, fg_color="transparent")
            quadro.grid(row=linha, column=0, sticky="w", pady=(0, 6))
            Botao(
                quadro, f"Usar “{candidato.nome}”", lambda nome=candidato.nome: self._usar_candidato(nome),
                "neutro", altura=30, largura=min(360, 90 + 8 * len(candidato.nome)),
            ).grid(row=0, column=0, padx=(0, 10))
            texto(
                quadro, "fonte: " + "; ".join(candidato.fontes), "pequena", tema.TEXTO_SECUNDARIO,
                wraplength=max(200, self.largura_do_aviso - 230),
            ).grid(row=0, column=1, sticky="w")
        self.quadro_candidatos.grid(
            row=self.linha_do_aviso + 2, column=0, columnspan=2, sticky="w", pady=(10, 0)
        )

    def _usar_candidato(self, nome):
        if self.trabalhando:
            return
        self.campos["funcionario"].definir(nome)
        self.automatico.pop("funcionario", None)  # escolha do técnico: passa a valer como digitado
        self._editou()

    def _recebeu_cobertura(self, serial, coberturas):
        if self.identificacao is None or self.identificacao.serial != serial:
            return
        self.painel_log.escrever("O que este aparelho permite copiar:")
        for chave, c in coberturas.items():
            opcao = self.opcoes[chave]
            disponivel = c.situacao != cobertura.INDISPONIVEL
            opcao.disponibilidade(disponivel, c.resumo)
            if disponivel:
                opcao.informar(c.resumo)
            self.painel_log.escrever(f"  {c.nome}: {c.situacao}. {c.resumo}")
            if c.inacessivel:
                self.painel_log.escrever(f"    Não acessível: {c.inacessivel}")
        self._atualizar()

    # ---------- backup ----------

    def _iniciar(self):
        if self.trabalhando:
            return
        dados, selecionadas = self._dados(), self._selecionadas()
        erros = estado.validar(dados, selecionadas, self.destino, self.aparelho)
        if erros:
            self._mostrar_erros(erros)
            return

        self.config.update(destino=self.destino, tecnico=dados["tecnico"])
        try:
            CONFIG.write_text(json.dumps(self.config, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

        self.cancelar.clear()
        self.resultado_na_tela = False
        self.fracao = 0
        self.painel_log.limpar()
        self._trabalhando(True)
        self.situacao.configure(text="Iniciando o backup", text_color=tema.TEXTO)
        self.percentual.configure(text="")
        self.ajuda.configure(text="Não mexa no cabo durante a cópia.", text_color=tema.TEXTO_SECUNDARIO)
        self._barra(None)
        threading.Thread(
            target=self._rodar,
            args=(
                self.aparelho.origem,
                executar.Dados(**dados, identificacao=self._identificacao_do_aparelho()),
                executar.Opcoes(**selecionadas),
                self.destino,
            ),
            daemon=True,
        ).start()

    def _mostrar_erros(self, erros):
        primeiro = None
        for chave, campo in self.campos.items():
            campo.erro(erros.get(chave, ""))
            if chave in erros and primeiro is None:
                primeiro = campo
        self._erro_em(self.erro_opcoes, erros.get("opcoes", ""), linha=3)
        self._erro_em(self.erro_destino, erros.get("destino", ""), linha=2)
        if primeiro is not None:
            primeiro.focar()
        self.resultado_na_tela = False
        self._atualizar()
        self.situacao.configure(text="Não foi possível iniciar", text_color=tema.ERRO)
        self.ajuda.configure(text=next(iter(erros.values())), text_color=tema.ERRO)
        self.resultado_na_tela = True

    def _rodar(self, aparelho, dados, opcoes, destino):
        try:
            self.fila.put(("fim", conectores.fazer_backup(aparelho, dados, opcoes, destino, self)))
        except Exception as e:  # noqa: BLE001
            self.fila.put(("erro", str(e)))

    def _cancelar(self):
        if not self.trabalhando or self.cancelar.is_set():
            return
        if messagebox.askyesno(
            "Cancelar", "Parar o backup? O que já foi copiado fica na pasta.", parent=self.raiz
        ):
            self.cancelar.set()
            self.botao_cancelar.ligar(False)
            self.situacao.configure(text="Cancelando…", text_color=tema.AVISO)
            self.ajuda.configure(text="Aguardando a etapa em andamento parar.", text_color=tema.TEXTO_SECUNDARIO)

    def _trabalhando(self, sim):
        self.trabalhando = sim
        for campo in self.campos.values():
            campo.ligar(not sim)
        for opcao in self.opcoes.values():
            opcao.ligar(not sim)
        self.botao_destino.ligar(not sim)
        self.botao_iniciar.ligar(not sim)
        self.botao_identificar.ligar(not sim and not self.identificando)
        self.botao_cancelar.ligar(sim)
        self.seletor.configure(state="disabled" if sim else "normal")

    def _andamento(self, fracao, etapa):
        self._barra(fracao)
        if fracao is not None:
            self.fracao = fracao
        if self.cancelar.is_set():
            return  # mantém "Cancelando…" até o backup confirmar que parou
        if fracao is None:
            self.situacao.configure(text=etapa, text_color=tema.TEXTO)
            self.percentual.configure(text="")
            self.ajuda.configure(text="Não mexa no cabo durante a cópia.", text_color=tema.TEXTO_SECUNDARIO)
        else:
            self.situacao.configure(text="Copiando arquivos", text_color=tema.TEXTO)
            self.percentual.configure(text=f"{int(fracao * 100)}%")
            self.ajuda.configure(text=f"{etapa} copiados.", text_color=tema.TEXTO_SECUNDARIO)

    def _terminar(self, resultado):
        tom, situacao, explicacao = estado.resultado(resultado.problemas, resultado.cancelado, resultado.pasta)
        self._encerrar(tom, situacao, explicacao, completo=tom == "sucesso")
        for chave, opcao in self.opcoes.items():
            da_categoria = estado.situacao_da_categoria(resultado.da_categoria(chave))
            if da_categoria:
                opcao.informar(da_categoria[1], da_categoria[0])
        try:
            os.startfile(resultado.pasta)
        except OSError:
            pass

    def _falhou(self, motivo):
        self.painel_log.escrever(f"ERRO: {motivo}")
        self._encerrar("erro", "Falha no backup", motivo, completo=False)

    def _encerrar(self, tom, situacao, explicacao, completo):
        self._trabalhando(False)
        cor = tema.TONS[tom][0]
        # 100% só quando o backup confirmou que terminou sem pendência
        self._barra(1 if completo else self.fracao)
        self.percentual.configure(text="100%" if completo else "")
        self.situacao.configure(text=situacao, text_color=cor)
        self.ajuda.configure(text=explicacao, text_color=cor)
        self.resultado_na_tela = True
        self._atualizar()

    # ---------- chamados pela thread do backup (executar.Tela) ----------

    def log(self, mensagem):
        self.fila.put(("log", mensagem))

    def progresso(self, fracao, texto):
        self.fila.put(("progresso", (fracao, texto)))

    def cancelado(self):
        return self.cancelar.is_set()

    def confirmar_whatsapp(self, apps):
        resposta = {"pronto": threading.Event(), "fez": False}
        self.fila.put(("whatsapp", (apps, resposta)))
        resposta["pronto"].wait()
        return resposta["fez"]

    # ---------- fila: tudo que mexe na tela passa por aqui ----------

    def _ler_fila(self):
        ultimo_progresso = None
        try:
            while True:
                tipo, valor = self.fila.get_nowait()
                if tipo == "progresso":
                    ultimo_progresso = valor
                elif tipo == "log":
                    self.painel_log.escrever(valor)
                elif tipo == "aparelhos":
                    if not self.trabalhando and not self.identificando:
                        self._recebeu_aparelhos(valor)
                elif tipo == "captura":
                    self._preencher(*valor)
                elif tipo == "cobertura":
                    if not self.trabalhando:
                        self._recebeu_cobertura(*valor)
                elif tipo == "whatsapp":
                    self._perguntar_whatsapp(*valor)
                elif tipo == "fim":
                    ultimo_progresso = None
                    self._terminar(valor)
                elif tipo == "erro":
                    ultimo_progresso = None
                    self._falhou(valor)
        except queue.Empty:
            pass
        if ultimo_progresso and self.trabalhando:
            self._andamento(*ultimo_progresso)
        self.raiz.after(100, self._ler_fila)

    def _perguntar_whatsapp(self, apps, resposta):
        nomes = " e ".join(app.nome for app in apps)
        ultimo = "\n".join(f"  {app.nome}: {app.backup_texto}" for app in apps)
        self.situacao.configure(text="Aguardando o backup do WhatsApp", text_color=tema.TEXTO)
        resposta["fez"] = messagebox.askyesno(
            "Backup do WhatsApp",
            whatsapp.PASSOS_BACKUP.format(nome=nomes)
            + f"\n\nÚltimo backup encontrado:\n{ultimo}"
            + "\n\nClique em SIM depois que o backup terminar."
            + "\nClique em NÃO para continuar sem refazer o backup.",
            parent=self.raiz,
        )
        resposta["pronto"].set()


def abrir():
    raiz = ctk.CTk()
    Janela(raiz)
    raiz.mainloop()
