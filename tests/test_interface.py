"""Protege a ligação entre a tela e o backup: aparelhos, identificação, validação e estados.

A janela é aberta de verdade (fora da área visível), mas o aparelho e o backup são simulados.
"""
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import customtkinter as ctk  # noqa: E402

from backup import adb, captura, cobertura, conectores, executar, leitura  # noqa: E402
from interface import estado, janela  # noqa: E402

A15 = conectores.Aparelho("Android", "R58X000", "pronto", "SM A155M", "device")
A16 = conectores.Aparelho("Android", "R9AT0B2", "pronto", "SM A166M", "device")
IPHONE = conectores.Aparelho("iPhone", "00008110", "sem_suporte", "Apple iPhone", conectores.MOTIVO_IPHONE)
IMEIS = {"R58X000": "356938035643809", "R9AT0B2": "490154203237518"}


def identificacao_de(aparelho, candidatos=(("João Silva", "e-mail corporativo joao.silva@forest.ind.br"),),
                     nao_obtidas=True):
    registro = leitura.Registro(aparelho.id)
    registro.coletado(leitura.GRUPO_APARELHO, "Modelo", aparelho.modelo, "propriedade do sistema")
    registro.coletado(leitura.GRUPO_APARELHO, "IMEI 1", IMEIS[aparelho.id], "serviço de telefonia")
    if nao_obtidas:
        registro.anotar(
            leitura.GRUPO_CHIPS, "Número da linha", leitura.NEGADO, metodo="4 fontes",
            motivo="tabela de chips: acesso negado",
        )
    nomes = [captura.Candidato(nome, [fonte]) for nome, fonte in candidatos]
    campos = {"imei": captura.Sugestao(IMEIS[aparelho.id], "serviço de telefonia")}
    if len(nomes) == 1:
        campos["funcionario"] = captura.Sugestao(nomes[0].nome, "sugerido por " + nomes[0].fontes[0])
    return captura.Identificacao("Android", aparelho.id, f"Samsung {aparelho.modelo}", registro.leituras, nomes, campos)


def cobertura_de(aparelho, recusadas=()):
    return {
        chave: cobertura.Cobertura(
            chave,
            cobertura.INDISPONIVEL if chave in recusadas else cobertura.DISPONIVEL,
            "Sem acesso: o Android recusou a leitura" if chave in recusadas else "Leitura liberada pelo aparelho",
        )
        for chave in cobertura.CATEGORIAS
    }


class Regras(unittest.TestCase):
    def test_situacoes_do_aparelho(self):
        sem_autorizar = conectores.Aparelho("Android", "a", "autorizar", "", "unauthorized")
        sem_resposta = conectores.Aparelho("Android", "a", "sem_resposta", "", "offline")
        casos = [
            (([],), "nenhum"),
            (([], "", "R58X000"), "interrompida"),
            (([sem_autorizar],), "autorizar"),
            (([sem_resposta],), "sem_resposta"),
            (([A15, A16],), "escolher"),
            (([A15, A16], "R9AT0B2"), "conectado"),
            (([IPHONE],), "sem_suporte"),
            (("adb.exe não encontrado",), "erro"),
            (([A15],), "conectado"),
        ]
        for argumentos, codigo in casos:
            self.assertEqual(estado.situacao_do_aparelho(*argumentos).codigo, codigo, argumentos)
        escolhido = estado.situacao_do_aparelho([A15, A16], "R9AT0B2")
        self.assertEqual((escolhido.titulo, escolhido.serial), ("SM A166M", "R9AT0B2"))
        self.assertIs(escolhido.origem, A16)

    def test_so_aparelho_pronto_e_sem_impedimento_libera_o_backup(self):
        with tempfile.TemporaryDirectory() as pasta:
            dados = {"funcionario": "João", "tecnico": "Bruno"}
            pronto = estado.situacao_do_aparelho([A15])
            self.assertEqual(estado.validar(dados, {"sms": True}, pasta, pronto), {})
            for aparelhos in ([], [IPHONE], [A15, A16], "falha"):
                erros = estado.validar(dados, {"sms": True}, pasta, estado.situacao_do_aparelho(aparelhos))
                self.assertEqual(set(erros), {"aparelho"}, aparelhos)
            self.assertIn("iPhone", estado.validar(dados, {"sms": True}, pasta, estado.situacao_do_aparelho([IPHONE]))["aparelho"])

    def test_validacao_aponta_cada_pendencia(self):
        with tempfile.TemporaryDirectory() as pasta:
            conectado = estado.situacao_do_aparelho([A15])
            erros = estado.validar({"funcionario": " ", "tecnico": ""}, {"sms": False}, "", estado.PROCURANDO)
            self.assertEqual(set(erros), {"aparelho", "funcionario", "tecnico", "opcoes", "destino"})
            self.assertEqual([p for _, p in estado.verificacoes(erros)], [False, False, False])

            dados = {"funcionario": "João", "tecnico": "Bruno"}
            so_destino = estado.validar(dados, {"sms": True}, pasta + "-nao-existe", conectado)
            self.assertEqual(set(so_destino), {"destino"})
            self.assertEqual([p for _, p in estado.verificacoes(so_destino)], [True, True, False])

    def test_textos_no_singular_e_plural(self):
        self.assertEqual(
            [estado.contador(n) for n in (0, 1, 6)], ["Nenhum selecionado", "1 selecionado", "6 selecionados"]
        )
        self.assertEqual(
            [estado.resumo_do_log(n) for n in (0, 1, 3)], ["Nenhuma atividade", "1 evento", "3 eventos"]
        )

    def test_resultado_segue_o_que_o_backup_devolveu(self):
        pendencia = [executar.Etapa("SMS", "Falhou", "sem permissão")]
        self.assertEqual(estado.resultado([], False, "C:\\x")[:2], ("sucesso", "Backup concluído"))
        self.assertEqual(estado.resultado(pendencia, False, "C:\\x")[:2], ("aviso", "Concluído com pendências"))
        self.assertEqual(estado.resultado(pendencia, True, "C:\\x")[:2], ("aviso", "Cancelado"))

    def test_resultado_da_categoria_mostra_a_pior_situacao(self):
        etapas = [executar.Etapa("Apps", "OK", "41 apps"), executar.Etapa("Contas", "Falhou", "sem resposta")]
        self.assertEqual(
            estado.situacao_da_categoria(etapas), ("erro", "Falhou: Apps: 41 apps; Contas: sem resposta")
        )
        self.assertEqual(
            estado.situacao_da_categoria([executar.Etapa("SMS", "OK", "2 conversas")]), ("sucesso", "OK: 2 conversas")
        )
        self.assertIsNone(estado.situacao_da_categoria([]))

    def test_leitura_negada_aparece_com_motivo_no_log(self):
        negada = leitura.Leitura("Chips e linha", "Número da linha", leitura.NEGADO, metodo="siminfo", motivo="recusado")
        linha = estado.linha_de_leitura(negada)
        self.assertEqual(linha, "[Acesso negado] Número da linha: recusado  (método: siminfo)")
        self.assertEqual(estado.tom_da_mensagem(linha), "aviso")
        self.assertEqual(estado.tom_da_mensagem("[Falha] Bateria: formato inesperado"), "erro")
        self.assertEqual(estado.tom_da_mensagem("[Não encontrado] Perfil: sem nome"), "")


class Tela(unittest.TestCase):
    no_cabo = [A15]
    candidatos = (("João Silva", "e-mail corporativo joao.silva@forest.ind.br"),)
    recusadas = ()

    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.no_cabo = list(type(self).no_cabo)
        self.resultado = executar.Resultado(Path(self.pasta.name), [executar.Etapa("SMS", "OK", "2 conversas", "sms")])
        self.rodar = mock.Mock(side_effect=lambda *a: self.resultado)
        self.identificar = mock.Mock(side_effect=lambda a: identificacao_de(a, self.candidatos))
        for alvo, nome, substituto in [
            (conectores, "listar", lambda com_iphone=True: list(self.no_cabo)),
            (conectores, "listar_iphones", lambda: []),
            (conectores, "identificar", self.identificar),
            (conectores, "levantar_cobertura", lambda a: cobertura_de(a, self.recusadas)),
            (conectores, "fazer_backup", self.rodar),
            (janela, "ler_config", mock.Mock(return_value={"tecnico": "Bruno", "destino": self.pasta.name})),
            (janela, "CONFIG", Path(self.pasta.name) / "config.json"),
            (janela.os, "startfile", mock.Mock()),
            (janela.messagebox, "askyesno", mock.Mock(return_value=True)),
        ]:
            ativo = mock.patch.object(alvo, nome, substituto, create=True)
            ativo.start()
            self.addCleanup(ativo.stop)

        self.raiz = ctk.CTk()
        self.addCleanup(self.raiz.destroy)
        self.tela = janela.Janela(self.raiz)
        self.raiz.geometry("1100x700+5000+5000")
        self.esperar(lambda: self.tela.aparelho.codigo != "procurando" and not self.tela.identificando)

    def esperar(self, condicao, limite=25):
        fim = time.time() + limite
        while time.time() < fim:
            self.raiz.update()
            if condicao():
                return
            time.sleep(0.02)
        self.fail("a tela não chegou ao estado esperado")

    def trocar_cabo(self, *aparelhos):
        """Simula tirar e colocar aparelhos, sem esperar os 3 segundos da próxima consulta."""
        self.no_cabo[:] = aparelhos
        self.tela._recebeu_aparelhos(list(aparelhos))
        self.esperar(lambda: not self.tela.identificando)
        self.raiz.update()

    def campo(self, chave):
        return self.tela.campos[chave].obter()

    def selo(self):
        return self.tela.aparelho_selo.rotulo.cget("text")

    def clicar(self, rotulo):
        """Clique do mouse sobre um texto (o evento chega na parte interna do componente)."""
        rotulo._label.event_generate("<Button-1>")
        self.raiz.update()


class Identificacao(Tela):
    def test_identifica_sozinho_ao_conectar_e_preenche(self):
        self.identificar.assert_called_once()
        self.assertEqual((self.campo("imei"), self.campo("funcionario")), (IMEIS["R58X000"], "João Silva"))
        self.assertEqual(self.campo("tecnico"), "Bruno")
        self.assertEqual(self.selo(), "Pronto")
        self.assertEqual(self.tela.aparelho_titulo.cget("text"), "Samsung SM A155M")
        self.assertEqual(self.tela.botao_identificar.rotulo.cget("text"), "Identificar novamente")
        self.assertIn("Não obtido: 1 acesso negado", self.tela.aviso_captura.cget("text"))
        log = self.tela.painel_log.conteudo()
        self.assertIn("[Acesso negado] Número da linha: tabela de chips: acesso negado", log)
        self.assertIn("Sugestão de funcionário: João Silva (por e-mail corporativo", log)

    def test_nao_fica_identificando_de_novo_a_cada_consulta(self):
        for _ in range(3):
            self.tela._recebeu_aparelhos([A15])
        self.identificar.assert_called_once()

    def test_identificar_de_novo_nao_apaga_o_que_foi_digitado(self):
        self.tela.campos["funcionario"].definir("João da Silva Santos")
        self.tela.campos["setor"].definir("Expedição")
        self.tela._identificar()
        self.esperar(lambda: not self.tela.identificando)
        self.assertEqual(self.identificar.call_count, 2)
        self.assertEqual(self.campo("funcionario"), "João da Silva Santos")
        self.assertEqual(self.campo("setor"), "Expedição")
        self.assertIn("Mantido como você digitou: Funcionário", self.tela.aviso_captura.cget("text"))

    def test_falha_na_identificacao_mostra_o_motivo_e_nao_entra_em_repeticao(self):
        self.identificar.side_effect = adb.AdbErro("device offline")
        self.trocar_cabo(A16)
        self.tela._nova_sessao(limpar_tudo=True)
        self.esperar(lambda: not self.tela.identificando)
        self.assertEqual(self.selo(), "Falha na identificação")
        self.assertIn("device offline", self.tela.aparelho_ajuda.cget("text"))
        chamadas = self.identificar.call_count
        for _ in range(3):
            self.tela._recebeu_aparelhos([A16])
        self.assertEqual(self.identificar.call_count, chamadas)

    def test_aparelho_fora_do_cabo_vira_conexao_interrompida_e_mantem_os_dados(self):
        self.trocar_cabo()
        self.assertEqual(self.tela.aparelho_titulo.cget("text"), "Conexão interrompida")
        self.assertEqual(self.campo("imei"), IMEIS["R58X000"])
        self.tela._iniciar()
        self.rodar.assert_not_called()
        self.assertIn("saiu do cabo", self.tela.ajuda.cget("text"))

    def test_mesmo_aparelho_de_volta_continua_a_sessao(self):
        self.trocar_cabo()
        self.trocar_cabo(A15)
        self.assertFalse(self.tela.troca_pendente)
        self.assertEqual(self.selo(), "Pronto")
        self.assertEqual(self.campo("imei"), IMEIS["R58X000"])


class CandidatosConflitantes(Tela):
    candidatos = (("Maria Souza", "e-mail corporativo maria.souza@forest.ind.br"),
                  ("João Pedro", "nome dado ao aparelho (“A15 de João Pedro”)"))

    def test_nao_escolhe_sozinho_e_deixa_o_tecnico_decidir(self):
        self.assertEqual(self.campo("funcionario"), "")
        self.assertIn("mais de um nome possível", self.tela.aviso_captura.cget("text"))
        self.assertTrue(self.tela.quadro_candidatos.winfo_manager())
        self.tela._iniciar()
        self.rodar.assert_not_called()

        self.tela._usar_candidato("Maria Souza")
        self.assertEqual(self.campo("funcionario"), "Maria Souza")
        # escolha do técnico vale como digitada: uma nova identificação não troca
        self.tela._identificar()
        self.esperar(lambda: not self.tela.identificando)
        self.assertEqual(self.campo("funcionario"), "Maria Souza")


class TrocaDeAparelho(Tela):
    def test_outro_aparelho_nao_reaproveita_os_dados_em_silencio(self):
        self.tela.campos["setor"].definir("Expedição")
        self.trocar_cabo(A16)
        self.assertTrue(self.tela.troca_pendente)
        self.identificar.assert_called_once()  # o novo ainda não foi identificado
        self.assertEqual(self.campo("imei"), IMEIS["R58X000"])  # nada foi apagado sem decisão
        self.assertTrue(self.tela.aviso_troca.winfo_manager())
        self.tela._iniciar()
        self.rodar.assert_not_called()
        self.assertIn("outro aparelho", self.tela.ajuda.cget("text"))

    def test_nova_sessao_limpa_o_formulario_menos_o_tecnico(self):
        self.tela.campos["setor"].definir("Expedição")
        self.trocar_cabo(A16)
        self.tela._nova_sessao(limpar_tudo=True)
        self.esperar(lambda: not self.tela.identificando and self.tela.sessao == "R9AT0B2")
        self.assertEqual((self.campo("setor"), self.campo("tecnico")), ("", "Bruno"))
        self.assertEqual(self.campo("imei"), IMEIS["R9AT0B2"])
        self.assertFalse(self.tela.troca_pendente)
        self.assertEqual(self.tela.identificacao.serial, "R9AT0B2")

    def test_manter_o_digitado_troca_so_o_que_veio_do_aparelho(self):
        self.tela.campos["setor"].definir("Expedição")
        self.tela.campos["funcionario"].definir("Ana Lima")
        self.trocar_cabo(A16)
        self.tela._nova_sessao(limpar_tudo=False)
        self.esperar(lambda: not self.tela.identificando and self.tela.sessao == "R9AT0B2")
        self.assertEqual((self.campo("setor"), self.campo("funcionario")), ("Expedição", "Ana Lima"))
        self.assertEqual(self.campo("imei"), IMEIS["R9AT0B2"])

    def test_formulario_vazio_comeca_a_sessao_nova_direto(self):
        for chave in ("funcionario", "imei"):
            self.tela.campos[chave].definir("")
        self.trocar_cabo(A16)
        self.assertFalse(self.tela.troca_pendente)
        self.assertEqual(self.tela.sessao, "R9AT0B2")
        self.assertEqual(self.campo("imei"), IMEIS["R9AT0B2"])

    def test_backup_usa_o_aparelho_e_a_identificacao_da_sessao_atual(self):
        self.trocar_cabo(A16)
        self.tela._nova_sessao(limpar_tudo=True)
        self.esperar(lambda: not self.tela.identificando and self.tela.sessao == "R9AT0B2")
        self.tela._iniciar()
        self.esperar(lambda: not self.tela.trabalhando and self.rodar.called)
        aparelho, dados = self.rodar.call_args.args[:2]
        self.assertIs(aparelho, A16)
        self.assertEqual((dados.imei, dados.identificacao.serial), (IMEIS["R9AT0B2"], "R9AT0B2"))


class VariosAparelhos(Tela):
    no_cabo = [A15, A16]

    def test_pede_a_escolha_e_so_identifica_o_escolhido(self):
        self.assertEqual(self.tela.aparelho.codigo, "escolher")
        self.identificar.assert_not_called()
        self.assertTrue(self.tela.seletor.winfo_manager())
        self.tela._iniciar()
        self.rodar.assert_not_called()

        self.tela._escolheu_aparelho(A16.rotulo)
        self.esperar(lambda: not self.tela.identificando and self.tela.sessao)
        self.assertIs(self.identificar.call_args.args[0], A16)
        self.assertEqual(self.campo("imei"), IMEIS["R9AT0B2"])

        self.tela._recebeu_aparelhos([A15, A16])  # a próxima consulta não muda a escolha
        self.assertEqual(self.tela.aparelho.serial, "R9AT0B2")
        self.tela._iniciar()
        self.esperar(lambda: not self.tela.trabalhando and self.rodar.called)
        self.assertIs(self.rodar.call_args.args[0], A16)


class Iphone(Tela):
    no_cabo = [IPHONE]

    def test_iphone_e_detectado_mas_o_backup_fica_bloqueado_com_motivo(self):
        self.assertEqual(self.tela.aparelho.codigo, "sem_suporte")
        self.assertEqual(self.selo(), "Backup não suportado")
        self.assertIn("ainda não foi implementado", self.tela.aparelho_ajuda.cget("text"))
        self.tela.campos["funcionario"].definir("João")
        self.tela._iniciar()
        self.rodar.assert_not_called()
        self.assertIn("iPhone", self.tela.ajuda.cget("text"))


class CoberturaNaTela(Tela):
    recusadas = ("sms",)

    def test_categoria_recusada_fica_desmarcada_travada_e_com_motivo(self):
        sms, contatos = self.tela.opcoes["sms"], self.tela.opcoes["contatos"]
        self.assertFalse(sms.marcada)
        self.assertFalse(sms.ligada)
        self.assertIn("recusou", sms.descricao.cget("text"))
        self.assertTrue(contatos.marcada)
        self.assertEqual(contatos.descricao.cget("text"), "Leitura liberada pelo aparelho")
        self.assertEqual(self.tela.cartao_opcoes.lateral.cget("text"), "5 selecionados")
        self.clicar(sms.titulo)
        self.assertFalse(sms.marcada)

    def test_outro_aparelho_devolve_a_categoria(self):
        self.recusadas = ()
        self.trocar_cabo(A16)
        self.tela._nova_sessao(limpar_tudo=True)
        self.esperar(lambda: self.tela.opcoes["sms"].ligada)
        self.assertTrue(self.tela.opcoes["sms"].marcada)


class Backup(Tela):
    def test_cartao_e_caixa_alternam_uma_vez_so(self):
        opcao = self.tela.opcoes["sms"]
        self.assertEqual(self.tela.cartao_opcoes.lateral.cget("text"), "6 selecionados")
        self.clicar(opcao.titulo)  # clique na área do cartão
        self.assertFalse(opcao.marcada)
        self.assertEqual(self.tela.cartao_opcoes.lateral.cget("text"), "5 selecionados")
        opcao.caixa.toggle()  # clique na própria caixa
        self.assertTrue(opcao.marcada)
        self.assertEqual(self.tela.cartao_opcoes.lateral.cget("text"), "6 selecionados")

    def test_sem_obrigatorio_nao_inicia_e_mantem_o_formulario(self):
        self.tela.campos["funcionario"].definir("")
        self.tela.campos["setor"].definir("Expedição")
        self.tela._iniciar()
        self.raiz.update()
        self.rodar.assert_not_called()
        self.assertTrue(self.tela.campos["funcionario"].com_erro)
        self.assertEqual(self.campo("setor"), "Expedição")
        self.assertEqual(self.tela.situacao.cget("text"), "Não foi possível iniciar")

        self.tela.campos["funcionario"].definir("João")
        self.tela._editou()
        self.assertFalse(self.tela.campos["funcionario"].com_erro)
        self.assertEqual([v.pronto for v in self.tela.verificacoes], [True, True, True])

    def test_nada_marcado_nao_inicia(self):
        for opcao in self.tela.opcoes.values():
            opcao.marcar(False)
        self.tela._iniciar()
        self.rodar.assert_not_called()
        self.assertEqual(self.tela.erro_opcoes.cget("text"), "Marque pelo menos um item para copiar.")

    def test_inicia_uma_vez_com_os_dados_e_opcoes_da_tela(self):
        self.tela.campos["observacoes"].definir("Tela trincada")
        self.tela.opcoes["chamadas"].marcar(False)
        self.tela.botao_iniciar._acionar()  # Enter ou Espaço no botão
        self.assertTrue(self.tela.trabalhando or self.rodar.called)
        self.tela.botao_iniciar._acionar()  # segundo disparo enquanto roda: ignorado
        self.tela._iniciar()
        self.esperar(lambda: not self.tela.trabalhando and self.rodar.called)

        self.rodar.assert_called_once()
        aparelho, dados, opcoes, destino, tela = self.rodar.call_args.args
        self.assertEqual((aparelho, destino, tela), (A15, self.pasta.name, self.tela))
        self.assertEqual((dados.funcionario, dados.tecnico, dados.imei), ("João Silva", "Bruno", IMEIS["R58X000"]))
        self.assertEqual(dados.observacoes, "Tela trincada")
        self.assertIs(dados.identificacao, self.tela.identificacao)
        self.assertEqual(
            vars(opcoes),
            dict(arquivos=True, whatsapp=True, contatos=True, sms=True, chamadas=False, apps=True),
        )
        self.assertEqual(self.tela.situacao.cget("text"), "Backup concluído")
        self.assertEqual(self.tela.percentual.cget("text"), "100%")
        self.assertEqual(self.tela.opcoes["sms"].descricao.cget("text"), "OK: 2 conversas")
        self.assertTrue(self.tela.botao_iniciar.ligado)

    def test_pendencia_nao_aparece_como_sucesso(self):
        self.resultado.etapas = [
            executar.Etapa("Arquivos", "Parcial", "10 de 12 arquivos", "arquivos"),
            executar.Etapa("Chamadas", "Não executada", "Não chegou a rodar", "chamadas"),
        ]
        self.tela._iniciar()
        self.esperar(lambda: not self.tela.trabalhando and self.rodar.called)
        self.assertEqual(self.tela.situacao.cget("text"), "Concluído com pendências")
        self.assertEqual(self.tela.percentual.cget("text"), "")
        self.assertIn("10 de 12 arquivos", self.tela.ajuda.cget("text"))
        self.assertEqual(self.tela.opcoes["arquivos"].descricao.cget("text"), "Parcial: 10 de 12 arquivos")
        self.assertIn("Não executada", self.tela.opcoes["chamadas"].descricao.cget("text"))

    def test_falha_mostra_erro_e_libera_nova_tentativa(self):
        self.rodar.side_effect = adb.AdbErro("device offline")
        self.tela._iniciar()
        self.esperar(lambda: not self.tela.trabalhando and self.rodar.called)
        self.assertEqual(self.tela.situacao.cget("text"), "Falha no backup")
        self.assertIn("device offline", self.tela.painel_log.conteudo())
        self.assertTrue(self.tela.botao_iniciar.ligado)
        self.assertEqual(self.campo("funcionario"), "João Silva")

    def test_cancelamento_so_vira_cancelado_quando_o_backup_confirma(self):
        def rodar(aparelho, dados, opcoes, destino, tela):
            tela.progresso(0.4, "1.0 GB de 2.5 GB")
            while not tela.cancelado():
                time.sleep(0.02)
            return executar.Resultado(
                Path(self.pasta.name), [executar.Etapa("Backup", "Cancelado", "Interrompido")], True
            )

        self.rodar.side_effect = rodar
        self.tela._iniciar()
        self.esperar(lambda: self.tela.percentual.cget("text") == "40%")
        self.assertFalse(self.tela.botao_iniciar.ligado)
        self.assertTrue(self.tela.botao_cancelar.ligado)
        self.assertFalse(self.tela.campos["funcionario"].ligado)

        self.tela._cancelar()
        self.assertEqual(self.tela.situacao.cget("text"), "Cancelando…")
        self.esperar(lambda: not self.tela.trabalhando)
        self.assertEqual(self.tela.situacao.cget("text"), "Cancelado")
        self.assertFalse(self.tela.botao_cancelar.ligado)

    def test_log_recolhe_e_reabre_sem_perder_mensagens(self):
        painel = self.tela.painel_log
        painel.limpar()
        painel.escrever("SMS...")
        painel.escrever("  FALHOU: sem permissão")
        painel.alternar()
        painel.alternar()
        self.assertEqual(painel.conteudo(), "SMS...\n  FALHOU: sem permissão")
        self.assertEqual(painel.resumo.cget("text"), "2 eventos")

    def test_cancelar_a_escolha_da_pasta_mantem_o_destino(self):
        with mock.patch.object(janela.filedialog, "askdirectory", return_value=""):
            self.tela._escolher_destino()
        self.assertEqual(self.tela.destino, self.pasta.name)

    def test_janela_estreita_empilha_em_uma_coluna(self):
        self.tela._organizar(1100)
        self.assertEqual(self.tela.disposicao, (True, False))
        self.tela._organizar(800)
        self.assertEqual(self.tela.disposicao, (False, False))
        self.tela._organizar(600)
        self.assertEqual(self.tela.disposicao, (False, True))


del Tela  # é só a base: sem isto o unittest rodaria a classe sem nenhum teste próprio

if __name__ == "__main__":
    unittest.main()
