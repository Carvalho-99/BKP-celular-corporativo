"""Celular Android simulado: responde aos comandos do ADB como um aparelho responderia.

Serve para testar sem aparelho, inclusive os casos ruins: acesso negado,
tela bloqueada, dado inexistente e queda de conexão.
"""
import io
import tarfile
import time
from unittest import mock

from backup import adb

SMS = (
    "Row: 0 address=+5511999990001, date=1758000000000, type=1, body=Oi, tudo bem?\n"
    "segunda linha, com virgula\n"
    "Row: 1 address=VIVO, date=1758000001000, type=1, body=Sua fatura fechou\n"
    "Row: 2 address=4141, date=1758000002000, type=1, body=TIM: recarga\n"
    "Row: 3 address=(11) 98888-0002, date=1758000003000, type=2, body=NULL\n"
)


def parcel(texto):
    """Resposta do `service call` com o texto dado, no formato do Android."""
    linhas, pontilhado = [], "........" + "".join(c + "." for c in texto)
    for i in range(0, len(pontilhado), 16):
        linhas.append(f"  0x{i:08x}: 00000000 00000000 00000000 00000000 '{pontilhado[i:i + 16]}'")
    return "Result: Parcel(\n" + "\n".join(linhas) + ")\n"


PARCEL_VAZIO = "Result: Parcel(ffffffff 00000000   '........')\n"
IMEI_1, IMEI_2 = "356938035643809", "490154203237518"
IMSI = "724060000000009"  # identidade do chip: 15 dígitos, passa no dígito verificador, não é IMEI
LINHA = "+5542999990001"

PROPRIEDADES = (
    "[ro.product.manufacturer]: [samsung]\n[ro.product.model]: [SM-A155M]\n"
    "[ro.build.version.release]: [14]\n[ro.build.version.sdk]: [34]\n"
    "[ro.build.version.security_patch]: [2026-08-01]\n[ro.build.display.id]: [UP1A.A155MUBS]\n"
    "[ro.serialno]: [R58X000]\n[gsm.sim.state]: [LOADED,LOADED]\n[gsm.sim.operator.alpha]: [Vivo,VIVO]\n"
)
# formato real do Android 16: os valores ocultos vêm como [****], com colchetes dentro do bloco
CHIPS = (
    "    [SubscriptionInfoInternal: id=1 iccId=8955[****] simSlotIndex=1 portIndex=0 isEmbedded=0 "
    "carrierName=VIVO displayName=VIVO number=+5542[****] mcc=724 mnc=06 cardString=8955[****]]\n"
    "    [SubscriptionInfoInternal: id=2 iccId=8955[****] simSlotIndex=0 portIndex=0 isEmbedded=0 "
    "carrierName=Vivo displayName=Vivo number= mcc=724 mnc=06 cardString=8955[****]]\n"
    "    [SubscriptionInfoInternal: id=3 iccId=8955[****] simSlotIndex=-1 portIndex=0 isEmbedded=0 "
    "carrierName=TIM displayName=TIM number= mcc=724 mnc=02]\n"
)
BATERIA = "Current Battery Service state:\n  status: 2\n  health: 2\n  level: 32\n  scale: 100\n  temperature: 311\n"
DISCO = (
    "Filesystem       1K-blocks     Used Available Use% Mounted on\n"
    "/dev/block/dm-60 110958572 31075752  79751748  28% /data/user/0\n"
)
CONTAS = (
    "Accounts: 5\n"
    "  Account {name=joao.silva@gmail.com, type=com.google}\n"
    "  Account {name=Work account, type=com.microsoft.workaccount}\n"
    "  Account {name=joao.silva@forest.ind.br, type=com.microsoft.workaccount}\n"
    "  Account {name=joao.silva@forest.ind.br (forestpaper.com.br), type=com.microsoft.skydrive}\n"
    "  Account {name=WhatsApp, type=com.whatsapp}\n"
)
PACOTES = (
    "Packages:\n"
    "  Package [com.whatsapp] (a1b2c3):\n"
    "    versionName=2.26.10.5\n"
    "    lastUpdateTime=2026-09-01 08:00:00\n"
    "    User 0: ceDataInode=1 installed=true hidden=false\n"
    "      firstInstallTime=2025-03-10 14:30:00\n"
    "  Package [com.microsoft.teams] (d4e5f6):\n"
    "    versionName=1416/1.0.0\n"
    "    firstInstallTime=2025-01-05 09:00:00\n"
    "    lastUpdateTime=2026-08-20 10:00:00\n"
    "  Package [com.android.chrome] (0a0b0c):\n"
    "    versionName=140.0.1\n"
    "    firstInstallTime=2024-01-01 00:00:00\n"
    "  Package [com.android.systemui] (0d0e0f):\n"
    "    versionName=16\n"
)
USO = (
    "In-memory daily stats\n"
    '      package=com.whatsapp totalTimeUsed="12:30" lastTimeUsed="2026-09-29 08:15:00" appLaunchCount=4\n'
    '      package=com.android.chrome totalTimeUsed="05:00" lastTimeUsed="2026-09-28 20:00:00"\n'
    "In-memory yearly stats\n"
    '      package=com.whatsapp totalTimeUsed="41:02:03" lastTimeUsed="2026-09-29 08:15:00"\n'
    '      package=com.android.chrome totalTimeUsed="3:10:00" lastTimeUsed="2026-09-28 20:00:00"\n'
    '      package=com.android.systemui totalTimeUsed="00:20" lastTimeUsed="2026-09-29 09:00:00"\n'
    '      package=com.microsoft.teams totalTimeUsed="00:00" lastTimeUsed="1970-01-01 00:00:00"\n'
    "    time=\"2026-09-29 08:15:00\" type=ACTIVITY_RESUMED package=com.whatsapp\n"
)
TELA_SOBRE = (
    '<?xml version="1.0"?><hierarchy><node text="Sobre o telefone" /><node text="A15 de Jo&#227;o" />'
    '<node text="N&#250;mero de telefone" /><node text="+55 42 99999-0001" />'
    '<node text="N&#250;mero do modelo" /><node text="SM-A156M/DSN" /></hierarchy>'
)
NEGADO = (
    "Error while accessing provider:{}\n"
    "java.lang.SecurityException: Permission Denial: reading {} requires android.permission.READ\n"
    "\tat android.os.Parcel.createExceptionOrNull(Parcel.java:3388)\n"
)

ARQUIVOS = {
    "./DCIM/Camera/foto 1.jpg": b"foto-um" * 1000,
    "./DCIM/Camera/a:b?.jpg": b"nome invalido no windows",
    "./DCIM/Camera/Foto.JPG": b"maiuscula",
    "./DCIM/Camera/foto.jpg": b"minuscula",
    "./Download/" + "pasta-bem-comprida/" * 15 + "relatorio.pdf": b"caminho longo",
    "./Android/media/com.whatsapp/WhatsApp/Databases/msgstore.db.crypt14": b"banco",
    "./Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images/foto.jpg": b"midia",
    "./Android/data/com.intsig.camscanner/files/contrato.pdf": b"documento de app",
}
PASTAS = ("DCIM", "Download", "Android/media", "Android/data")


def montar_tar(prefixo):
    memoria = io.BytesIO()
    with tarfile.open(fileobj=memoria, mode="w") as tar:
        for nome, conteudo in ARQUIVOS.items():
            if nome.startswith(prefixo):
                membro = tarfile.TarInfo(nome)
                membro.size = len(conteudo)
                membro.mtime = 1758000000
                tar.addfile(membro, io.BytesIO(conteudo))
    memoria.seek(0)
    return memoria


class CelularFalso:
    """Por padrão é um aparelho que entrega tudo. Os parâmetros ligam os casos ruins.

    negar: trechos de comando que o Android recusa (ex.: "content://sms", "iphonesubinfo").
    cair_em: trecho de comando a partir do qual o cabo "solta" (toda consulta passa a falhar).
    cortar_cabo_em: pasta cuja cópia vem pela metade.
    """

    def __init__(self, negar=(), cair_em="", cortar_cabo_em="", tela_bloqueada=False,
                 linha_no_servico=True, perfil="", contas=CONTAS, nome="A15 de João",
                 tela=TELA_SOBRE, whatsapp=True):
        self.negar = tuple(negar)
        self.cair_em = cair_em
        self.cortar_cabo_em = cortar_cabo_em
        self.tela_bloqueada = tela_bloqueada
        self.linha_no_servico = linha_no_servico
        self.perfil = perfil
        self.contas = contas
        self.nome = nome
        self.tela = tela
        self.whatsapp = whatsapp
        self.caiu = False
        self.comandos = []

    # ---------- as duas portas de entrada do programa ----------

    def shell(self, comando, serial, timeout=60):
        saida, erro, _ = self._responder(comando)
        if not saida.strip() and erro:
            raise adb.AdbErro(erro.splitlines()[0])
        return saida

    def consultar(self, comando, serial, timeout=60):
        return adb.Resposta(*self._responder(comando))

    def stream(self, comando, serial):
        dados = montar_tar(self._prefixo(comando)).getvalue()
        if self.cortar_cabo_em and self.cortar_cabo_em in comando:
            dados = dados[:700]
        return mock.Mock(stdout=io.BytesIO(dados))

    def ativar(self, caso):
        """Liga o celular falso nos três pontos em que o programa fala com o ADB."""
        for nome in ("shell", "consultar", "stream"):
            ativo = mock.patch.object(adb, nome, getattr(self, nome))
            ativo.start()
            caso.addCleanup(ativo.stop)
        # sem esperar a tela do celular abrir e sem gravar a trilha na pasta registros\ do programa
        for alvo in ("backup.captura.time.sleep", "backup.leitura.Registro.gravar"):
            ativo = mock.patch(alvo, return_value=None)
            ativo.start()
            caso.addCleanup(ativo.stop)
        return self

    # ---------- respostas ----------

    def _responder(self, comando):
        self.comandos.append(comando)
        if self.cair_em and self.cair_em in comando:
            self.caiu = True
        if self.caiu:
            raise adb.AdbErro("adb.exe: device 'R58X000' not found")
        negado = next((n for n in self.negar if n in comando), None)
        if negado:
            if "iphonesubinfo" in comando:
                recusa = parcel("getImeiForSlot: The user 2000 does not meet the requirements to access device identifiers")
                return "@@1|s16 com.android.shell\n" + recusa, "", 0
            if comando.startswith("cmd phone"):
                return "", "Device IMEI: Permission denied.", 255
            return "", NEGADO.format(negado, negado), 0
        return self._normal(comando), "", 0

    def _normal(self, comando):
        if comando == "getprop":
            return PROPRIEDADES
        if comando == "date +%s":
            return str(int(time.time()) - 3600)
        if comando == "df -k /data":
            return DISCO
        if comando == "dumpsys battery":
            return BATERIA
        if comando == "dumpsys isub":
            return CHIPS
        if comando == "dumpsys window":
            return f"  isKeyguardShowing={'true' if self.tela_bloqueada else 'false'}\n"
        if comando == "dumpsys account":
            return self.contas
        if comando == "dumpsys package packages":
            return PACOTES
        if comando == "dumpsys usagestats":
            return USO
        if comando == "pm list users":
            return "Users:\n\tUserInfo{0:null:4c13} running\n"
        if comando == "pm list packages -3":
            return "package:com.whatsapp\npackage:com.microsoft.teams\n"
        if comando == "pm list packages":
            return ("package:com.whatsapp\n" if self.whatsapp else "") + "package:com.android.settings\n"
        if comando.startswith("settings get global device_name"):
            return self.nome + "\n" if self.nome else "null\n"
        if comando.startswith("settings get"):
            return "null\n"
        if comando.startswith("for c in") and "iphonesubinfo" in comando:
            return (
                "@@1|s16 com.android.shell\n" + parcel(IMEI_1)
                + "@@2|s16 com.android.shell\n" + PARCEL_VAZIO
                + "@@4|i32 1 s16 com.android.shell\n" + parcel(IMEI_2)
                + "@@8|s16 com.android.shell\n" + parcel(IMSI)
                + "@@9|s16 com.android.shell\n" + parcel("89550000000000000001")
                + ("@@16|s16 com.android.shell\n" + parcel(LINHA) if self.linha_no_servico else "")
            )
        if comando.startswith("cmd phone get-imei"):
            return ""
        if comando.startswith("am start") or comando.startswith("input keyevent"):
            return ""
        if comando.startswith("uiautomator dump"):
            return self.tela
        if "--where" in comando:
            return "No result found.\n"
        if "telephony/siminfo" in comando:
            return "Row: 0 number=\n"
        if "contacts/profile" in comando:
            return f"Row: 0 display_name={self.perfil or 'NULL'}\n"
        if "content://sms" in comando:
            return SMS
        if "contacts" in comando:
            return "Row: 0 data1=+5511999990001, display_name=Silva, João\n"
        if "call_log" in comando:
            return "Row: 0 number=11999990001, date=1758000000000, duration=65, type=3, name=NULL\n"
        if comando.startswith("stat -c"):
            return f"{int(time.time())} /sdcard/Android/media/com.whatsapp/WhatsApp/Databases/msgstore.db.crypt14\n"
        if comando.startswith("[ -d"):
            return "sim\n" if "Android/media/com.whatsapp/WhatsApp" in comando else ""
        if comando.startswith("[ -e"):
            return "sim\n"
        if comando.startswith("ls -1A"):
            return "DCIM\nDownload\nAndroid\n"
        if comando.startswith("du -sk"):
            return "".join(f"100\t{parte}\n" for parte in comando.split() if parte.startswith("/sdcard"))
        if comando.startswith("find"):
            return f"{sum(1 for n in ARQUIVOS if n.startswith(self._prefixo(comando)))}\n"
        if comando == "command -v tar":
            return "/system/bin/tar\n"
        raise AssertionError(f"comando inesperado: {comando}")

    @staticmethod
    def _prefixo(comando):
        for pasta in sorted(PASTAS + ("Android/media/com.whatsapp/WhatsApp",), key=len, reverse=True):
            if f"/sdcard/{pasta}" in comando or f"./{pasta}" in comando:
                return f"./{pasta}/"
        raise AssertionError(comando)
