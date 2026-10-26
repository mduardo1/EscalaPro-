# EscalaPro — execução, deploy e recuperação

## Estado desta entrega

Código preparado e testado em ambientes isolados. **Nenhum deploy, contratação, envio real ou migração do banco principal foi executado.** A liberação depende de homologação no Render, configuração dos proxies reais, validação autorizada do provedor de e-mail, orçamento e aprovação da transferência dos dados.

O backend mantém SQLite local. PostgreSQL usa SQLAlchemy Core com comandos nomeados, psycopg e pool limitado. Os contratos dos modelos e os horários civis em ISO foram preservados; não foi introduzido ORM nem conversão automática para UTC. O adaptador PostgreSQL preserva o acesso por nome/posição dos resultados usados pelos serviços. As revisões Alembic são específicas por dialeto quando necessário.

## Executar localmente com o ambiente existente

Na raiz do projeto:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

O `.env` existente não foi alterado. Sem `DATABASE_URL`, o banco SQLite continua sendo utilizado; sem novas opções de e-mail, o SMTP local mantém o comportamento anterior. O modo em memória é exclusivo de desenvolvimento. A nova prontidão pode retornar 503 para um banco antigo até aplicar as revisões **depois de autorizar a migração**.

Para executar testes e ferramentas de manutenção:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -v -W error
```

Sem `TEST_DATABASE_URL`, os testes PostgreSQL são explicitamente ignorados. A suíte completa reproduzível, incluindo PostgreSQL, pg_dump/pg_restore e Gunicorn no Linux, está em `compose.test.yml`:

```powershell
docker compose -f compose.test.yml -p escalapro-tests up --build --abort-on-container-exit --exit-code-from tests
docker compose -f compose.test.yml -p escalapro-tests down
```

O compose é somente de testes: credenciais fictícias, nenhum volume persistente ou `.env` real, nenhum serviço externo. Não utilizar seus valores em produção. Um container novo pode criar outro conjunto descartável de dados; nunca apontar testes ao banco principal. A fixture PostgreSQL aceita apenas banco terminado em `_test`, em hosts locais/CI, e cria schemas aleatórios próprios.

O runtime de produção e CI foi fixado em **Python 3.14.8**; o ambiente Windows existente em 3.14.3 foi mantido. A versão 3.14.8 inclui correções de segurança. [Release oficial](https://www.python.org/downloads/release/python-3148/).

## Variáveis de produção

Configure no ambiente da hospedagem; não copie segredos para arquivos versionados. `.env.example` documenta valores locais e nomes, sem credenciais.

| Variável | Configuração |
|---|---|
| `APP_ENV` | `production`; valores desconhecidos são recusados |
| `FLASK_DEBUG` | `0`; debugger/reloader recusados |
| `SECRET_KEY` | Segredo aleatório estável, com ao menos 32 caracteres; exclusivo do ambiente |
| `DATABASE_URL` | PostgreSQL, com `sslmode=require`, `verify-ca` ou `verify-full`, conforme o destino. Não há fallback SQLite em produção |
| `DB_POOL_SIZE` | Padrão 3 conexões por processo, sem overflow; ajustar com base na capacidade total web + workers |
| `DB_TIMEOUT` | Padrão 3 segundos para conexão/espera no pool; consultas e locks também têm limites |
| `TRUSTED_HOSTS` | Hosts reais separados por vírgula, sem esquema. Obrigatório em produção; considerar o host usado no health check |
| `TRUSTED_PROXY_NETWORKS` | Redes/IPs dos peers de proxy efetivamente confiáveis, em CIDR; não preencher com uma rede inventada ou indiscriminada |
| `PROXY_HOPS` | Compatibilidade para o mesmo número de saltos por cabeçalho; padrão 0 |
| `PROXY_FOR_HOPS`, `PROXY_PROTO_HOPS` | Quantidades específicas para IP e esquema, quando diferentes. Configurar somente após verificar a topologia real |
| `APP_TIMEZONE` | `America/Sao_Paulo`, preservando horários civis atuais |
| `MAIL_TRANSPORT` | `resend` para API HTTPS; `smtp` para transporte existente; `disabled` somente para manutenção/testes sem envio |
| `MAIL_FROM` | Remetente autorizado/verificado no provedor HTTPS |
| `RESEND_API_KEY` | Credencial de envio do provedor; a validação atual requer configuração em web e worker, sem exposição ao frontend |
| `EMAIL_DELIVERY_MODE` | `outbox` obrigatório em produção |
| `EMAIL_OUTBOX_KEY` | Chave Fernet distinta de `SECRET_KEY`, estável e compartilhada entre web e worker |
| `PORT` | Fornecido pelo Render e consumido por `gunicorn.conf.py` |
| `SMTP_*` | Mantidos para instalações que utilizem SMTP; TLS obrigatório em produção |
| `RESTORE_DATABASE_URL` | Somente durante restauração explícita em banco novo e diferente; não é o destino normal da aplicação |

Para gerar a chave da outbox, sem salvá-la automaticamente:

```powershell
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Não rotacione a chave enquanto houver tarefas pendentes sem planejar sua recuperação: tarefas indecifráveis falham de forma segura. A biblioteca Fernet autentica o payload; destinatário e código não ficam em texto puro na fila. [Documentação Fernet](https://cryptography.io/en/latest/fernet/).

Credenciais de bootstrap `ADMIN_*` continuam opcionais e restritas ao comando local confiável. Não recriar os administradores importados nem substituir suas senhas.

## Preparação no Render — depende de autorização futura

Proposta: web service Docker, PostgreSQL gerenciado e um background worker da outbox, na mesma região. Não foi criado `render.yaml` provisionando planos pagos, conta externa ou serviço. A imagem executa como usuário sem privilégios; `.dockerignore` exclui `.env`, bancos, backups, chaves, ambiente virtual e artefatos locais.

- **Web:** `Dockerfile`, target final `production`, comando padrão `gunicorn --config gunicorn.conf.py 'app:create_app()'`.
- **Worker:** mesma imagem, comando `python -m flask --app app:create_app mail-worker`.
- **Prontidão:** `/health/ready`, consulta revisão e tabelas necessárias; falha retorna somente `{"status":"unavailable"}` com 503.
- **Vivacidade:** `/health/live`, sem consulta ao banco. Ambos ignoram sessão/cookies do solicitante.
- **Build:** instala requisitos; não migra nem importa dados.
- **Banco novo:** inicializar uma única vez por comando autorizado, antes de disponibilizar o serviço.
- **Banco existente:** `migrate-db --backup ...`, após autorizar e validar o backup. Não migrar em cada worker.
- **Auto-deploy:** inicialmente desativado. Não colocar migrações destrutivas em hooks automáticos.

O Dockerfile inclui clientes PostgreSQL 18 para backup/restauração. O cliente precisa ter versão compatível com o servidor; caso escolha outra major, ajustar e ensaiar novamente. A instalação nativa Windows precisa desses clientes no PATH para os comandos PostgreSQL de backup, mas não para o acesso normal via psycopg.

O Render termina TLS e encaminha tráfego ao processo. A aplicação só aceita cabeçalhos encaminhados de peers configurados e não aceita `X-Forwarded-Host`. Gunicorn não faz uma segunda interpretação desses cabeçalhos. **Os CIDRs e saltos do Render não foram medidos nesta etapa**; manter a liberação bloqueada até validar IP, esquema, CSRF, `Referer`, cookies e hosts no domínio HTTPS real. [Proxy Flask](https://flask.palletsprojects.com/en/stable/deploying/proxy_fix/) e [rede Render](https://render.com/docs/web-services).

## Migrações e transferência SQLite → PostgreSQL

Nenhum comando desta seção foi executado no banco principal. Pare as instâncias antigas e abra uma janela de manutenção somente depois de autorizar a operação real.

### SQLite local

Em instalação nova descartável, `init-db` inicializa a base legada e aplica as revisões Alembic. Para uma instalação existente autorizada:

```powershell
.\.venv\Scripts\python.exe -m flask --app app:create_app migrate-db
```

O comando cria um backup consistente ao lado do banco, verifica sua integridade e suas chaves estrangeiras antes de fazer a adoção versionada. Uma cópia inválida cancela a migração. `0001_baseline` não recria as tabelas SQLite existentes; `0002_outbox` acrescenta a fila. A migração de empresas anterior permanece em `app/migrations.py` e continua preservando IDs, hashes e histórico.

### PostgreSQL novo

Defina `DATABASE_URL` **apenas para o destino novo** no ambiente do comando. A aplicação não migra ao iniciar.

```sh
python -m flask --app app:create_app init-db
python -m flask --app app:create_app import-sqlite --source backups/snapshot.sqlite3
```

O importador aceita somente snapshot dentro do projeto, aberto em modo somente leitura, com integridade e FKs válidas. O destino deve ser PostgreSQL inicializado e sem registros de usuários, equipe, escalas ou autenticação; seeds modificados também são recusados. Não passa por cima de uma empresa existente.

Empresas, configurações, usuários, funcionários, turnos, escalas, indisponibilidades e preferências legadas são copiados e comparados campo a campo, em uma transação. IDs, `company_id`, hashes e snapshots são mantidos; sequências são ajustadas. Falhas revertem os dados importados; sequências PostgreSQL podem deixar lacunas, sem reutilizar IDs. O snapshot original permanece intacto.

Sessões, limites transitórios, desafios e tarefas pendentes não são importados. As contas existentes permanecem verificadas como na origem; o domínio de produção exige novo login e os fluxos pendentes precisam ser reiniciados. Esses registros continuam preservados no snapshot original. Não há e-mails ou notificações disparados pela importação.

Antes da transferência real: fazer um ensaio em destino separado, comparar contagens por empresa, autenticar contas autorizadas e conferir PDFs. Suspender todas as escritas de origem durante o snapshot/cutover. Após novas escritas no destino, não voltar ao SQLite antigo sem reconciliar as alterações.

### Evolução e reversão

```sh
python -m flask --app app:create_app migrate-db --backup backups/pre-release.dump
```

PostgreSQL com schema existente exige `--backup`; `init-db` recusa reaproveitar schema existente. O upgrade é serializado por lock de migração. A baseline PostgreSQL usa FKs compostas para impedir vínculos entre empresas e gatilhos contra mudança de pertencimento. Escalas e indisponibilidades bloqueiam a mesma linha do funcionário; confirmações usam lock por identidade e transações. Filtros por empresa permanecem obrigatórios; RLS não foi acrescentado.

Reversões Alembic devem ser ensaiadas **em cópia**, com backup prévio, por exemplo `python -m alembic downgrade 0001_baseline`. A outbox não pode ser removida se contiver tarefas, inclusive histórico; não apagar registros para contornar essa proteção. A baseline PostgreSQL só pode voltar a `base` quando não há dados além dos seeds originais. No SQLite, a reversão da adoção preserva o schema legado. Para dados existentes, recuperar em destino separado é a alternativa segura; nunca executar downgrade destrutivo no banco principal.

## Backup e restauração

### SQLite

```powershell
.\.venv\Scripts\python.exe -m flask --app app:create_app backup-db --output backups/snapshot.sqlite3
.\.venv\Scripts\python.exe -m flask --app app:create_app restore-sqlite --source backups/snapshot.sqlite3 --output tmp/recovered.sqlite3
```

A cópia usa a API de backup SQLite, verifica integridade e FKs e nunca substitui arquivo existente. A restauração recusa o caminho do banco configurado da aplicação. Validar o arquivo recuperado antes de qualquer troca autorizada.

### PostgreSQL

```sh
python -m flask --app app:create_app backup-db --output backups/snapshot.dump
# RESTORE_DATABASE_URL deve apontar a outro banco vazio, nunca ao atual.
python -m flask --app app:create_app restore-postgres --source backups/snapshot.dump
```

São utilizados `pg_dump` custom e `pg_restore --single-transaction --exit-on-error`, sem comandos de limpeza/drop. A senha é passada no ambiente do subprocesso e não na linha de comando; saídas privadas das ferramentas não são registradas. Restauração no mesmo banco ou em destino com tabelas é recusada. O ensaio automatizado cria e remove somente databases fictícios de testes.

Arquivos locais não são backup externo. Ainda é necessário aprovar armazenamento externo protegido, retenção, agendamento, acesso restrito e ensaio regular de restauração. Ativar recuperação gerenciada do plano escolhido e monitorar falhas. RPO/RTO de produção não foram medidos. Não guardar dumps no GitHub nem dentro de uma imagem Docker. [Recuperação no Render](https://render.com/docs/postgresql-backups).

## Outbox e API de e-mail

O adaptador Resend usa `https://api.resend.com/emails`, certificado validado, timeout, texto/HTML e chave de idempotência por tarefa. Não segue redirects com a credencial. O modo SMTP continua disponível. Não houve chamada ao provedor real; todos os testes de transporte são mocks. [API Resend](https://resend.com/docs/api-reference/emails/send-email).

Desafio e tarefa são gravados na mesma transação. O worker usa lease e token de posse, até cinco tentativas, atraso progressivo com jitter e expiração. Ele rejeita tarefas de códigos usados, substituídos ou expirados e limpa o payload após conclusão. Reinícios não apagam tarefas; ACK de worker antigo não sobrescreve uma nova posse. Se o transporte estiver desativado, o worker recusa iniciar sem consumir a fila.

```sh
python -m flask --app app:create_app mail-worker
# Operação pontual de teste:
python -m flask --app app:create_app mail-worker --once
python -m flask --app app:create_app cleanup-auth
```

O último comando limpa estados de autenticação expirados e desafios com mais de 24 horas; não remove usuários ou histórico de escalas. O agendamento não foi criado. Transporte em memória permanece somente para desenvolvimento.

Entrega é ao menos uma vez: falhas após aceitação SMTP podem duplicar a mensagem. Idempotência HTTPS reduz esse risco, mas não garante chegada à caixa de entrada. Uma mensagem já em trânsito não pode ser recolhida; códigos anteriores continuam inválidos após reenvio. Não alterar o prazo de dez minutos para compensar atrasos de entrega. A chave de idempotência do Resend tem janela própria; as tarefas daqui expiram antes dela. [Idempotência do provedor](https://resend.com/docs/dashboard/emails/idempotency-keys).

## Custos estimados — sem contratação

Referência consultada em 17/10/2026, valores em USD/mês; confirmar no painel antes de aprovar. O mínimo ilustrativo é **US$20/mês**: web US$7 + worker US$7 + PostgreSQL US$6. O projeto não exige Redis. Essa configuração pequena precisa de teste de memória/carga; aumentar recursos aumenta o custo. Armazenamento adicional, tráfego, build, backups externos, workspace, impostos e domínio podem acrescentar valores. [Tabela oficial Render](https://render.com/pricing).

Resend oferece plano gratuito de 3.000 e-mails/mês, com limite diário de 100 na consulta atual; depende de conta e remetente/domínio autorizado. Domínio próprio e armazenamento externo de backups têm custo variável. Nenhuma conta ou cobrança foi ativada. [Preços Resend](https://resend.com/pricing).

Render Free pode servir a uma demonstração descartável com API HTTPS, mas não substitui a topologia durável: há suspensão, restrição SMTP e prazo de expiração do Postgres gratuito; worker separado também precisa de solução operacional aprovada. Não apresentar uma demonstração gratuita como produção permanente. [Limites Free](https://render.com/docs/free).

## Pendências de liberação

Validação final: **208 testes aprovados no Linux/Python 3.14.8**, sem avisos ou testes ignorados; **206 aprovados e 2 ignorados no Windows/Python 3.14.3**, com os testes específicos executados no Linux. Cobertura Linux de `app/` e `migrations/`: **93,81% das linhas**, **85,91% das ramificações**, **92,19% combinada**. Evidências em `tmp/phase2-linux-*` e `tmp/phase2-windows-*`, ignoradas pelo Git. Esses testes não equivalem à homologação do Render ou ao recebimento de e-mails reais.

- Autorização e ensaio da transferência real; nenhum banco principal foi migrado.
- Homologação Render: proxy, HTTPS/CSRF, hosts, recursos, persistência após redeploy e reinício coordenado web/worker.
- Conta/remetente e teste real de e-mail autorizados; aprovação de qualquer custo.
- Agendamento/cópia externa de backups, métricas/alertas e restauração periódica.
- Carga/paginação, RLS se desejado, revisão de dependências/segredos e fixação de imagens/actions por digest/SHA antes de uma cadeia de publicação mais restrita.
- Escolha de licença pelo proprietário e revisão dos arquivos a publicar. Nenhum push ou deploy foi realizado.

## Arquivos e dependências da Fase 2

- Novos: `app/persistence.py`, `app/proxy.py`, `app/routes/health.py`, `app/services/{outbox_service,backup_service,data_transfer}.py`.
- Novos: `alembic.ini`, `migrations/env.py`, revisões `0001_baseline.py` e `0002_outbox.py`.
- Novos: `Dockerfile`, `.dockerignore`, `.python-version`, `gunicorn.conf.py`, `compose.test.yml`, `.github/workflows/tests.yml` e este guia.
- Novos testes: `tests/test_postgres.py`, `tests/test_outbox.py`, `tests/test_phase2_operations.py`.
- Atualizados: factory, configuração, banco/CLI, segurança, modelos, rotas/serviços de autenticação, envio e escalas, `run.py`; fixtures e testes de configuração, entrada e expiração; ignore, exemplo de ambiente, requisitos, README, ACCOUNT_SETUP e PRODUCTION_READINESS.
- Templates, CSS, JavaScript, fontes e o banco SQLite principal foram preservados nesta fase.

Instalados no `.venv` existente: SQLAlchemy **2.0.55**, psycopg/psycopg-binary **3.3.6**, Alembic **1.20.0** e cryptography **50.0.2**, com suas dependências. Gunicorn **26.2.0** é instalado somente no Linux; o requisito possui marcador de plataforma. `pytest` e `pypdf` foram separados no arquivo de desenvolvimento. `pip check`, compilação e Black passaram; uma auditoria completa de CVEs continua pendente.
