"""Testes da identificação, da coleta e do backup com um celular simulado."""
import csv
import hashlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backup import adb, arquivos, captura, cobertura, coleta, conectores, executar, leitura, nomes_apps, relatorio  # noqa: E402
from celular_falso import ARQUIVOS, CHIPS, IMEI_1, IMEI_2, LINHA, SMS, TELA_SOBRE, CelularFalso  # noqa: E402

# os testes não consultam a internet nem mexem no cache de nomes do programa
nomes_apps.CONSULTAR_PLAY_STORE = False
nomes_apps.CACHE = Path(tempfile.gettempdir()) / "backup-celular-teste-nomes.json"
nomes_apps.CACHE.write_text('{"com.whatsapp": "WhatsApp Messenger"}', encoding="utf-8")


class TelaFalsa(executar.Tela):
    def __init__(self, cancelar_em=""):
        self.mensagens = []
        self.cancelar_em = cancelar_em

    def log(self, mensagem):
        self.mensagens.append(mensagem)

    def cancelado(self):
        return bool(self.cancelar_em) and any(self.cancelar_em in m for m in self.mensagens)


def leituras_por_item(identificacao):
    return {l.item: l for l in identificacao.leituras}


class Formatos(unittest.TestCase):
    def test_mensagem_com_virgula_e_varias_linhas(self):
        registros = coleta.interpretar(SMS, ["address", "date", "type", "body"])
        self.assertEqual(len(registros), 4)
        self.assertEqual(registros[0]["body"], "Oi, tudo bem?\nsegunda linha, com virgula")
        self.assertEqual(registros[3]["body"], "")

    def test_operadora_e_numero_curto_nao_sao_pessoa(self):
        self.assertTrue(coleta.eh_pessoa("+5511999990001"))
        self.assertTrue(coleta.eh_pessoa("(11) 98888-0002"))
        for remetente in ("VIVO", "TIM", "4141", "27182", ""):
            self.assertFalse(coleta.eh_pessoa(remetente), remetente)

    def test_formato_de_linha(self):
        for numero in ("+5542999990001", "42999990001", "4232220001", "+55 42 99999-0001", "042999990001"):
            self.assertTrue(captura.eh_linha(numero), numero)
        for numero in (IMEI_1, "724060000000009", "89550000000000000001", "*555", "Desconhecido", ""):
            self.assertFalse(captura.eh_linha(numero), numero)

    def test_imei_precisa_de_formato_valido_e_nao_pode_ser_identidade_do_chip(self):
        self.assertTrue(captura.eh_imei(IMEI_1))
        self.assertFalse(captura.eh_imei("356938035643800"))  # dígito verificador errado
        self.assertTrue(captura.luhn_valido("724060000000009"))
        self.assertFalse(captura.eh_imei("724060000000009"))  # formato válido, mas é do chip

    def test_tela_so_vale_com_o_rotulo_do_campo(self):
        self.assertEqual(captura.numero_na_tela(TELA_SOBRE), "+55 42 99999-0001")
        self.assertEqual(captura.numero_na_tela(TELA_SOBRE.replace("+55 42 99999-0001", "Desconhecido")), "")
        outro_numero = '<hierarchy><node text="Suporte" /><node text="+55 42 99999-0001" /></hierarchy>'
        self.assertEqual(captura.numero_na_tela(outro_numero), "")

    def test_chips_com_valores_ocultos(self):
        chips = captura.ler_chips(CHIPS)
        self.assertEqual([c["compartimento"] for c in chips], [1, 2])  # o terceiro não está no aparelho
        self.assertEqual(chips[1]["inicio_da_linha"], "+5542")
        self.assertEqual((chips[0]["numero"], chips[0]["inicio_da_linha"]), ("", ""))

    def test_nome_pelo_email_so_com_nome_e_sobrenome(self):
        self.assertEqual(captura.nome_pelo_email("joao.silva@forest.ind.br"), "Joao Silva")
        self.assertEqual(captura.nome_pelo_email("vendas01@forest.ind.br"), "")

    def test_nomes_que_concordam_viram_um_candidato_so(self):
        candidatos = captura.juntar_candidatos(
            [("", "perfil"), ("Joao Silva", "e-mail corporativo"), ("Joao Silva Forest", "e-mail pessoal"),
             ("João", "nome do aparelho")]
        )
        self.assertEqual([c.nome for c in candidatos], ["Joao Silva"])
        self.assertEqual(len(candidatos[0].fontes), 3)

    def test_nomes_diferentes_ficam_como_candidatos_separados(self):
        candidatos = captura.juntar_candidatos([("Maria Souza", "e-mail"), ("João Pedro", "nome do aparelho")])
        self.assertEqual([c.nome for c in candidatos], ["Maria Souza", "João Pedro"])


class Identificacao(unittest.TestCase):
    def test_le_aparelho_chips_e_usuario_com_a_fonte_de_cada_dado(self):
        CelularFalso().ativar(self)
        r = captura.identificar("R58X000")
        itens = leituras_por_item(r)

        self.assertEqual(r.titulo, "Samsung SM-A155M")
        self.assertEqual(itens["Versão do Android"].valor, "14 (API 34)")
        self.assertEqual(itens["Armazenamento"].valor, "105.8 GB no total, 76.1 GB livres")
        self.assertEqual(itens["Bateria"].valor, "32%, carregando, saúde boa, 31,1 °C")
        self.assertEqual((itens["IMEI 1"].valor, itens["IMEI 2"].valor), (IMEI_1, IMEI_2))
        self.assertIn("código 4", itens["IMEI 2"].metodo)
        # série, identificador da conexão e IMEI são coisas diferentes e ficam em itens separados
        self.assertEqual(itens["Número de série"].metodo, "propriedade do sistema (ro.serialno)")
        self.assertEqual(itens["Identificador da conexão USB (ADB)"].metodo, "lista de aparelhos do ADB")

        linha = itens["Número da linha (chip do compartimento 2, VIVO)"]
        self.assertEqual(linha.valor, LINHA)
        self.assertIn("código 16", linha.metodo)
        self.assertIn("serviço de assinaturas: número oculto pelo Android", linha.metodo)

        self.assertEqual(itens["E-mail corporativo"].valor, "joao.silva@forest.ind.br")
        self.assertEqual(itens["Conta WhatsApp"].valor, "registrada, sem identificador visível")
        self.assertEqual(itens["Nome no perfil do aparelho"].situacao, leitura.NAO_ENCONTRADO)
        self.assertEqual(itens["Nome do usuário local"].situacao, leitura.NAO_ENCONTRADO)

        self.assertEqual({k: v.valor for k, v in r.campos.items()}, {
            "funcionario": "Joao Silva",
            "imei": f"{IMEI_1} / {IMEI_2}",
            "linha": LINHA,
            "conta_whatsapp": "joao.silva@gmail.com",
        })
        self.assertIn("e-mail corporativo", r.campos["funcionario"].fonte)
        self.assertIn("confirme", r.campos["conta_whatsapp"].fonte)

    def test_acesso_negado_aparece_como_negado_e_nao_como_vazio(self):
        CelularFalso(negar=("iphonesubinfo", "cmd phone", "telephony/siminfo"), tela_bloqueada=True).ativar(self)
        r = captura.identificar("R58X000")
        itens = leituras_por_item(r)

        self.assertEqual(itens["IMEI"].situacao, leitura.NEGADO)
        self.assertIn("*#06#", itens["IMEI"].motivo)
        self.assertNotIn("imei", r.campos)

        linha = itens["Número da linha"]
        self.assertEqual(linha.situacao, leitura.NAO_ENCONTRADO)
        for trecho in ("tabela de chips: acesso negado", "número oculto", "tela do celular está bloqueada"):
            self.assertIn(trecho, linha.motivo)
        self.assertNotIn("linha", r.campos)

    def test_tela_bloqueada_nao_e_aberta(self):
        celular = CelularFalso(linha_no_servico=False, tela_bloqueada=True).ativar(self)
        captura.identificar("R58X000")
        self.assertFalse([c for c in celular.comandos if c.startswith(("am start", "uiautomator"))])

    def test_le_a_linha_pela_tela_quando_as_outras_fontes_falham(self):
        celular = CelularFalso(linha_no_servico=False).ativar(self)
        r = captura.identificar("R58X000")
        self.assertEqual(r.campos["linha"].valor, "+55 42 99999-0001")
        self.assertIn("Sobre o telefone", r.campos["linha"].fonte)
        self.assertEqual(celular.comandos[celular.comandos.index("input keyevent KEYCODE_HOME") - 1][:11], "uiautomator")

    def test_falha_de_comunicacao_vira_falha_com_motivo(self):
        CelularFalso(cair_em="getprop").ativar(self)
        r = captura.identificar("R58X000")
        self.assertEqual(r.campos, {})
        self.assertFalse(r.coletadas()[1:])  # só sobra o identificador da conexão, que veio do ADB
        self.assertTrue(all(l.situacao == leitura.FALHA for l in r.nao_obtidas()))
        self.assertTrue(all(l.motivo for l in r.nao_obtidas()))

    def test_resposta_em_formato_inesperado_nao_derruba_a_identificacao(self):
        celular = CelularFalso().ativar(self)
        original = celular._normal
        celular._normal = lambda c: "level: muito\n" if c == "dumpsys battery" else original(c)
        with mock.patch.object(captura, "ler_chips", side_effect=KeyError("simSlotIndex")):
            r = captura.identificar("R58X000")
        itens = leituras_por_item(r)
        self.assertEqual(itens["Bateria"].situacao, leitura.FALHA)
        self.assertEqual(itens["Chips no aparelho"].situacao, leitura.FALHA)
        self.assertIn("KeyError", itens["Chips no aparelho"].motivo)
        self.assertEqual(r.campos["imei"].valor, f"{IMEI_1} / {IMEI_2}")  # o resto continua

    def test_nomes_conflitantes_nao_preenchem_o_funcionario(self):
        contas = "  Account {name=maria.souza@forest.ind.br, type=com.microsoft.workaccount}\n"
        CelularFalso(contas=contas, nome="A15 de João Pedro").ativar(self)
        r = captura.identificar("R58X000")
        self.assertTrue(r.conflito)
        self.assertEqual([c.nome for c in r.candidatos], ["Maria Souza", "João Pedro"])
        self.assertNotIn("funcionario", r.campos)

    def test_sem_nenhuma_pista_de_nome(self):
        CelularFalso(contas="Accounts: 0\n", nome="").ativar(self)
        r = captura.identificar("R58X000")
        self.assertEqual(r.candidatos, [])
        self.assertEqual(leituras_por_item(r)["Contas do aparelho"].situacao, leitura.NAO_ENCONTRADO)
        self.assertNotIn("conta_whatsapp", r.campos)

    def test_erro_so_no_canal_de_erro_e_percebido(self):
        resposta = adb.Resposta("", "java.lang.SecurityException: Access SIMINFO table from not phone/system UID", 0)
        self.assertEqual(leitura.problema(resposta)[0], leitura.NEGADO)
        self.assertEqual(leitura.problema(adb.Resposta("", "Can't find service: euicc", 0))[0], leitura.NAO_SUPORTADO)
        self.assertIsNone(leitura.problema(adb.Resposta("No result found.\n", "", 0)))
        self.assertIsNone(leitura.problema(adb.Resposta("Row: 0 body=Error ao abrir\n", "", 0)))


class Conectores(unittest.TestCase):
    def test_lista_android_e_iphone_juntos(self):
        lista = [
            {"serial": "R58X000", "estado": "device", "modelo": "SM A155M"},
            {"serial": "R7KM04C", "estado": "unauthorized", "modelo": ""},
        ]
        iphone = conectores.Aparelho(conectores.IPHONE, "00008110", conectores.SEM_SUPORTE, "Apple iPhone")
        with mock.patch.object(adb, "listar_aparelhos", return_value=lista), mock.patch.object(
            conectores, "listar_iphones", return_value=[iphone]
        ):
            aparelhos = conectores.listar()
        self.assertEqual(
            [(a.plataforma, a.id, a.estado) for a in aparelhos],
            [("Android", "R58X000", "pronto"), ("Android", "R7KM04C", "autorizar"), ("iPhone", "00008110", "sem_suporte")],
        )

    def test_iphone_visto_pelo_windows(self):
        um = '{"FriendlyName":"Apple iPhone","InstanceId":"USB\\\\VID_05AC&PID_12A8\\\\00008110001A2B3C","Status":"OK"}'
        self.assertEqual([a.id for a in conectores.interpretar_iphones(um)], ["00008110001A2B3C"])
        self.assertEqual(len(conectores.interpretar_iphones(f"[{um},{um}]")), 1)
        self.assertEqual(conectores.interpretar_iphones(""), [])
        self.assertEqual(conectores.interpretar_iphones("erro do powershell"), [])

    def test_iphone_e_reconhecido_mas_nao_promete_nada(self):
        iphone = conectores.interpretar_iphones(
            '{"FriendlyName":"Apple iPhone","InstanceId":"USB\\\\VID_05AC&PID_12A8\\\\00008110"}'
        )[0]
        with mock.patch.object(leitura.Registro, "gravar", return_value=None):
            r = conectores.identificar(iphone)
        self.assertEqual(r.plataforma, "iPhone")
        self.assertEqual(r.campos, {})
        self.assertTrue(all(l.situacao == leitura.NAO_IMPLEMENTADO for l in r.nao_obtidas()))
        self.assertTrue(conectores.motivo_para_nao_copiar(iphone))
        self.assertTrue(
            all(c.situacao == cobertura.INDISPONIVEL for c in conectores.levantar_cobertura(iphone).values())
        )
        with self.assertRaises(NotImplementedError):
            conectores.fazer_backup(iphone, None, None, "", None)


class Cobertura(unittest.TestCase):
    def test_mostra_o_que_cada_categoria_entrega(self):
        CelularFalso().ativar(self)
        c = cobertura.android("R58X000")
        self.assertEqual(set(c), set(cobertura.CATEGORIAS))
        self.assertEqual(c["contatos"].situacao, cobertura.DISPONIVEL)
        self.assertEqual(c["arquivos"].resumo, "4 pastas, 0.0 GB")
        self.assertIn("/data/data", c["arquivos"].inacessivel)
        self.assertEqual(c["whatsapp"].situacao, cobertura.PARCIAL)
        self.assertIn("criptografado", c["whatsapp"].legivel)
        self.assertIn("RCS", c["sms"].inacessivel)
        self.assertIn("não prova", c["apps"].inacessivel)

    def test_categoria_recusada_fica_indisponivel_com_motivo(self):
        CelularFalso(negar=("content://sms",), whatsapp=False).ativar(self)
        c = cobertura.android("R58X000")
        self.assertEqual(c["sms"].situacao, cobertura.INDISPONIVEL)
        self.assertIn("recusou", c["sms"].resumo)
        self.assertEqual(c["whatsapp"].resumo, "WhatsApp não instalado")
        self.assertEqual(c["chamadas"].situacao, cobertura.DISPONIVEL)

    def test_queda_de_conexao_nao_impede_o_levantamento_de_terminar(self):
        CelularFalso(cair_em="call_log").ativar(self)
        c = cobertura.android("R58X000")
        self.assertEqual(c["sms"].situacao, cobertura.PARCIAL)
        self.assertEqual(c["chamadas"].situacao, cobertura.INDISPONIVEL)
        self.assertIn("not found", c["apps"].resumo)


class Apps(unittest.TestCase):
    def test_lista_com_nome_origem_e_uso(self):
        CelularFalso().ativar(self)
        with tempfile.TemporaryDirectory() as pasta:
            lista = coleta.apps("x", Path(pasta))
        por_pacote = {a["pacote"]: a for a in lista}
        # systemui foi usado só 20s: fica de fora
        self.assertEqual(set(por_pacote), {"com.whatsapp", "com.microsoft.teams", "com.android.chrome"})
        self.assertEqual([a["pacote"] for a in lista][0], "com.whatsapp")  # usado por último

        whatsapp = por_pacote["com.whatsapp"]
        self.assertEqual(whatsapp["nome"], "WhatsApp Messenger")
        self.assertEqual(whatsapp["tempo_de_uso"], "41h 02min")
        self.assertEqual(whatsapp["ultimo_uso"], "29/09/2026 08:15")
        self.assertEqual(whatsapp["instalado"], "10/03/2025 14:30")

        self.assertEqual(por_pacote["com.android.chrome"]["origem"], "De fábrica")
        teams = por_pacote["com.microsoft.teams"]
        self.assertEqual(teams["nome"], "Microsoft Teams (nome provável)")
        self.assertEqual((teams["ultimo_uso"], teams["tempo_de_uso"]), ("", ""))


class Conversas(unittest.TestCase):
    def test_sms_agrupado_por_pessoa_e_filtro_documentado(self):
        CelularFalso().ativar(self)
        agenda = [("João Silva", "(11) 99999-0001")]
        with tempfile.TemporaryDirectory() as pasta:
            conversas, excluidas = coleta.sms("x", Path(pasta), agenda)
            texto = (Path(pasta) / "sms.txt").read_text(encoding="utf-8-sig")
            with open(Path(pasta) / "sms_filtro.csv", encoding="utf-8-sig", newline="") as f:
                filtro = list(csv.reader(f, delimiter=";"))[1:]
        self.assertEqual(excluidas, {"VIVO": 1, "4141": 1})
        self.assertEqual(len(conversas), 2)
        self.assertIn("Conversa com João Silva (+5511999990001) - 1 mensagens", texto)
        self.assertNotIn("fatura", texto)
        # o filtro guarda quem foi excluído e por quê, nunca o texto da mensagem
        self.assertEqual(
            sorted(filtro), [["4141", "menos de 8 dígitos", "1"], ["VIVO", "remetente com letras", "1"]]
        )


class Caminhos(unittest.TestCase):
    def test_nome_invalido_e_tentativa_de_sair_da_pasta(self):
        self.assertEqual(str(arquivos.caminho_seguro("./a/b:c?.jpg", set())), r"a\b_c_.jpg")
        self.assertEqual(str(arquivos.caminho_seguro("../../x/CON.txt", set())), r"x\_CON.txt")

    def test_nomes_que_so_mudam_a_caixa_nao_se_sobrescrevem(self):
        usados = set()
        self.assertEqual(str(arquivos.caminho_seguro("Foto.JPG", usados)), "Foto.JPG")
        self.assertEqual(str(arquivos.caminho_seguro("foto.jpg", usados)), "foto (2).jpg")


class BackupCompleto(unittest.TestCase):
    def rodar(self, celular, opcoes=None, tela=None):
        celular.ativar(self)
        temp = tempfile.mkdtemp()
        # o prefixo de caminho longo é necessário também para apagar
        self.addCleanup(shutil.rmtree, arquivos.longo(temp))
        try:
            identificacao = captura.identificar("R58X000", ler_tela=False)
        except adb.AdbErro:
            identificacao = None
        celular.caiu = False
        dados = executar.Dados(
            funcionario="João da Silva", tecnico="Bruno", linha="11 99999-0001", identificacao=identificacao
        )
        return executar.rodar("R58X000", dados, opcoes or executar.Opcoes(), temp, tela or TelaFalsa())

    def test_backup_inteiro(self):
        r = self.rodar(CelularFalso())
        self.assertEqual([(e.nome, e.situacao, e.detalhe) for e in r.problemas], [])
        self.assertFalse(r.cancelado)
        pasta = r.pasta

        with open(pasta / "dados" / "sms.csv", encoding="utf-8-sig", newline="") as f:
            self.assertEqual(len(list(csv.reader(f, delimiter=";"))), 3)  # cabeçalho + 2 com pessoas

        with open(pasta / "manifesto.csv", encoding="utf-8-sig", newline="") as f:
            manifesto = list(csv.reader(f, delimiter=";"))[1:]
        self.assertEqual(len(manifesto), len(ARQUIVOS))
        for relativo, tamanho, sha, _ in manifesto:
            with open(arquivos.longo(pasta / "arquivos" / relativo), "rb") as f:
                conteudo = f.read()
            self.assertEqual(len(conteudo), int(tamanho))
            self.assertEqual(hashlib.sha256(conteudo).hexdigest(), sha)
        self.assertTrue(any("Android\\data" in linha[0] for linha in manifesto))

        self.assertGreater((pasta / "relatorio.pdf").stat().st_size, 2000)
        self.assertGreater((pasta / "detalhes.pdf").stat().st_size, 2000)
        self.assertIn("Conversa com Silva, João", (pasta / "dados" / "sms.txt").read_text("utf-8-sig"))
        self.assertTrue((pasta / "log.txt").exists())

    def test_cada_etapa_diz_o_que_preservou_o_que_da_para_ler_e_o_que_nao(self):
        r = self.rodar(CelularFalso())
        etapas = {e.nome: e for e in r.etapas}
        self.assertEqual({e.categoria for e in r.etapas}, set(cobertura.CATEGORIAS))
        for etapa in r.etapas:
            self.assertTrue(etapa.preservado and etapa.legivel and etapa.inacessivel, etapa.nome)

        self.assertIn("2 mensagens de 2 remetentes excluídas pelo filtro", etapas["SMS"].detalhe)
        self.assertIn("sms_filtro.csv", etapas["SMS"].inacessivel)
        whatsapp = etapas["WhatsApp"]
        self.assertIn("2 arquivos do aplicativo, incluindo 1 banco(s) de conversas criptografado(s)", whatsapp.preservado)
        self.assertEqual(whatsapp.legivel, "mídias (fotos, vídeos, áudios e documentos)")
        self.assertIn("texto das conversas", whatsapp.inacessivel)
        self.assertIn("8 arquivos", etapas["Arquivos"].preservado)

    def test_relatorio_mostra_a_mesma_situacao_que_o_backup_devolveu(self):
        tabelas = []
        original = relatorio._Pdf.tabela

        def espiar(pdf, linhas, larguras, cabecalho=True):
            linhas = [list(map(str, linha)) for linha in linhas]
            tabelas.append(linhas)
            return original(pdf, linhas, larguras, cabecalho)

        with mock.patch.object(relatorio._Pdf, "tabela", espiar):
            r = self.rodar(CelularFalso(cortar_cabo_em="./DCIM", negar=("call_log",)))
        resultado = next(t for t in tabelas if t[0] == ["Etapa", "Situação", "Detalhe"])
        self.assertEqual(resultado[1:], [[e.nome, e.situacao, e.detalhe] for e in r.etapas])
        self.assertEqual(
            {linha[0]: linha[1] for linha in resultado[1:] if linha[1] != "OK"},
            {"Chamadas": "Falhou", "Arquivos": "Parcial"},
        )
        lidas = next(t for t in tabelas if t[0] == ["Informação", "Valor", "Fonte"])
        self.assertIn(["Modelo", "SM-A155M", "propriedade do sistema (ro.product.model)"], lidas)
        self.assertTrue(any(t[0] == ["Informação", "Situação", "Motivo"] for t in tabelas))
        self.assertTrue(any(t[0] == ["Nome sugerido", "De onde veio a sugestão"] for t in tabelas))

    def test_cabo_solto_no_meio_aparece_como_pendencia(self):
        r = self.rodar(CelularFalso(cortar_cabo_em="./DCIM"))
        self.assertEqual([e.nome for e in r.problemas], ["Arquivos"])
        self.assertIn("DCIM", r.problemas[0].detalhe)
        self.assertIn("DCIM", r.problemas[0].inacessivel)
        self.assertTrue((r.pasta / "relatorio.pdf").exists())

    def test_queda_de_conexao_deixa_as_categorias_restantes_como_nao_executadas(self):
        r = self.rodar(CelularFalso(cair_em="call_log"))
        situacoes = {e.nome: e.situacao for e in r.etapas}
        self.assertEqual(situacoes["Contatos"], "OK")
        self.assertEqual(situacoes["SMS"], "OK")
        self.assertEqual(situacoes["Backup"], "Falhou")
        self.assertIn("Conexão com o aparelho interrompida", next(e.detalhe for e in r.etapas if e.nome == "Backup"))
        for nome in ("Chamadas", "Apps e contas", "Arquivos e mídias"):
            self.assertEqual(situacoes[nome], "Não executada", nome)
        self.assertEqual(situacoes["WhatsApp"], "Falhou")  # a pasta dele não chegou a ser copiada
        self.assertFalse(r.cancelado)
        self.assertTrue((r.pasta / "relatorio.pdf").exists())

    def test_cancelamento_mantem_o_que_foi_feito_e_marca_o_resto(self):
        r = self.rodar(CelularFalso(), tela=TelaFalsa(cancelar_em="contatos"))
        situacoes = {e.nome: e.situacao for e in r.etapas}
        self.assertTrue(r.cancelado)
        self.assertEqual(situacoes["Contatos"], "OK")
        self.assertEqual(situacoes["Backup"], "Cancelado")
        self.assertEqual(situacoes["SMS"], "Não executada")
        self.assertTrue((r.pasta / "dados" / "contatos.csv").exists())

    def test_categoria_recusada_falha_sozinha_e_as_outras_seguem(self):
        r = self.rodar(CelularFalso(negar=("content://sms",)))
        self.assertEqual([(e.nome, e.situacao) for e in r.problemas], [("SMS", "Falhou")])
        self.assertIn("SecurityException", r.problemas[0].detalhe)

    def test_so_whatsapp_copia_so_a_pasta_dele(self):
        opcoes = executar.Opcoes(arquivos=False, sms=False, contatos=False, chamadas=False, apps=False)
        r = self.rodar(CelularFalso(), opcoes)
        self.assertEqual(r.problemas, [])
        copiados = sorted(p.name for p in (r.pasta / "arquivos").rglob("*") if p.is_file())
        self.assertEqual(copiados, ["foto.jpg", "msgstore.db.crypt14"])


if __name__ == "__main__":
    unittest.main()
