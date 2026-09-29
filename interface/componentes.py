"""Peças visuais reutilizadas pela janela. Nenhuma delas conhece o backup."""
import customtkinter as ctk

from . import estado, tema
from .icones import icone


def _pertence(widget, ancestral):
    while widget is not None:
        if widget is ancestral:
            return True
        widget = getattr(widget, "master", None)
    return False


def texto(master, conteudo="", fonte="normal", cor=tema.TEXTO, **opcoes):
    opcoes.setdefault("anchor", "w")
    opcoes.setdefault("justify", "left")
    opcoes.setdefault("height", 18)
    return ctk.CTkLabel(
        master, text=conteudo, font=tema.fonte(fonte), text_color=cor, fg_color="transparent", **opcoes
    )


class Botao(ctk.CTkFrame):
    """Botão com ícone e texto, acessível por teclado (Tab, Espaço e Enter)."""

    ESTILOS = {
        "principal": dict(
            fundo=tema.PRINCIPAL, sobre=tema.PRINCIPAL_SOBRE, cor=tema.SOBRE_PRINCIPAL, borda=tema.PRINCIPAL,
            fundo_desligado=tema.PRINCIPAL_DESLIGADO, cor_desligado=tema.SOBRE_PRINCIPAL,
            borda_desligado=tema.PRINCIPAL_DESLIGADO, fonte="botao_principal",
        ),
        "secundario": dict(
            fundo=tema.SUPERFICIE, sobre=tema.SELECIONADO, cor=tema.DESTAQUE, borda=tema.BORDA,
            fundo_desligado=tema.SUPERFICIE, cor_desligado=tema.TEXTO_APAGADO,
            borda_desligado=tema.BORDA, fonte="botao",
        ),
        "neutro": dict(
            fundo=tema.SUPERFICIE, sobre=tema.SUAVE, cor=tema.TEXTO, borda=tema.BORDA,
            fundo_desligado=tema.SUPERFICIE, cor_desligado=tema.TEXTO_APAGADO,
            borda_desligado=tema.BORDA, fonte="botao",
        ),
        "discreto": dict(
            fundo=tema.SUPERFICIE, sobre=tema.SUAVE, cor=tema.TEXTO_SECUNDARIO, borda=tema.SUPERFICIE,
            fundo_desligado=tema.SUPERFICIE, cor_desligado=tema.TEXTO_APAGADO,
            borda_desligado=tema.SUPERFICIE, fonte="botao",
        ),
    }

    def __init__(self, master, rotulo, comando, estilo="secundario", icone_esquerda=None,
                 icone_direita=None, altura=tema.ALTURA_BOTAO, espalhado=False, largura=0):
        self.estilo = self.ESTILOS[estilo]
        super().__init__(
            master, height=altura, width=largura or 120, corner_radius=tema.RAIO_BOTAO, border_width=1,
            fg_color=self.estilo["fundo"], border_color=self.estilo["borda"],
        )
        self.comando = comando
        self.ligado = True
        self.em_foco = False
        self.nomes_dos_icones = (icone_esquerda, icone_direita)
        self.grid_propagate(False)
        self.grid_rowconfigure(0, weight=1)

        self.esquerda = texto(self, height=20, width=20, anchor="center") if icone_esquerda else None
        self.rotulo = texto(self, rotulo, self.estilo["fonte"], height=20)
        self.direita = texto(self, height=20, width=20, anchor="center") if icone_direita else None

        if espalhado:  # ícone à esquerda, texto junto dele, seta na ponta direita
            self.grid_columnconfigure(1, weight=1)
            if self.esquerda:
                self.esquerda.grid(row=0, column=0, padx=(16, 8))
            self.rotulo.grid(row=0, column=1, sticky="w")
            if self.direita:
                self.direita.grid(row=0, column=2, padx=(8, 16))
        else:
            self.grid_columnconfigure((0, 4), weight=1)
            if self.esquerda:
                self.esquerda.grid(row=0, column=1, padx=(14, 8))
            self.rotulo.grid(row=0, column=2, padx=(0 if self.esquerda else 14, 0 if self.direita else 14))
            if self.direita:
                self.direita.grid(row=0, column=3, padx=(8, 14))

        self._canvas.configure(takefocus=True)
        self._canvas.bind("<FocusIn>", lambda e: self._foco(True))
        self._canvas.bind("<FocusOut>", lambda e: self._foco(False))
        self._canvas.bind("<KeyRelease-space>", self._acionar)
        self._canvas.bind("<Return>", self._acionar)
        for peca in (self, self.esquerda, self.rotulo, self.direita):
            if peca is not None:
                peca.bind("<Enter>", lambda e: self._pintar(sobre=True))
                peca.bind("<Leave>", self._saiu)
                peca.bind("<ButtonRelease-1>", self._clicou)
        self._pintar()

    def _pintar(self, sobre=False):
        e = self.estilo
        if self.ligado:
            fundo, cor, borda = (e["sobre"] if sobre else e["fundo"]), e["cor"], e["borda"]
        else:
            fundo, cor, borda = e["fundo_desligado"], e["cor_desligado"], e["borda_desligado"]
        self.configure(
            fg_color=fundo,
            border_color=tema.TEXTO if self.em_foco else borda,
            border_width=2 if self.em_foco else 1,
            cursor="hand2" if self.ligado else "arrow",
        )
        self.rotulo.configure(text_color=cor)
        for peca, nome in zip((self.esquerda, self.direita), self.nomes_dos_icones):
            if peca is not None:
                peca.configure(image=icone(nome, cor, 18), text="")

    def _saiu(self, evento):
        dentro = self.winfo_containing(evento.x_root, evento.y_root)
        if not _pertence(dentro, self):
            self._pintar()

    def _foco(self, em_foco):
        self.em_foco = em_foco
        self._pintar()

    def _clicou(self, evento):
        if _pertence(self.winfo_containing(evento.x_root, evento.y_root), self):
            self._canvas.focus_set()
            self._acionar()

    def _acionar(self, evento=None):
        if self.ligado and self.comando:
            self.comando()
        return "break"

    def ligar(self, ligado):
        self.ligado = bool(ligado)
        self._canvas.configure(takefocus=self.ligado)
        self._pintar()

    def rotular(self, rotulo):
        self.rotulo.configure(text=rotulo)


class Selo(ctk.CTkFrame):
    """Etiqueta de situação: bolinha + texto, com a cor do tom."""

    def __init__(self, master):
        super().__init__(master, corner_radius=6, height=24, fg_color=tema.NEUTRO_FUNDO)
        self.bolinha = texto(self, height=16, width=10, anchor="center")
        self.bolinha.grid(row=0, column=0, padx=(9, 4), pady=4)
        self.rotulo = texto(self, fonte="ajuda", height=16)
        self.rotulo.grid(row=0, column=1, padx=(0, 10), pady=4)

    def mostrar(self, rotulo, tom):
        cor, fundo = tema.TONS[tom]
        self.configure(fg_color=fundo)
        self.bolinha.configure(image=icone("ponto", cor, 10), text="")
        self.rotulo.configure(text=rotulo, text_color=cor)


class Cartao(ctk.CTkFrame):
    """Cartão branco com cabeçalho (ícone, título e um texto discreto à direita)."""

    def __init__(self, master, titulo, nome_do_icone, lateral=""):
        super().__init__(
            master, corner_radius=tema.RAIO_CARTAO, border_width=1,
            border_color=tema.BORDA, fg_color=tema.SUPERFICIE,
        )
        self.grid_columnconfigure(0, weight=1)
        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.grid(row=0, column=0, sticky="ew", padx=tema.PADDING_CARTAO, pady=(tema.PADDING_CARTAO, 0))
        topo.grid_columnconfigure(1, weight=1)
        texto(topo, height=22, width=20, image=icone(nome_do_icone, tema.DESTAQUE, 19)).grid(
            row=0, column=0, padx=(0, 10)
        )
        texto(topo, titulo, "cartao", height=22).grid(row=0, column=1, sticky="w")
        self.lateral = texto(topo, lateral, "pequena", tema.TEXTO_SECUNDARIO, anchor="e")
        self.lateral.grid(row=0, column=2, sticky="e")

        self.corpo = ctk.CTkFrame(self, fg_color="transparent")
        self.corpo.grid(
            row=1, column=0, sticky="nsew", padx=tema.PADDING_CARTAO, pady=(16, tema.PADDING_CARTAO)
        )
        self.corpo.grid_columnconfigure(0, weight=1)


class Campo(ctk.CTkFrame):
    """Rótulo em cima, campo embaixo e espaço para a mensagem de erro."""

    def __init__(self, master, rotulo, dica="", obrigatorio=False, linhas=1):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        self.linhas = linhas
        self.dica = dica
        self.mostrando_dica = False
        self.com_erro = False
        self.ligado = True

        nome = ctk.CTkFrame(self, fg_color="transparent")
        nome.grid(row=0, column=0, sticky="w", pady=(0, 6))
        texto(nome, rotulo, "rotulo").grid(row=0, column=0)
        if obrigatorio:
            texto(nome, "*", "rotulo", tema.DESTAQUE).grid(row=0, column=1, padx=(4, 0))

        comum = dict(
            corner_radius=tema.RAIO_CAMPO, border_width=1, border_color=tema.BORDA,
            fg_color=tema.CAMPO, text_color=tema.TEXTO, font=tema.fonte("normal"),
        )
        if linhas == 1:
            self.entrada = ctk.CTkEntry(
                self, height=tema.ALTURA_CAMPO, placeholder_text=dica,
                placeholder_text_color=tema.TEXTO_APAGADO, **comum,
            )
            self.interno = self.entrada._entry
        else:
            self.entrada = ctk.CTkTextbox(
                self, height=20 * linhas + 16, wrap="word", border_spacing=6,
                activate_scrollbars=False, **comum,
            )
            self.interno = self.entrada._textbox
            # no campo de várias linhas o Tab muda de campo em vez de escrever um tab
            self.interno.bind("<Tab>", self._proximo)
            self.interno.bind("<Shift-Tab>", self._anterior)
            self._dica(True)
        self.entrada.grid(row=1, column=0, sticky="ew")
        self.interno.bind("<FocusIn>", self._entrou, add="+")
        self.interno.bind("<FocusOut>", self._saiu, add="+")

        self.mensagem = texto(self, fonte="pequena", cor=tema.ERRO, wraplength=260)

    def _proximo(self, evento):
        evento.widget.tk_focusNext().focus_set()
        return "break"

    def _anterior(self, evento):
        evento.widget.tk_focusPrev().focus_set()
        return "break"

    def _dica(self, mostrar):
        """Placeholder do campo de várias linhas (o de uma linha já é do customtkinter)."""
        if self.linhas == 1 or mostrar == self.mostrando_dica:
            return
        self.mostrando_dica = mostrar
        self.entrada.delete("1.0", "end")
        if mostrar:
            self.entrada.insert("1.0", self.dica)
        self.entrada.configure(text_color=tema.TEXTO_APAGADO if mostrar else tema.TEXTO)

    def _borda(self, em_foco=False):
        if self.com_erro:
            cor = tema.ERRO
        else:
            cor = tema.DESTAQUE if em_foco else tema.BORDA
        self.entrada.configure(border_color=cor)

    def _entrou(self, evento):
        self._dica(False)
        self._borda(em_foco=True)

    def _saiu(self, evento):
        if self.linhas > 1 and not self.entrada.get("1.0", "end").strip():
            self._dica(True)
        self._borda()

    def obter(self):
        if self.linhas == 1:
            return self.entrada.get().strip()
        return "" if self.mostrando_dica else self.entrada.get("1.0", "end").strip()

    def definir(self, valor):
        estava_desligado = not self.ligado
        if estava_desligado:
            self.ligar(True)
        if self.linhas == 1:
            self.entrada.delete(0, "end")
            if valor:
                self.entrada.insert(0, valor)
            elif self.focus_get() is not self.interno:
                # o customtkinter só devolve a dica sozinho depois que o campo já teve foco
                self.entrada._activate_placeholder()
        else:
            self._dica(False)
            self.entrada.delete("1.0", "end")
            if valor:
                self.entrada.insert("1.0", valor)
            elif self.focus_get() is not self.interno:
                self._dica(True)
        if estava_desligado:
            self.ligar(False)

    def erro(self, mensagem=""):
        self.com_erro = bool(mensagem)
        self.mensagem.configure(text=mensagem)
        if mensagem:
            self.mensagem.grid(row=2, column=0, sticky="w", pady=(4, 0))
        else:
            self.mensagem.grid_remove()
        self._borda(em_foco=self.focus_get() is self.interno)

    def focar(self):
        self.interno.focus_set()

    def ligar(self, ligado):
        self.ligado = bool(ligado)
        self.entrada.configure(
            state="normal" if ligado else "disabled",
            fg_color=tema.CAMPO if ligado else tema.CAMPO_DESLIGADO,
        )

    def ao_mudar(self, funcao):
        self.interno.bind("<KeyRelease>", lambda e: funcao(), add="+")


class Opcao(ctk.CTkFrame):
    """Cartão selecionável de uma categoria: ícone, nome, descrição e caixa de seleção."""

    def __init__(self, master, titulo, descricao, nome_do_icone, ao_mudar, marcada=True):
        super().__init__(master, corner_radius=8, border_width=1, height=66)
        self.ao_mudar = ao_mudar
        self.ligada = True
        self.em_foco = False
        self.descricao_padrao = descricao
        self.indisponivel = False
        self.pedida = True
        self.marcada_antes = marcada
        self.nome_do_icone = nome_do_icone
        self.grid_columnconfigure(1, weight=1)

        self.figura = texto(self, height=22, width=22, anchor="center")
        self.figura.grid(row=0, column=0, rowspan=2, padx=(14, 12), pady=14)
        self.titulo = texto(self, titulo, "normal")
        self.titulo.grid(row=0, column=1, sticky="sw", pady=(13, 0))
        self.descricao = texto(self, descricao, "pequena", tema.TEXTO_SECUNDARIO, height=16, wraplength=250)
        self.descricao.grid(row=1, column=1, sticky="nw", pady=(1, 13))

        self.caixa = ctk.CTkCheckBox(
            self, text="", width=20, height=20, checkbox_width=18, checkbox_height=18,
            corner_radius=4, border_width=2, fg_color=tema.PRINCIPAL, hover_color=tema.PRINCIPAL_SOBRE,
            border_color=tema.TEXTO_APAGADO, checkmark_color=tema.SOBRE_PRINCIPAL,
            command=self._mudou,
        )
        self.caixa.grid(row=0, column=2, rowspan=2, padx=(8, 14))
        if marcada:
            self.caixa.select()

        # clicar em qualquer ponto do cartão alterna; a caixa cuida do próprio clique
        for peca in (self, self.figura, self.titulo, self.descricao):
            peca.bind("<Button-1>", self._clicou_no_cartao)
        self.caixa._canvas.configure(takefocus=True)
        self.caixa._canvas.bind("<FocusIn>", lambda e: self._foco(True))
        self.caixa._canvas.bind("<FocusOut>", lambda e: self._foco(False))
        self.caixa._canvas.bind("<KeyRelease-space>", self._clicou_no_cartao)
        self._pintar()

    @property
    def marcada(self):
        return bool(self.caixa.get())

    def marcar(self, marcada):
        if marcada:
            self.caixa.select()
        else:
            self.caixa.deselect()
        self._pintar()

    def informar(self, mensagem="", tom=""):
        """Troca a descrição pelo que se sabe do aparelho ou pelo resultado; vazio volta ao padrão."""
        cor = tema.TONS[tom][0] if tom in ("sucesso", "aviso", "erro") else tema.TEXTO_SECUNDARIO
        self.descricao.configure(text=mensagem or self.descricao_padrao, text_color=cor)

    def disponibilidade(self, disponivel, motivo=""):
        """Categoria que o aparelho não entrega fica desmarcada e travada, com o motivo à vista."""
        if not disponivel and not self.indisponivel:
            self.marcada_antes = self.marcada
            self.indisponivel = True
            self.caixa.deselect()
        elif disponivel and self.indisponivel:
            self.indisponivel = False
            if self.marcada_antes:
                self.caixa.select()
        if not disponivel:
            self.informar(motivo, "aviso")
        self.ligar(self.pedida)

    def _clicou_no_cartao(self, evento=None):
        if self.ligada:
            self.caixa._canvas.focus_set()
            self.caixa.toggle()  # chama _mudou pelo command da caixa
        return "break"

    def _mudou(self):
        self._pintar()
        self.ao_mudar()

    def _foco(self, em_foco):
        self.em_foco = em_foco
        self._pintar()

    def _pintar(self):
        marcada = self.marcada
        if self.em_foco:
            borda = tema.DESTAQUE
        else:
            borda = tema.SELECIONADO_BORDA if marcada else tema.BORDA
        self.configure(
            fg_color=tema.SELECIONADO if marcada else tema.SUPERFICIE,
            border_color=borda,
            border_width=2 if self.em_foco else 1,
            cursor="hand2" if self.ligada else "arrow",
        )
        cor = tema.DESTAQUE if self.ligada else tema.TEXTO_APAGADO
        self.figura.configure(image=icone(self.nome_do_icone, cor, 20), text="")
        self.titulo.configure(text_color=tema.TEXTO if self.ligada else tema.TEXTO_SECUNDARIO)

    def ligar(self, ligada):
        self.pedida = bool(ligada)
        self.ligada = self.pedida and not self.indisponivel
        self.caixa.configure(state="normal" if self.ligada else "disabled")
        self.caixa._canvas.configure(takefocus=self.ligada)
        self._pintar()


class Verificacao(ctk.CTkFrame):
    """Linha do cartão Preparação: indicador, o que é verificado e a situação por escrito."""

    def __init__(self, master, rotulo):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(1, weight=1)
        self.indicador = texto(self, height=18, width=12, anchor="center")
        self.indicador.grid(row=0, column=0, padx=(0, 9))
        texto(self, rotulo, "normal").grid(row=0, column=1, sticky="w")
        self.situacao = texto(self, fonte="ajuda", anchor="e")
        self.situacao.grid(row=0, column=2, sticky="e")
        self.mostrar(False)

    def mostrar(self, pronto):
        self.pronto = bool(pronto)
        if pronto:
            self.indicador.configure(image=icone("pronto", tema.SUCESSO, 12), text="")
            self.situacao.configure(text="Pronto", text_color=tema.SUCESSO)
        else:
            self.indicador.configure(image=icone("pendente", tema.TEXTO_SECUNDARIO, 12, 2.4), text="")
            self.situacao.configure(text="Pendente", text_color=tema.TEXTO_SECUNDARIO)


class PainelDeLog(ctk.CTkFrame):
    """"Detalhes da execução": uma linha quando recolhido, o log inteiro quando aberto."""

    def __init__(self, master):
        super().__init__(
            master, corner_radius=tema.RAIO_CARTAO, border_width=1,
            border_color=tema.BORDA, fg_color=tema.SUPERFICIE,
        )
        self.grid_columnconfigure(0, weight=1)
        self.aberto = False
        self.eventos = 0
        self.em_foco = False

        self.topo = ctk.CTkFrame(self, fg_color="transparent", height=50, corner_radius=tema.RAIO_CARTAO)
        self.topo.grid(row=0, column=0, sticky="ew", padx=5, pady=4)
        self.topo.grid_columnconfigure(1, weight=1)
        pecas = [
            texto(self.topo, height=22, width=20, image=icone("terminal", tema.TEXTO_SECUNDARIO, 18)),
            texto(self.topo, "Detalhes da execução", "normal", height=22),
        ]
        self.resumo = texto(self.topo, estado.resumo_do_log(0), "ajuda", tema.TEXTO_SECUNDARIO, anchor="e")
        self.seta = texto(self.topo, height=22, width=20, anchor="center")
        pecas[0].grid(row=0, column=0, padx=(15, 10), pady=11)
        pecas[1].grid(row=0, column=1, sticky="w")
        self.resumo.grid(row=0, column=2, sticky="e", padx=(8, 10))
        self.seta.grid(row=0, column=3, padx=(0, 15))
        for peca in [self.topo, self.resumo, self.seta, *pecas]:
            peca.bind("<Button-1>", self.alternar)
            peca.configure(cursor="hand2")
        self.topo._canvas.configure(takefocus=True)
        self.topo._canvas.bind("<FocusIn>", lambda e: self._foco(True))
        self.topo._canvas.bind("<FocusOut>", lambda e: self._foco(False))
        self.topo._canvas.bind("<KeyRelease-space>", self.alternar)
        self.topo._canvas.bind("<Return>", self.alternar)

        self.caixa = ctk.CTkTextbox(
            self, height=tema.ALTURA_LOG, wrap="word", font=tema.fonte("log"), corner_radius=6,
            border_width=1, border_color=tema.BORDA, fg_color=tema.CAMPO, text_color=tema.TEXTO,
            border_spacing=8, state="disabled",
        )
        self.caixa.tag_config("erro", foreground=tema.ERRO)
        self.caixa.tag_config("aviso", foreground=tema.AVISO)
        self._pintar()

    def _foco(self, em_foco):
        self.em_foco = em_foco
        self._pintar()

    def _pintar(self):
        self.seta.configure(image=icone("acima" if self.aberto else "abaixo", tema.TEXTO_SECUNDARIO, 18))
        self.configure(
            border_color=tema.DESTAQUE if self.em_foco else tema.BORDA,
            border_width=2 if self.em_foco else 1,
        )

    def alternar(self, evento=None):
        self.aberto = not self.aberto
        if self.aberto:
            self.caixa.grid(row=1, column=0, sticky="ew", padx=tema.PADDING_CARTAO, pady=(0, tema.PADDING_CARTAO))
        else:
            self.caixa.grid_remove()
        self._pintar()
        return "break"

    def escrever(self, mensagem):
        # só acompanha o fim se o usuário já estava no fim; lendo o começo, fica onde está
        no_fim = self.caixa.yview()[1] >= 0.999
        self.caixa.configure(state="normal")
        tom = estado.tom_da_mensagem(mensagem)
        self.caixa.insert("end", mensagem + "\n", (tom,) if tom else ())
        self.caixa.configure(state="disabled")
        if no_fim:
            self.caixa.see("end")
        self.eventos += 1
        self.resumo.configure(text=estado.resumo_do_log(self.eventos))

    def limpar(self):
        self.caixa.configure(state="normal")
        self.caixa.delete("1.0", "end")
        self.caixa.configure(state="disabled")
        self.eventos = 0
        self.resumo.configure(text=estado.resumo_do_log(0))

    def conteudo(self):
        return self.caixa.get("1.0", "end").rstrip("\n")
