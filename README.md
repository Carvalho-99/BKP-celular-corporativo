# Backup de celular corporativo

Programa do TI para copiar os dados de um celular Android da empresa quando o
funcionário é desligado. O celular fica no cabo USB e o computador comanda a cópia.

## Como usar

1. No celular, ative a depuração USB:
   - Configurações > Sobre o telefone > toque 7 vezes em **Número da versão**
     (na Samsung: Sobre o telefone > Informações do software)
   - Configurações > Opções do desenvolvedor > ligue **Depuração USB**
2. Ligue o celular no computador pelo cabo e aceite **Permitir depuração USB** na tela dele.
3. Abra o `iniciar.bat`.
4. Preencha os dados, escolha a pasta de destino e clique em **Iniciar backup**.
5. Quando o programa pedir, faça o backup dentro do WhatsApp no celular.

Deixe a tela do celular desbloqueada e não mexa no cabo durante a cópia.

## O que é copiado

| Item | Onde fica no backup |
|---|---|
| Arquivos, fotos, vídeos, downloads | `arquivos\` |
| Arquivos externos dos apps (documentos escaneados, downloads de apps) | `arquivos\Android\data\` |
| Pasta do WhatsApp / WhatsApp Business (mídias e banco) | `arquivos\Android\media\` |
| Conversas de SMS com pessoas (operadora e serviços são ignorados) | `dados\sms.txt` e `dados\sms.csv` |
| Contatos | `dados\contatos.csv` |
| Histórico de chamadas | `dados\chamadas.csv` |
| Apps com nome, data de instalação, último uso e tempo de uso | `dados\apps.csv` |
| Contas logadas | `dados\contas.csv` |
| Resumo do backup e identificação do usuário | `relatorio.pdf` |
| Apps, conversas de SMS, chamadas e contatos por extenso | `detalhes.pdf` |
| SHA-256 de cada arquivo copiado | `manifesto.csv` |
| Registro do que o programa fez | `log.txt` |

## Plataformas

| Recurso | Android | iPhone |
|---|---|---|
| Detectar o aparelho no cabo | Sim | Sim |
| Identificar aparelho, chips e contas | Sim | Não implementado |
| Arquivos, fotos e vídeos | Sim | Não implementado |
| Contatos, SMS e chamadas | Sim | Não implementado |
| Apps e histórico de uso | Sim | Não implementado |
| WhatsApp (mídias e banco criptografado) | Sim | Não implementado |
| Conversas do WhatsApp em texto | Não | Não implementado |

O iPhone aparece na tela como "detectado", com o backup bloqueado e o motivo escrito.
Para implementar o backup de iPhone falta: instalar o suporte da Apple no Windows
(aplicativo Dispositivos Apple ou iTunes) e uma biblioteca de comunicação
(pymobiledevice3, que no Python 3.14 não instala completa por falta de duas dependências
compiladas).

## Identificação automática

Ao conectar (ou pelo botão **Identificar**) o programa lê o aparelho, os chips e as contas.
Cada informação fica registrada com a situação, a fonte e, quando não deu certo, o motivo:

| Situação | Significado |
|---|---|
| Coletado | Lido do aparelho |
| Não encontrado | A consulta funcionou, mas o aparelho não tem o dado |
| Acesso negado | O sistema recusou a consulta |
| Não suportado | O aparelho ou a versão não tem o recurso |
| Falha | Erro de comunicação ou de leitura |
| Não implementado | O programa ainda não sabe coletar |

A trilha aparece em **Detalhes da execução**, vai para o `relatorio.pdf` e fica gravada
em `registros\identificacao-AAAA-MM-DD.log`. Senhas e tokens não são lidos.

Três coisas ficam separadas: o que foi **lido** do aparelho, o nome **sugerido** a partir
disso, e o funcionário **confirmado** pelo técnico. Nome de aparelho e e-mail ajudam a
sugerir, mas não comprovam quem usava o celular. Se houver mais de um nome possível, o
programa mostra as opções com a fonte e não escolhe sozinho. O que você digitar nunca é
substituído.

Para o número da linha são quatro fontes, nesta ordem: tabela de chips, serviço de
assinaturas, serviço de telefonia e, por último, a tela **Sobre o telefone**, que só é
aberta com o celular desbloqueado e só vale se o número estiver no campo "Número de telefone".

Com mais de um aparelho no cabo, a tela pede a escolha. Se outro aparelho for conectado
com dados do anterior no formulário, nada é reaproveitado sem a sua decisão: você escolhe
entre começar uma sessão nova ou manter o que digitou.

## Cobertura de cada categoria

Antes do backup, cada cartão de "O que copiar" mostra o que o aparelho conectado permite.
Categoria que o Android recusa fica desmarcada e travada, com o motivo. Depois do backup,
o cartão mostra o resultado real, e o relatório traz três colunas por etapa:

| Coluna | Significado |
|---|---|
| Preservado | O que ficou guardado no backup |
| Legível | O que dá para abrir e ler |
| Não acessível | O que não foi possível obter |

Filtro de SMS: ficam de fora as mensagens cujo remetente tem letras (como VIVO ou TIM) ou
tem menos de 8 dígitos. A quantidade e os remetentes excluídos ficam em
`dados\sms_filtro.csv`; o texto dessas mensagens não é copiado. MMS e mensagens de chat
(RCS) não são lidas.

O `manifesto.csv` permite verificar se um arquivo foi alterado depois do backup. Sozinho,
ele não comprova que todos os dados do celular foram coletados.

O nome comercial dos apps vem da página pública da Play Store (só o nome do pacote é
enviado) e fica guardado em `nomes_apps.json`. Sem internet, o relatório mostra um nome
provável. Para desligar a consulta, mude `CONSULTAR_PLAY_STORE` em `backup\nomes_apps.py`.

## O que não dá para copiar

- Dados internos de outros aplicativos: o Android bloqueia sem root.
- Senhas: não são acessíveis. Redefina pelo painel de administração da conta.
- Conversas do WhatsApp em texto: o banco é criptografado. Para ler, restaure o
  backup em outro aparelho com o chip da linha (passo a passo no relatório).

## Instalar em outro computador

Precisa de Python 3.11 ou mais novo.

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

Baixe o [platform-tools do Android](https://developer.android.com/tools/releases/platform-tools)
e extraia em `tools\`, de modo que exista `tools\platform-tools\adb.exe`.

## Organização do código

| Pasta | O que tem |
|---|---|
| `backup\` | Identificação do aparelho, coleta, cópia dos arquivos e relatórios. Não conhece a tela. |
| `backup\conectores.py` | Lista os aparelhos de todas as plataformas e encaminha para o conector certo. |
| `backup\captura.py` | Identificação do Android, com a fonte de cada leitura. |
| `backup\cobertura.py` | O que cada categoria entrega no aparelho conectado. |
| `backup\executar.py` | Sequência do backup do Android e resultado de cada etapa. |
| `interface\tema.py` | Cores, fontes e medidas, em um lugar só. |
| `interface\icones.py` | Ícones desenhados pelo próprio programa (sem arquivos nem internet). |
| `interface\componentes.py` | Botão, campo, cartão, opção selecionável, selo e painel de log. |
| `interface\estado.py` | Regras da tela: situação do aparelho, validação, textos de resultado. |
| `interface\janela.py` | Monta a tela e liga os componentes às rotinas de `backup\`. |

A interface usa [customtkinter](https://customtkinter.tomschimansky.com/), uma camada sobre
o Tkinter que desenha cantos arredondados e respeita a escala do Windows.

## Testes

```
.venv\Scripts\python -m unittest discover -s tests
```

Os testes usam um celular simulado, não precisam de aparelho no cabo. Os de
`test_interface.py` abrem a janela de verdade, fora da área visível da tela.

Para conferir o visual, `tests\captura_de_tela.py saida.png` abre a janela com dados
fictícios e salva uma imagem dela (opções como `--conflito`, `--troca` e `--iphone`).

Para validar um modelo novo de celular sem fazer backup, conecte o aparelho e rode
`.venv\Scripts\python diagnostico.py`. Ele mostra, com os valores mascarados, o que foi
lido, o que não foi e por quê. Os testes simulados não substituem um backup completo
pela janela com aparelho real.
