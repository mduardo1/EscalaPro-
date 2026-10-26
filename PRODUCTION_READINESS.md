# EscalaPro — auditoria de prontidão para produção

**Auditoria original:** 17/10/2026 · **Atualização:** Fase 2 implementada em ambiente isolado.

## Fase 2 — estado atual dos achados

**A liberação para produção continua bloqueada até a homologação externa e a autorização da transferência real.** Foram implementados PostgreSQL com SQLAlchemy Core/psycopg, Alembic, outbox criptografada, API HTTPS, WSGI, configuração estrita, health checks e ferramentas de backup/recuperação. A aplicação continua compatível com SQLite local. O `.env` e os dados principais não foram alterados; nenhuma migração principal, contratação, mensagem real, publicação ou deploy foi executado.

O guia operacional atual está em [DEPLOYMENT.md](DEPLOYMENT.md). As seções numeradas abaixo preservam o diagnóstico original como histórico; esta tabela prevalece para o estado da implementação.

| Achado | Estado após a Fase 2 | Validação e pendência restante |
|---|---|---|
| PR-01 | Proteção implementada | Produção recusa SQLite e fallback silencioso; PostgreSQL validado com dados fictícios. Persistência no Render e transferência real ainda não executadas. |
| PR-02 | Implementado e testado em Linux | Gunicorn fixado, bind por `PORT`, processo HTTP real testado; servidor de desenvolvimento recusa produção. Configuração de domínio/TLS no Render permanece pendente. |
| PR-03 | Implementado e validado em PostgreSQL 18 | Consultas nomeadas, pool limitado, FKs compostas, imutabilidade de empresa, locks de concorrência, importação verificada e revisões reversíveis com proteção de dados. Banco principal preservado; cutover real não autorizado. |
| PR-04 | Adaptador preparado; integração externa pendente | Resend por HTTPS com TLS, HTML/texto, timeout, redirecionamentos recusados e idempotência. Testes usam mocks; conta, domínio/remetente e envio real dependem de autorização. SMTP local mantido. |
| PR-05 | Implementado e testado | Outbox e desafio na mesma transação, payload Fernet, lease/token, limite de tentativas, expiração e recuperação entre instâncias. Worker separado fornecido; orquestração/monitoramento na hospedagem não configurados. |
| PR-06 | Implementado; topologia Render pendente | Middleware confia somente em peers/CIDRs explícitos, com saltos por cabeçalho; testes rejeitam spoofing de peer e host. Confirmar redes, saltos, esquema e CSRF no ambiente real antes de liberar. |
| PR-07 | Ferramentas implementadas e ensaiadas | Backup SQLite e pg_dump/pg_restore; restauração somente em destino novo, preservação de hashes e integridade verificadas. Cópia externa, agendamento, retenção e RPO/RTO operacionais ainda precisam de aprovação/ensaio. |
| PR-08 | Corrigido em código e testes | Ambiente validado/normalizado, flags estritas, TLS PostgreSQL obrigatório em produção, `TRUSTED_HOSTS`, chave de outbox separada e configurações faltantes recusadas. |
| PR-09 | Prontidão implementada; monitoramento parcial | `/health/live` e `/health/ready` não expõem sessão ou conexão; revisão/tabelas e timeouts verificados. Alertas e métricas operacionais da fila/capacidade ainda não foram implantados. |
| PR-10 | Proteções de arquivos reforçadas | `.gitignore` e `.dockerignore` excluem ambientes, bancos auxiliares, backups e chaves. Sem repositório local não foi possível auditar histórico/índice; revisão final de segredos antes da publicação permanece necessária. |
| PR-11 | Preparação implementada; cadeia de publicação parcial | Runtime de produção fixado em Python 3.14.8, dependências de testes separadas, Gunicorn fixado e workflow SQLite/PostgreSQL criado. CI GitHub não foi acionada; auditoria de CVEs e pinagem de imagens/actions por digest/SHA ainda pendentes. |
| PR-12 | Parcial | Limpeza explícita de estados expirados e limites de pool/consultas/retentativas acrescentados. Paginação, carga e agendamento de limpeza continuam pendentes. |
| PR-13 | Documentação atualizada; melhorias opcionais pendentes | Guia de deploy/recuperação e CI adicionados. Nenhuma licença foi escolhida em nome do proprietário; CDN/SRI e revisão da cadeia permanecem para etapa própria. |

### Evidências da implementação

| Ambiente final | Testes | Linhas | Ramificações | Combinada |
|---|---|---|---|---|
| Windows, Python 3.14.3, PostgreSQL 18.3 local | **206 aprovados, 2 ignorados**, 87,35 s | **92,99%** | **85,00%** | **91,36%** |
| Linux Docker, Python 3.14.8, PostgreSQL 18.3 | **208 aprovados, nenhum ignorado**, 86,02 s | **93,81%** | **85,91%** | **92,19%** |

Ambas as execuções usaram `-W error`, sem avisos. Os dois testes ignorados no Windows são pg_dump/pg_restore e processo Gunicorn; foram executados no Linux. Cobertura de `app/` e `migrations/`, com 1.712 linhas executáveis e 440 ramificações. O denominador aumentou em relação à auditoria inicial; não comparar percentuais como se o escopo fosse idêntico. A imagem de produção também foi construída localmente e conferida sem `.env`, banco principal ou pytest.

- Regressões anteriores preservadas; teste de expiração ajustado para relógio determinístico, sem relaxar a rejeição de código expirado.
- Bases SQLite temporárias e PostgreSQL 18.3 local descartável; fixtures restringem nomes/hosts e isolam schemas. Nenhum banco principal foi consultado ou migrado.
- Importação ensaiada com duas empresas, IDs, hashes, histórico noturno, validação de referências e sequências; origem permanece intacta. Sessões e desafios transitórios não são transferidos, conforme a estratégia documentada.
- Migrações ensaiadas de ida/volta; reversão destrutiva de baseline com dados é recusada. A remoção de outbox com tarefas é recusada. Adoção SQLite não recria suas tabelas legadas.
- O backup automático anterior à migração SQLite passa por verificações de integridade e chaves estrangeiras. Uma origem inválida cancela a migração, preservando sua revisão e seus registros; regressão coberta pela suíte final.
- Relatórios finais: `tmp/phase2-windows-tests.xml`, `tmp/phase2-windows-coverage.json`, `tmp/phase2-linux-tests.xml` e `tmp/phase2-linux-coverage.json`. A cobertura inclui `app/` e `migrations/`; arquivos de configuração/entrypoint também possuem verificações específicas.
- Python/venv Windows existente preservado. A imagem Linux e `.python-version` usam 3.14.8, release de segurança da série 3.14; nenhuma instalação Python global foi alterada. [Release Python](https://www.python.org/downloads/release/python-3148/).

### Decisões e limites de operação

O uso de comandos SQL nomeados através do SQLAlchemy Core preserva os contratos dos modelos; SQLite continua nativo para não reescrever migrações/backup legados nem mudar seus resultados. Diferenças de transação e identidade são tratadas explicitamente. Datas permanecem ISO civis, evitando uma conversão implícita para UTC durante a portabilidade. Não foi introduzido ORM nem RLS.

O worker usa processamento ao menos uma vez. Mensagens já aceitas pela rede não podem ser recolhidas; a validade do código continua sendo conferida no servidor. A idempotência HTTPS reduz duplicidade, sem promessa de chegada à caixa de entrada. Os testes externos foram simulados para respeitar a proibição de envio real.

Estimativa ilustrativa de infraestrutura persistente: web US$7 + worker US$7 + PostgreSQL US$6, **US$20/mês antes de adicionais**, sem Redis. Recursos, tráfego, backups externos, domínio e impostos podem elevar o total; nenhuma contratação foi realizada. O guia contém fontes, limites gratuitos e variáveis necessárias. [Preços oficiais Render](https://render.com/pricing).

**Próxima autorização necessária:** homologação no Render e teste de entrega real, depois revisão do ensaio de transferência antes de tocar os dados principais. Não executar comandos de migração ou restauração no banco real apenas para reproduzir os testes.

---

## Registro histórico da auditoria inicial

## 1. Parecer

O MVP tem uma base funcional e modular, com proteções de autenticação e isolamento cobertas por testes. **A configuração atual ainda não deve ser publicada como serviço de produção no Render.** Os principais impedimentos são persistência do SQLite, ausência de servidor WSGI nas dependências, incompatibilidade atual com PostgreSQL e envio de e-mail dependente de uma fila em memória e de portas indisponíveis no plano Free.

Publicar o código no GitHub e colocar dados de usuários online são decisões distintas. O código pode ser preparado para revisão pública depois de conferir o conjunto de arquivos, segredos, licença e documentação. Isso não elimina os bloqueios de hospedagem descritos abaixo.

O usuário informou que validou manualmente cadastro, Gmail, confirmação, recuperação, login/logout, módulos administrativos e isolamento. Essa validação local foi considerada como evidência fornecida pelo usuário; **não equivale a um teste da rede, do proxy, do banco ou dos reinícios do Render**.

Nesta etapa:

- Não foram alterados módulos da aplicação, dependências, `.env.example`, README ou configurações existentes.
- O `.env` real não foi aberto ou alterado; o banco principal não foi consultado ou migrado.
- Não foram alterados administradores, senhas ou registros reais.
- Não houve envio de e-mail real, instalação de pacotes, publicação, push ou deploy.
- Foram executados os testes existentes e sondagens com configuração fictícia. Artefatos ficam em `tmp/`, além deste relatório. A execução de cobertura também atualiza `.coverage`, ignorado pelo Git.
- A avaliação de padrões Git utilizou uma cópia do `.gitignore` em um repositório temporário descartável dentro de `tmp/`; não foi inicializado um repositório na raiz do projeto.

## 2. Evidências e verificações executadas

Ambiente: Windows, Python **3.14.3**, ambiente virtual existente `.venv`.

| Verificação | Resultado |
|---|---|
| Suíte existente, com `-W error` | **147 aprovados**, sem falhas ou avisos, em **57,20 s** |
| Cobertura Python de linhas | **96,23%** — 1.073 de 1.115 linhas executáveis |
| Cobertura de ramificações | **90,23%** — 231 de 256 |
| Cobertura combinada | **95,11%** |
| `python -m pip check` | Sem incompatibilidades declaradas |
| Cookies em configuração `production` | `Secure=True`, `HttpOnly=True`, `SameSite=Lax`; debug desativado |
| Bloqueio de debug em produção | Coberto pelos testes existentes, incluindo configurações explícitas e variações de `FLASK_DEBUG` |
| Login sem banco inicializado, em configuração isolada | HTTP **200**; o arquivo SQLite continuou inexistente |
| Rota `/health` | **404**; não existe endpoint dedicado de prontidão |
| Cabeçalhos encaminhados, sem middleware, em requisição simulada | `remote_addr` permaneceu o IP do proxy; `is_secure=False` mesmo com `X-Forwarded-Proto: https` |
| `APP_ENV=Production` | Não ativa o modo de produção; comparação atual exige exatamente `production` |
| Banco configurado fora da raiz do projeto | Rejeitado pela factory |
| Sintaxe do serviço SMTP interpretada como Python 3.13 | Incompatível; usa sintaxe introduzida no Python 3.14 |
| Padrões do `.gitignore` | Arquivos locais atuais protegidos; lacunas listadas na seção 5 |
| Busca limitada de segredos em 88 arquivos públicos selecionados | Sem correspondências para cabeçalhos de chave privada, formatos conhecidos de tokens GitHub e IDs de chave AWS; não é uma certificação de ausência de segredos |
| Estado Git local | Não há `.git` nesta cópia; `git rev-parse` não identificou repositório nesta pasta ou nos pais |
| Ferramentas de produção no ambiente atual | Gunicorn, psycopg, SQLAlchemy, Alembic e pip-audit não instalados |

Comando de testes executado, com as saídas de cobertura e JUnit direcionadas para `tmp/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -v -W error --cov=app --cov-branch --cov-report=term-missing --cov-report=json:tmp/production-readiness-coverage.json --junitxml=tmp/production-readiness-tests.xml --tb=short
```

Evidências locais, ignoradas pelo Git:

- `tmp/production-readiness-tests.xml` e `tmp/production-readiness-tests-run.txt`.
- `tmp/production-readiness-coverage.json`.
- `tmp/production-readiness-checks.json` e o script `tmp/production_audit_checks.py`.

Os testes desativam dotenv, configuram bancos temporários e simulam SMTP, conforme [tests/conftest.py](tests/conftest.py). A cobertura não mede HTML/CSS/JavaScript nem comprova funcionamento no Linux, no Render ou no PostgreSQL. Não foi executada uma auditoria de vulnerabilidades das dependências; `pip check` verifica compatibilidade de requisitos, não CVEs.

## 3. Achados por gravidade

**Crítica:** risco direto de perda de dados na hospedagem proposta. **Alta:** bloqueio técnico ou risco relevante à segurança/confiabilidade dos fluxos principais. **Média:** condição a resolver ou validar antes de uma liberação pública sustentada. **Baixa:** melhoria de manutenção e apresentação. As condições de cada achado fazem parte da classificação; não foi comprovada invasão ou exposição de credenciais.

| ID | Gravidade | Evidência e impacto | Correção recomendada / critério de aceite |
|---|---|---|---|
| PR-01 | **Crítica**, se usar disco efêmero | [app/database.py](app/database.py) grava SQLite local; o caminho padrão é `instance/escalapro.sqlite3`. A perda do arquivo elimina contas, escalas, sessões e limites persistidos. | PostgreSQL gerenciado ou disco persistente explicitamente configurado. Dados de teste devem sobreviver a restart e redeploy antes de importar dados reais. |
| PR-02 | **Alta** | Não há Gunicorn em `requirements.txt`. [run.py](run.py) usa o servidor de desenvolvimento em `127.0.0.1:5000`, sem `PORT`. Não há bloqueio específico contra executar esse comando com `APP_ENV=production`. | Servir a factory por Gunicorn no Linux, em `0.0.0.0:$PORT`. Manter `python run.py` restrito ao desenvolvimento; não resolver apenas expondo o servidor Flask. |
| PR-03 | **Alta**, para a estratégia PostgreSQL | Não existe `DATABASE_URL`, driver PostgreSQL ou migração compatível. SQL, exceções e transações dependem de SQLite. | Portar a persistência e as migrações; validar concorrência e isolamento no PostgreSQL real. Trocar somente a URL não funciona. |
| PR-04 | **Alta**, se usar Render Free + SMTP | O envio atual usa SMTP em portas usuais. O plano Free bloqueia saída em `25`, `465` e `587`. | Escolher serviço com saída SMTP compatível ou implementar transporte por API HTTPS. Validar o envio no ambiente escolhido, com autorização. [Bloqueio documentado pelo Render](https://render.com/changelog/free-web-services-will-no-longer-allow-outbound-traffic-to-smtp-ports). |
| PR-05 | **Alta**, confiabilidade | [email_service.py](app/services/email_service.py) usa `ThreadPoolExecutor`, dois trabalhadores e limite de 32 tarefas por processo. Reinícios perdem pendências; fila cheia/falha produz apenas log genérico, sem retentativa persistente. | Outbox transacional persistente e trabalhador separado, com expiração, tentativas limitadas, deduplicação e monitoramento. Testar falhas e reinícios. |
| PR-06 | **Alta**, atrás do proxy | Não há configuração explícita de proxy na aplicação. Limites usam `request.remote_addr`; usuários podem compartilhar o mesmo identificador de rede. Esquema HTTPS depende da combinação proxy/WSGI. | Definir a fronteira de confiança de proxy e validar IP/esquema em homologação, inclusive cabeçalhos falsificados. Não confiar indiscriminadamente em `X-Forwarded-*`. |
| PR-07 | **Alta**, preservação de dados | `migrate-db` gera backup ao lado do SQLite. Não há rotina implementada de cópia externa, retenção e restauração testada. Backup no mesmo disco não resolve perda do disco. | Backup gerenciado e cópia lógica protegida fora do serviço; ensaio documentado de recuperação com objetivos de perda de dados e tempo de recuperação. |
| PR-08 | **Média** | [config.py](app/config.py) usa igualdade exata de `APP_ENV`; erro de caixa/valor desliga proteções de produção. Não há `TRUSTED_HOSTS` configurado. | Validar ambientes por lista permitida e recusar valor inválido; configurar hosts aceitos, TLS e variáveis obrigatórias com falha clara na inicialização. |
| PR-09 | **Média** | Não há health check de banco/schema ou métricas de fila, falhas e saturação. `/login` pode responder 200 sem persistência disponível. | Endpoint de prontidão com consulta barata e revisão de schema, prazo curto e resposta 503 em falha; logs sem dados sensíveis e alertas operacionais. |
| PR-10 | **Média**, antes do GitHub | `.gitignore` protege os caminhos usados, mas não todos os formatos de backup/chave. Não há histórico local para auditar nem CI de segredos. | Reforçar padrões, examinar o conjunto a publicar e o histórico quando existir. Não usar `git add .` sem revisar os arquivos. Não há evidência de vazamento nesta auditoria. |
| PR-11 | **Média** | Runtime Python não está fixado para o Render; `pyproject.toml` só configura ferramentas. Há dependências de teste no arquivo de produção, sem lock completo com hashes ou CI Linux. | Fixar Python 3.14 compatível, testar instalação limpa no Linux, separar testes de runtime e executar análise de dependências. |
| PR-12 | **Média**, capacidade e retenção | Listagens e PDFs carregam coleções completas; a validação de escala consulta todo o histórico do funcionário. Limpeza de registros de autenticação depende de novas operações. | Paginação, consultas por janela e índices guiados por medições; limites de uso/exportação e limpeza periódica com política de retenção. |
| PR-13 | **Baixa** | README prioriza Windows/local; não há licença do projeto, workflow de CI ou manifesto de deploy. Chart.js vem de CDN sem SRI. | Documentar produção e recuperação, escolher licença, adicionar CI e configuração revisável; avaliar hospedar o JS localmente ou usar integridade. A licença DejaVu já está incluída. |

## 4. Arquitetura, segurança e arquivos de configuração

### Base que deve ser preservada

- Factory `create_app`, blueprints, serviços e modelos têm responsabilidades separadas. O backend pode evoluir sem substituir templates ou regras de negócio.
- SQL recebe parâmetros; os nomes de tabela dinâmicos das migrações vêm de uma lista fixa interna. Não foi identificado uso de entrada do navegador como nome de tabela.
- O contexto de empresa vem do usuário autenticado em [app/tenant.py](app/tenant.py); falha sem identidade administrativa. Consultas de funcionários, turnos, escalas e configurações filtram empresa. Dashboard, alertas e PDF usam esses modelos.
- O SQLite atual possui FKs, índices e gatilhos contra mudança de empresa e vínculos cruzados. Testes exercitam leitura, edição, exclusão e referências indevidas entre duas empresas.
- Senhas usam scrypt. Sessões possuem token aleatório com hash no banco, validade e revogação no logout/recuperação. Os códigos usam gerador seguro, HMAC, prazo, limite de tentativas e consumo atômico.
- CSRF global, escape Jinja, validação no servidor, cookies protegidos, cabeçalhos de segurança e respostas neutras de recuperação já existem. Não é necessário reimplementar esses fluxos para fazer deploy.

Essas observações e os testes são evidência positiva, não uma prova de ausência de todas as vulnerabilidades ou de isolamento em um backend ainda não implementado.

### Revisão dos arquivos pedidos

| Arquivo | Avaliação |
|---|---|
| `requirements.txt` | Versões explícitas e `pip check` aprovado. Faltam servidor WSGI e dependências de PostgreSQL. `pytest` e `pypdf` são utilizados nos testes e podem sair do runtime; `reportlab`, `tzdata` e Flask-WTF devem permanecer. Fixações atuais não travam todas as transitivas com hashes. |
| `requirements-dev.txt` | Complementa o arquivo principal e já inclui cobertura e formatação. Futuramente pode receber as dependências de teste hoje no runtime e ferramentas de auditoria. |
| `pyproject.toml` | Coerente como configuração de Black/djlint, incluindo `py314`. Não declara runtime para o Render nem torna este projeto um pacote instalável. Isso não impede `pip install -r requirements.txt`; não há necessidade de empacotar a aplicação só para hospedá-la. |
| `.gitignore` | Boa proteção dos caminhos reais atuais; evidências e lacunas na seção 5. Ignorar um arquivo não remove conteúdo já commitado. |
| `.env.example` | Segredos vazios, sem credenciais reais aparentes. `development` e `DATABASE_PATH` fazem sentido localmente, mas precisam ser distinguidos das futuras variáveis de produção. Não contém ainda `DATABASE_URL`, configuração de proxy/hosts ou outbox. |
| `run.py` | Entrada local adequada e objeto WSGI importável. A checagem da porta 5000 só roda em `main()`. Importar `run:app` não executa `app.run`; também é possível usar diretamente `app:create_app()`. |
| Configuração Flask | Produção suporta cookies Secure e HSTS e recusa debug. Falta validação estrita do nome do ambiente, configuração do proxy e de hosts. A factory impede caminhos de banco fora da raiz; isso deve ser considerado ao escolher disco persistente. |
| README | Instalação local e limites funcionais bem descritos. Acrescentar instruções Linux/Render, dados persistentes, migrações PostgreSQL, backup, incidentes, variáveis e validação; manter separado o resultado local de testes do resultado de homologação. |

### HTTPS, cookies e proxy

`APP_ENV=production` correto ativa `SESSION_COOKIE_SECURE` e HSTS; `HttpOnly` e `SameSite=Lax` já são padrão. A suite verifica flags reais em `Set-Cookie`. **HSTS não implementa redirecionamento HTTP por si só.** O Render termina TLS no balanceador, redireciona HTTP para HTTPS e encaminha a requisição ao serviço em HTTP. Isso precisa ser reconciliado com a percepção de esquema e cliente da aplicação. [Rede e TLS do Render](https://render.com/docs/web-services).

Configurar `ProxyFix` ou os mecanismos equivalentes do servidor somente depois de confirmar quais proxies e cabeçalhos são confiáveis. Validar quantidade de saltos para cada cabeçalho; não aplicar middleware e configuração WSGI de forma contraditória nem aceitar cabeçalhos de clientes como IP confiável. O teste simulado prova a ausência de tratamento na aplicação atual; **não comprova quais valores o Render/Gunicorn entregariam**, pois esse ambiente não foi iniciado. [Orientação do Flask para proxies](https://flask.palletsprojects.com/en/stable/deploying/proxy_fix/) e [configurações de confiança do Gunicorn](https://gunicorn.org/reference/settings/).

Adicionar futuramente `TRUSTED_HOSTS` com os hosts efetivos da aplicação e considerar o health check ao definir essa lista. `SERVER_NAME` não substitui a validação de hosts. A aplicação usa formulários com CSRF; os testes de produção devem incluir a combinação HTTPS, cookies, `Referer` e encaminhamento do proxy. [Configuração oficial do Flask](https://flask.palletsprojects.com/en/stable/config/).

## 5. Proteção antes de publicar no GitHub

Foi validado com o próprio Git, em ambiente temporário, que os padrões atuais ignoram:

- `.env`, `.env.production` e `.venv/`; `.env.example` continua publicável.
- `instance/`, inclusive backups do banco dentro dela.
- `*.sqlite3` e arquivos auxiliares `*.sqlite3-*`, `*.db` e `*.db-*`, além de `*.sqlite`.
- `tmp/`, `output/`, logs, temporários, caches e `.coverage`.

Lacunas reproduzidas com **nomes fictícios**, sem indicar que esses arquivos existam no projeto:

| Caminho de exemplo | Ignorado atualmente? | Proposta |
|---|---|---|
| `data.sqlite-wal`, `data.sqlite-shm` | Não | Cobrir `*.sqlite-*`, mantendo o schema SQL publicável |
| `backups/export.sql`, `backups/export.dump` | Não | Ignorar uma pasta dedicada `backups/` e formatos de dumps definidos no procedimento de backup |
| `credential.pem`, `credential.key` | Não | Ignorar chaves/certificados privados conforme formatos usados e revisar antes de adicionar arquivos |
| `.coverage.worker`, `coverage.json` | Não | Ignorar artefatos adicionais de cobertura; baixa gravidade, mas podem carregar caminhos locais |

Não ignorar indiscriminadamente `*.sql`, pois `app/schema.sql` e futuras migrações fazem parte do código. `.env.example` é intencionalmente uma exceção: deve continuar sem segredos. Arquivos ignorados ainda podem ser forçados ao índice; essa proteção não substitui revisão e secret scanning.

A inspeção da configuração mostra leitura de `SECRET_KEY`, credenciais de administrador e SMTP por ambiente, sem credencial operacional fixa identificada no código revisado. Testes contêm senhas fictícias identificadas e endereços `.test`. A busca automática limitada não reconhece todo formato possível de senha Gmail ou segredo arbitrário; o `.env` real não foi lido para comparar valores.

Como não há repositório nesta cópia, não foi possível auditar índice, commits, remotos ou histórico de outro repositório GitHub. Na etapa de publicação autorizada, revisar o índice e o histórico disponível, executar um scanner de segredos sem imprimir valores e habilitar proteção equivalente no GitHub quando disponível. Caso seja encontrada exposição real, revogar o segredo correspondente antes de publicar. **Nenhuma exposição foi constatada nesta revisão.**

## 6. Persistência: alternativas e estratégia recomendada

| Alternativa | Uso aceitável | Limitações / trabalho necessário |
|---|---|---|
| SQLite em filesystem efêmero | Somente demonstração descartável, sem expectativa de preservar contas | Inadequado para os dados reais e para contas verificadas |
| SQLite + disco persistente em serviço pago | Ponte para piloto pequeno, com baixa concorrência e backup externo | Uma instância, contenção de escrita, operação e recuperação do arquivo; sem compartilhamento do disco com worker separado |
| PostgreSQL gerenciado + aplicação sem estado local | **Recomendação para publicação profissional** | Portar persistência/migrações, testar concorrência, configurar conexões e backup; preserva a arquitetura modular |

No Render, apenas o conteúdo do ponto de montagem persiste. Um disco pertence a uma instância, não pode ser compartilhado com outro serviço e não está disponível no build/pre-deploy; ele também restringe escala horizontal e deploy sem interrupção. Um caminho dentro de `/opt/render/project/src/instance` pode atender à restrição atual da factory, se a configuração real usar essa raiz. `/var/data` fora do projeto seria rejeitado pelo código atual. Isso deve ser validado, não assumido. [Regras de discos persistentes](https://render.com/docs/disks).

O plano Free é para avaliação: o Postgres gratuito expira após 30 dias e não inclui recuperação gerenciada; serviços web Free também têm suspensão por ociosidade. Portanto, não adotar essa combinação como armazenamento definitivo de usuários. Confirmar planos e custos na contratação, sem presumir gratuidade de produção. [Limitações oficiais dos serviços Free](https://render.com/docs/free).

### Portabilidade para PostgreSQL

Proposta técnica, sujeita à revisão: **SQLAlchemy Core + psycopg 3 + Alembic**, mantendo os contratos dos modelos, serviços, blueprints e templates. Não é necessário converter entidades para ORM nem reescrever regras de escala. A biblioteca de persistência cuida de conexões, parâmetros e diferenças de dialeto; as migrações ficam versionadas. As versões e extras compatíveis com Python/Linux deverão ser homologados antes de fixar dependências.

| Dependência atual de SQLite | Tratamento necessário |
|---|---|
| `sqlite3.connect`, `sqlite3.Row`, `executescript`, `PRAGMA` | Conexão/pool PostgreSQL, resultados compatíveis com os consumidores e migrações específicas; substituir tratamento de exceções SQLite |
| Placeholders `?` e `:nome` | Parâmetros do driver/Core; nunca converter usando interpolação de valores |
| `INTEGER PRIMARY KEY` e `lastrowid` | Identidades/sequências e `INSERT ... RETURNING id` |
| `INSERT OR IGNORE`, gatilhos `RAISE(ABORT,...)` | Conflitos e constraints PostgreSQL; não copiar DDL SQLite diretamente |
| `COLLATE NOCASE`, `LIKE` | Unicidade de e-mail normalizado, pesquisa e ordenação equivalentes; validar Unicode, maiúsculas e curingas |
| Inteiros usados como booleanos | Definir conversão consistente; `active=1` não deve permanecer se o destino for `boolean` |
| Datas e horas em texto, `fromisoformat` nos serviços | Definir tipos/serialização na fronteira de persistência; não devolver `datetime` onde o código espera texto sem adaptar o contrato |
| Horários civis sem timezone | Preservar a semântica atual, inicialmente com tipos civis adequados e fuso configurado; não reinterpretar automaticamente como UTC/timestamptz |
| Expirações em epoch `REAL` | Mapear explicitamente para precisão suficiente ou adaptar para timestamps sem mudar as regras de prazo |
| `BEGIN IMMEDIATE` | Reprojetar bloqueio e consumo atômico; um `BEGIN` simples não oferece a mesma proteção |

**Isolamento entre empresas:** manter `company_id NOT NULL` nas entidades administrativas, FKs para empresas e a imutabilidade de pertencimento. Usar chaves de referência compostas, como `(company_id, employee_id)` para `(company_id, id)` de funcionários, e o equivalente para turnos. Adicionar a unicidade necessária nas tabelas referenciadas e manter os filtros por empresa autenticada. Preservar a unicidade global de e-mail administrativo normalizado; nome de empresa igual não autoriza compartilhamento. [Constraints PostgreSQL](https://www.postgresql.org/docs/current/ddl-constraints.html).

Sessões são vinculadas ao usuário, e cadastro/recuperação têm etapas anteriores à existência de uma empresa. Não forçar um tenant arbitrário nesses fluxos públicos. A autorização administrativa deve continuar falhando quando não houver contexto confiável.

**Concorrência:** escalas e indisponibilidades devem bloquear a mesma linha do funcionário antes de ler conflitos e gravar. Em edição que mova uma atribuição, bloquear os funcionários antigo e novo em ordem determinística. Para códigos, usar bloqueio/atualização condicional, limite de tentativas e consumo único na mesma transação; duas confirmações não podem criar duas empresas. Preservar contadores atômicos compartilhados entre workers. Se usar isolamento serializável, implementar repetição limitada da transação inteira para falhas de serialização. [Isolamento e repetição de transações PostgreSQL](https://www.postgresql.org/docs/current/transaction-iso.html).

Uma constraint de exclusão por intervalo pode reforçar conflitos entre escalas, mas não resolve sozinha conflitos com outra tabela de indisponibilidades. Primeiro manter uma estratégia consistente de bloqueio entre todos os escritores; avaliar a constraint como proteção adicional com testes específicos.

RLS pode ser uma segunda camada futura. Não substitui filtros, FKs ou testes. Exige contexto definido a partir da conta autenticada por transação, limpeza ao devolver conexões ao pool e um papel de runtime que não contorne as políticas. Proprietários e papéis privilegiados podem ignorar RLS, dependendo da configuração. **RLS ainda não existe neste projeto.** [Segurança por linha no PostgreSQL](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).

### Plano seguro de transferência dos dados

1. Implementar e testar o destino somente com dados fictícios; separar migrações de schema e importação de dados. Criar mapeamento explícito de todas as tabelas e campos.
2. Após autorização futura, abrir janela de manutenção e suspender todas as origens de escrita da instalação local. Produzir backup SQLite consistente com a API de backup, sem depender de copiar apenas o arquivo enquanto houver journal/WAL ativo. Manter o original preservado e acesso restrito.
3. Ensaiar a importação a partir de uma cópia protegida, verificando integridade e FKs dessa cópia. Não colocar snapshots, dumps ou dados pessoais no GitHub, em CI pública ou em logs.
4. Criar um PostgreSQL de destino novo e aplicar apenas as migrações desse backend. O comando atual `flask --app run migrate-db` continua sendo SQLite e **não serve para esse destino**.
5. Importar com transação, ordem de dependências e parâmetros: empresas/configurações, usuários, funcionários, turnos, escalas e indisponibilidades. Preservar IDs, `company_id`, status, snapshots de turnos, horários, históricos e hashes de senha exatamente. Não associar todas as empresas existentes à empresa 1.
6. Comparar contagens por tabela **e por empresa**, referências, campos relevantes e relatórios equivalentes. Confirmar que os hashes de senha foram copiados sem rehash. Ajustar sequências para que novos IDs não colidam com os importados.
7. Tratar sessões e desafios pendentes como estado transitório: propor novas sessões no domínio de produção e reinício de confirmações/recuperações pendentes, sem apagar esses registros do original. Não migrar mensagens de teste nem disparar notificações durante o ensaio.
8. Só liberar escrita no destino após login, cadastro, isolamento, PDF, backup e restauração aprovados. Evitar escrita simultânea em SQLite e PostgreSQL.
9. Registrar um ponto claro de retorno. Antes de aceitar novas escritas no destino, pode-se voltar à origem preservada. **Depois de novas escritas, voltar ao SQLite antigo perderia alterações**: suspender escrita e planejar reconciliação ou correção no PostgreSQL; não executar rollback automático de dados.

## 7. Confiabilidade dos e-mails

O transporte atual tem TLS com validação de certificado, timeout, mensagens HTML/texto e logs que omitem conteúdo sensível. Isso deve ser mantido. A entrega Gmail validada pelo usuário confirma a configuração local, mas a fila não é durável e não há coordenação transacional entre gravar o desafio e enfileirar o envio.

Proposta inicial: **outbox no próprio PostgreSQL e um background worker separado**, evitando adicionar Redis/Celery sem necessidade demonstrada.

- Gravar desafio e tarefa de envio na mesma transação. Identificar tarefa por desafio, finalidade e versão do código.
- Armazenar apenas o HMAC no desafio. Um worker não consegue recuperar o código a partir desse hash: se a outbox precisar guardar o conteúdo para enviar, proteger o payload com criptografia autenticada e chave externa exclusiva, nunca OTP em texto puro no banco ou na fila. A futura `EMAIL_OUTBOX_KEY` não deve ser a chave de sessão; requer gestão de rotação e compatibilidade com tarefas pendentes.
- Consumir tarefas com bloqueio/lease, estado persistente e concorrência segura. Repetir falhas transitórias com atraso progressivo, limite e expiração; não prorrogar a validade do código a cada tentativa.
- Cancelar tarefas de códigos consumidos, expirados ou substituídos por reenvio. Proteger a ordem para que um código antigo não seja enviado como se ainda fosse válido.
- Admitir processamento ao menos uma vez: uma falha após aceitação SMTP pode gerar duplicidade. Reenviar o mesmo código ainda válido deve ser seguro; não prometer entrega exatamente uma vez. Usar idempotência do provedor quando disponível.
- Monitorar quantidade pendente, idade, falhas e mensagens expiradas. Não registrar códigos, senha, payload, credenciais, destinatários completos ou exceções SMTP brutas.
- Worker e web devem sobreviver independentemente a restart/redeploy. Persistência da fila não remove as restrições de rede do plano escolhido nem garante chegada à caixa de entrada.

Decisão de transporte: serviço pago compatível com o SMTP atual é a opção de menor mudança de transporte; API HTTPS de provedor transacional é uma alternativa, especialmente para demonstração em Free. A segunda opção exige implementação, credencial própria, remetente autorizado e novos testes. Não trocar portas aleatoriamente para contornar a restrição do plano.

## 8. Proposta de deploy no Render — ainda não executável integralmente

**Os comandos abaixo são uma configuração-alvo.** Faltam dependências, backend PostgreSQL, migrações, outbox, worker e health check. Nenhum serviço ou manifesto de deploy foi criado nesta etapa.

### Topologia recomendada

| Componente | Proposta |
|---|---|
| Web Service | Runtime Python no Linux; Gunicorn; sem dados persistentes locais |
| Banco | Render Postgres pago, com backup/recuperação; major version escolhida e testada explicitamente |
| Background Worker | Processo Python para a outbox, mesma região do banco; comando a implementar |
| E-mail | SMTP permitido no serviço escolhido ou adaptador HTTPS; nenhuma mensagem de produção durante build/testes |
| Homologação | Banco, segredos e filas separados; destinatários de teste controlados; sem cópia pública de dados reais |
| GitHub/CI | Testes Linux e PostgreSQL, análise de dependências/segredos; publicação e conexão ao Render somente após autorização |

Usar a URL interna do PostgreSQL na mesma conta/região, restringir acesso externo e definir TLS conforme o tipo de conexão. A documentação atual informa `sslmode=require` para exigir TLS interno com certificados autossinados; `verify-full` não é suportado nesse caminho interno. Credenciais e URLs nunca devem aparecer em logs ou neste relatório. [Conexões e TLS do Render Postgres](https://render.com/docs/postgresql-creating-connecting).

### Build, inicialização e migrações

| Item | Valor-alvo e ressalva |
|---|---|
| Raiz | Raiz do repositório, onde estão `app/` e `requirements.txt` |
| Build | `pip install -r requirements.txt`, após ajustar e homologar dependências |
| Start | Comando Gunicorn abaixo, ajustado após teste de capacidade |
| Pre-deploy | `python -m alembic upgrade head` **somente após implementar Alembic e as revisões PostgreSQL** |
| Health check | `/health/ready`, a implementar; não usar o login como prova de acesso ao banco |
| Auto-deploy | Inicialmente desativado; depois condicionado aos testes aprovados e à política de revisão |

Exemplo de start no shell Linux do Render, não no PowerShell local:

```sh
gunicorn --bind "0.0.0.0:$PORT" --worker-class gthread --workers 1 --threads 2 --timeout 30 --access-logfile - --error-logfile - 'app:create_app()'
```

A factory existente é um alvo WSGI válido; não é necessário transformar `run.py` em servidor público. Gunicorn é voltado a Unix/Linux, portanto a homologação desse comando não foi feita no Windows. Um worker com duas threads é apenas um ponto inicial conservador: medir memória de scrypt, geração de PDF e conexões antes de aumentar concorrência. Personalizar o log de acesso para omitir query strings com dados de pesquisa e nunca incluir corpo/cookies. [Gunicorn com factory Flask](https://flask.palletsprojects.com/en/stable/deploying/gunicorn/).

Render recomenda bind em `0.0.0.0` e na variável `PORT`. Migrações PostgreSQL devem rodar uma única vez por release, com controle de concorrência e compatibilidade com a versão anterior. Não migrar em cada worker ou importar dados no build. O pre-deploy de serviços pagos executa em instância separada, sem acesso ao disco persistente do serviço; isso serve ao PostgreSQL remoto, não a uma migração do SQLite montado no web service. [Web Services](https://render.com/docs/web-services) e [etapas de deploy](https://render.com/docs/deploys).

### Variáveis de ambiente

| Variável | Situação e política proposta |
|---|---|
| `PYTHON_VERSION` | Fixar versão completa 3.14.x homologada. 3.14.3 reproduz os testes locais; avaliar patch de segurança mais recente antes da liberação, sem adotar versão não testada |
| `APP_ENV` | `production`, com futura validação estrita |
| `FLASK_DEBUG` | `0`; nenhum recarregador/debugger no serviço público |
| `SECRET_KEY` | Segredo aleatório forte, exclusivo do ambiente e estável entre workers/redeploys; não gerar a cada inicialização |
| `APP_TIMEZONE` | `America/Sao_Paulo`, preservando a semântica atual |
| `PORT` | Fornecido pelo Render; consumido pelo Gunicorn, não pelo comando local atual |
| `DATABASE_URL` | **Ainda não suportada.** Futuramente, conexão secreta PostgreSQL com política de TLS e limites de pool |
| `DATABASE_PATH` | Apenas SQLite local ou alternativa com disco; não deixar como fallback silencioso quando PostgreSQL for obrigatório |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` | Nomes já suportados; preencher no ambiente da hospedagem, sem copiar o `.env` ao repositório |
| `SMTP_STARTTLS`, `SMTP_SSL` | Modos exclusivos, TLS obrigatório em produção; defaults não devem mascarar valor inválido |
| Hosts/proxy/pool/outbox | Novas opções a definir na implementação; não são lidas hoje só por criá-las no painel |
| `EMAIL_OUTBOX_KEY` | Proposta futura para payloads protegidos; secret independente e disponível apenas a quem precisar enviar |
| `ADMIN_EMAIL`, `ADMIN_NAME`, `ADMIN_PASSWORD` | Somente provisionamento confiável quando necessário. Preservar administradores importados e não recriar/reescrever suas senhas; não manter senha de bootstrap no serviço web sem necessidade |

O arquivo `pyproject.toml` não fixa a versão usada pelo Render. Escolher `PYTHON_VERSION` ou `.python-version` explicitamente; não presumir que o default do provedor seguirá o ambiente local. A análise de sintaxe confirmou dependência de Python 3.14. [Fixação de Python no Render](https://render.com/docs/python-version).

### Verificações de funcionamento e recuperação

- Implementar prontidão com `SELECT 1` e revisão de schema esperada, timeout curto, sem informações de conexão na resposta. Falta de banco/schema deve retornar 503. Não enviar e-mail durante o health check. Render aceita respostas 2xx/3xx no caminho de saúde, razão adicional para evitar redirects de login como teste de banco. [Health checks do Render](https://render.com/docs/health-checks).
- Criar política de backup com recuperação gerenciada e exportações lógicas protegidas fora do web service. Definir e testar metas, por exemplo RPO de até 24h para a cópia lógica e RTO de até 4h; são objetivos propostos, **não garantias medidas**.
- Ensaiar restauração em um banco separado, com e-mails desativados, conferir empresas/contagens/login e registrar o tempo. Manter credenciais de backup com acesso restrito e política de retenção. Recuperação e janela disponíveis dependem do plano contratado. [Backups e recuperação PostgreSQL no Render](https://render.com/docs/postgresql-backups).
- Validar login/logout, cadastro, códigos, reenvio, recuperação e revogação; testar duas empresas e IDs cruzados; conferir PDF. Depois fazer restart e redeploy e repetir as verificações de persistência.
- Medir latência, erros 5xx/429, memória, conexões, contenção, tempo de PDF e idade da outbox. Confirmar shutdown seguro, devolução de conexões e recuperação após indisponibilidade temporária do banco/provedor.

## 9. Testes adicionais necessários

Não foram adicionados testes permanentes nesta etapa de revisão. A implementação futura deve incluir:

| Prioridade | Teste | Critério de aceite |
|---|---|---|
| Antes de homologação | Instalação Linux + Python fixado + Gunicorn | Dependências instalam do zero; factory inicia na porta fornecida sem debugger |
| Antes de PostgreSQL | Migrações em banco novo e atualização | Schema versionado, reaplicação segura, erro interrompe release; sem inicialização SQLite acidental |
| Antes de importar dados | Importação e reconciliação em destino descartável | IDs, empresas, hashes, horários e snapshots preservados; sequência seguinte correta; falha não produz importação parcial |
| Antes de liberar escrita | Toda a suíte de persistência no PostgreSQL real | SQLite temporário não é suficiente para comprovar semântica do novo backend |
| Antes de liberar escrita | Concorrência com conexões/processos distintos | Escalas sobrepostas e escala versus indisponibilidade não são confirmadas simultaneamente; edição entre funcionários também é segura |
| Antes de cadastro público | Confirmação/reenvio/reset concorrentes | Uma ativação, uso único, tentativas e contadores atômicos, códigos substituídos rejeitados |
| Antes de escalar workers | Revogação e rate limiting compartilhados | Logout/reset e limites valem entre workers e instâncias, sem estado crítico por processo |
| Antes de publicar serviço | Proxy real e cabeçalhos falsificados | IP correto por cliente, esquema HTTPS correto, limites não colapsam num único IP nem são burlados pelo cliente |
| Antes de publicar serviço | HTTPS/CSRF/hosts/cookies no domínio final | Cookies e referer funcionam com proxy; hosts não permitidos rejeitados; debug e ambiente inválido recusados |
| Antes de confiar na fila | Crash antes/depois de envio e reenfileiramento | Tarefa recuperável, payload protegido, nenhuma entrega de código expirado/rotacionado, sem vazamentos em logs |
| Antes de liberar contas reais | Restart, redeploy e restauração de backup | Dados por empresa preservados; metas de recuperação medidas |
| Antes de publicar serviço | Readiness sem banco/schema ou com timeout | 503 sem segredo; recuperação após reconexão; health check não depende do SMTP |
| Antes do GitHub | Scanner de segredos, índice/histórico e dependências | Artefatos privados ausentes; achados revisados; relatório sem valores sensíveis |
| Antes de uso sustentado | Carga, abuso e volume | Limites de memória/conexões/PDF demonstrados; sem vazamento entre tenants sob concorrência |
| Homologação funcional | Navegador, teclado e celular | Formulários, estados, CSRF, contador, senhas e PDFs conferidos no domínio HTTPS |
| Entrega de e-mail | Envio autorizado no ambiente final | Recebimento e conteúdo validados, inclusive reenvio; sucesso local informado não cobre esta rede |

## 10. Plano por etapas e pontos de revisão

| Etapa | Trabalho futuro | Entrega / condição para avançar |
|---|---|---|
| **0 — Revisão atual** | Revisar este relatório; decidir estratégia de dados, transporte e orçamento | **Somente este relatório e evidências foram produzidos. Nenhuma decisão estrutural aplicada.** |
| **1 — Preparar código para GitHub** | Ajustar ignore e documentação, escolher licença, separar runtime/testes, fixar Python e configurar CI Linux/análise de segredos | Conjunto publicável revisável e testes aprovados; sem upload automático |
| **2 — Persistência PostgreSQL** | Introduzir camada/driver e migrações; manter contratos; FKs compostas, bloqueios e testes no backend real | Banco fictício migrado e suíte validada, inclusive concorrência e isolamento |
| **3 — Operação e e-mail** | WSGI, validação de ambiente, proxy/hosts, readiness, outbox/worker, métricas e runbook de backup | Testes de falha/restart e de segurança aprovados; comandos reais documentados |
| **4 — Homologação Render** | Somente após autorização para deploy: serviços separados de teste, sem dados reais, envio autorizado | Persistência após redeploy, proxy/HTTPS, e-mails, carga e restauração conferidos |
| **5 — Transferência e liberação** | Nova autorização para tratar dados reais: manutenção, backup consistente, importação validada, decisão de liberação e plano de retorno | Administradores/dados preservados; validação por empresa; sem dupla escrita ou retorno com perda de alterações |
| **6 — Publicação e acompanhamento** | Push/publicação somente autorizados; monitorar a primeira operação e manter revisões de dependências/backups | Histórico sanitizado, alertas ativos e recuperação ensaiada |

As etapas de publicação do código podem ser antecipadas à transferência de dados se o conteúdo estiver sanitizado e a documentação indicar corretamente o status. **Publicação GitHub, deploy de homologação e migração/liberação de dados reais continuam exigindo as autorizações correspondentes.**

## 11. Limites desta conclusão

O relatório não atesta implantação em Linux/Render, compatibilidade PostgreSQL, entrega de e-mail no provedor final, capacidade sob carga, restauração real ou revisão do histórico de um repositório ausente. A revisão visual atual foi relatada pelo usuário; não foi repetida nesta auditoria. Também não foi feita varredura completa de CVEs ou comparação com os valores do `.env`.

O resultado dos 147 testes demonstra que os comportamentos cobertos continuam aprovados no ambiente local auditado. A recomendação é preservar essa base e implementar as etapas propostas em alterações pequenas, com evidências específicas antes de cada liberação.
