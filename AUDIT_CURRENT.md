# EscalaPro — auditoria técnica atual

**Atualizado em 24/11/2026, America/Sao_Paulo. Base local: 53af6e7 e alterações recebidas. Classificação A — versão da branch validada para portfólio público; integração em main pendente.**

## A. Diagnóstico atual

**CORRIGIDO:** acesso alternativo ao navegador, formulários responsivos, foco do calendário e origin Git. **CONCLUÍDO:** dez capturas reais, 21 verificações de interface, 28 combinações de página/resolução, regressões completas e documentação. **CONCLUÍDO:** publicação autorizada da branch e [CI remoto](https://github.com/mduardo1/EscalaPro-/actions/runs/45399188201) com 278 testes aprovados. **PENDENTE:** PR/integração em main, exigindo autorização separada. Não houve merge ou deploy.

Linux/PostgreSQL 18.3: **278 aprovados, zero ignorados**. Windows: **264 aprovados, 14 ignorados**, todos exercitados no Linux. Cobertura Linux: **92,33% de linhas, 85,40% de ramificações, 90,86% combinada**. As 21 verificações Playwright não são somadas aos 278 casos pytest. Nenhuma falha foi ignorada para obter aprovação.

O .env e o banco principal tiveram SHA-256 comparado antes/depois, sem alteração. Os 26 caminhos alterados/não rastreados recebidos foram inventariados e preservados; diff e baselines privados estão em tmp/browser-validation-20261123/. Os testes usaram dados fictícios, sem envio real de e-mail. Relatórios anteriores foram preservados nessa pasta como AUDIT_BEFORE_BROWSER.md e PORTFOLIO_BEFORE_BROWSER.md. Não publicar esses artefatos privados.

O [checklist atual](PORTFOLIO_READINESS_REPORT.md) reúne status, comandos, funcionalidades e pendências. Preparação de portfólio não aprova operação em produção.

### Arquitetura e manutenção

| Camada | Avaliação do código atual |
|---|---|
| Factory e configuração | `create_app` registra blueprints, CSRF, middleware de proxy, cabeçalhos e erros. Configuração lida por factory, sem inicialização automática do banco principal. Produção exige PostgreSQL, hosts permitidos e configurações de e-mail compatíveis. |
| Rotas e serviços | Rotas de contas, funcionários, turnos, dashboard, escalas e saúde separadas. Regras de conflitos e validação ficam nos serviços. Não foi necessária uma reorganização ampla. |
| Persistência | SQLite nativo; PostgreSQL por SQLAlchemy **Core** e adaptação ao pequeno contrato dos modelos. Os modelos são funções de acesso a dados, não entidades de ORM declarativo. Consultas usam parâmetros nomeados. |
| Empresas | Empresa derivada da sessão autenticada; filtros obrigatórios e integridade adicional. SQLite usa gatilhos, PostgreSQL usa FKs compostas e gatilhos de imutabilidade. Não há RLS. |
| Transações | Atribuições e ausências validam/gravam sob `BEGIN IMMEDIATE` no SQLite e locks por funcionário no PostgreSQL. Rollbacks e concorrência foram executados nos dois backends. |
| Migrações | Adoção SQLite e duas revisões Alembic. Reversão de baseline populada/outbox com tarefas é recusada. Nenhuma migração destrutiva foi executada em dados reais. |
| Exportação | PDF em memória com ReportLab, texto escapado, fonte incorporada e tabela paginada. Relatórios mensal/semanal compartilham a mesma implementação. |
| E-mail | SMTP/API HTTPS, testes com remetentes simulados; outbox criptografada e worker separados das requisições em produção. Entrega real não foi homologada. |
| Compatibilidade | O código utiliza sintaxe de Python 3.14. Gunicorn é exclusivo do Linux; a dependência possui marcador para Windows. Foram executados tanto Python 3.14.3/Windows quanto 3.14.8/Linux. |

Não foi constatado defeito que justificasse trocar o framework, adotar ORM completo ou reescrever serviços. Há oportunidades de evolução: rotas/templates de calendário extensos, ausência de paginação e consultas que carregam todo o histórico de um funcionário para validar conflitos. A montagem mensal percorre as atribuições para cada dia e os alertas percorrem semanas completas. Isso é limitado para a demonstração de 150 atribuições; não houve benchmark que sustente capacidade para bases grandes. Não foram removidas funções por suposta inutilidade nem realizadas refatorações cosméticas.

## B. Achados e correções

AT-01 a AT-09 foram reproduzidos/corrigidos em **12/11/2026**, preservados abaixo. A suíte atual revalidou suas regressões. Consultas de vulnerabilidades citadas nesses achados são históricas, não consultas novas em 24/11. AT-03 foi encerrado pela execução remota real em 24/11, indicada abaixo.

### AT-01 — Datas alternativas aceitas, com navegação inválida após gravar

- **Gravidade:** média, consistência da validação e experiência de salvamento.
- **Reprodução:** POST de atribuição com `work_date=20261112`, `2026-W46-4` ou `2026W464`. A reprodução inicial retornou 302, aceitando os formatos alternativos. A rota usa o valor bruto para construir o mês do redirect; esse valor não corresponde ao formato aceito pelo calendário mensal.
- **Causa:** `date.fromisoformat` aceita representações além de `AAAA-MM-DD`; a rota pressupõe o formato canônico ao recortar os sete primeiros caracteres.
- **Arquivo/correção:** `app/services/validation.py` exige string canônica antes da conversão e dos limites. O POST inválido retorna 422 e não grava; consulta semanal inválida retorna 400.
- **Evidência:** seis casos parametrizados de `test_assignment_rejects_noncanonical_date_before_writing` e `test_week_query_rejects_noncanonical_dates` em `tests/test_current_audit.py`, falhando antes e aprovados depois. Datas válidas, bissextos e bordas seguem cobertos pela suíte existente.

### AT-02 — Edição selecionava um dia sem relação com a atribuição

- **Gravidade:** baixa, interface do calendário.
- **Reprodução:** abrir a edição de uma atribuição em 05/11 pelo calendário de novembro. O formulário editava a atribuição correta, mas os detalhes e o destaque do dia usavam Hoje ou o início do período. Uma continuação de 31/10 também podia selecionar outro dia de novembro.
- **Causa:** `render_calendar` não considerava a atribuição editada para determinar o dia padrão.
- **Arquivo/correção:** `app/routes/schedules.py` seleciona o dia da atribuição quando ela toca o período exibido; uma continuação seleciona o primeiro dia visível. Seleção explícita em `day` continua prevalecendo.
- **Evidência:** `test_edit_selects_assignment_day_within_displayed_period` (mensal/semanal), `test_edit_continuation_selects_first_visible_day` e `test_explicit_day_selection_is_preserved_while_editing`.

### AT-03 — O workflow nativo não selecionava os clientes PostgreSQL 18

- **Gravidade:** média, confiabilidade do CI e ensaio de backup.
- **Reprodução/verificação:** o YAML original usa serviço PostgreSQL 18.3 e executa pytest diretamente no runner; não instala nem seleciona `pg_dump`/`pg_restore` 18. O Dockerfile já copia ferramentas 18, mas não é usado por esse job. Não foi reproduzida uma execução remota com cliente 16 nesta auditoria.
- **Causa:** correção aplicada à imagem Docker sem equivalente no workflow nativo. O cliente padrão do runner fica implícito.
- **Arquivo/correção:** `.github/workflows/tests.yml`: runner `ubuntu-24.04`, timeout de 20 minutos, repositório oficial PGDG, instalação de `postgresql-client-18`, precedência de `/usr/lib/postgresql/18/bin` no PATH e conferência das duas versões antes dos testes.
- **Evidência atual — CONCLUÍDO:** YAML analisado e backup/restauração aprovado no Docker; o [run GitHub 45399188201](https://github.com/mduardo1/EscalaPro-/actions/runs/45399188201) também passou no commit bfde09c, com clientes 18.7 instalados/selecionados no Ubuntu 24.04, servidor 18.3 e 278 testes aprovados. Nenhum erro foi suprimido para aprovar.
- **Fundamento:** [compatibilidade documentada do pg_dump](https://www.postgresql.org/docs/18/app-pgdump.html) e [instalação oficial no Ubuntu](https://www.postgresql.org/download/linux/ubuntu/). Um cliente de versão principal inferior não pode exportar o servidor mais novo.

### AT-04 — Dependência de testes pypdf com avisos conhecidos

- **Gravidade:** média no ambiente de ferramentas; não foi demonstrada exploração da aplicação web.
- **Reprodução:** `pip-audit 2.10.1` consultou avisos públicos para `pypdf 6.21.0` e retornou 11 identificadores de vulnerabilidade. Incluem consumo excessivo de recursos e loops ao processar PDFs malformados.
- **Causa:** versão de desenvolvimento fixada antes dos patches disponíveis.
- **Arquivo/correção:** `requirements-dev.txt`, de 6.21.0 para **6.21.4**; a mesma versão foi instalada no `.venv`. O servidor exporta com ReportLab e não oferece upload de PDFs; não foi atribuído esse risco ao endpoint de exportação.
- **Evidência:** suíte final inteira, extração de relatórios e nova consulta sem avisos. [Aviso oficial com patch 6.21.4](https://github.com/py-pdf/pypdf/security/advisories/GHSA-5849-834g-hvw5).

### AT-05 — pip local desatualizado

- **Gravidade:** baixa no escopo da aplicação; risco de ferramenta de instalação.
- **Reprodução:** inventário do `.venv` encontrou `pip 25.3`; a consulta retornou cinco identificadores distintos de avisos, alguns duplicados pela base de avisos. Os dois pacotes afetados inicialmente produziram 21 registros, correspondentes a 16 IDs distintos no total.
- **Causa:** ferramenta do ambiente virtual anterior às correções de instalação/extração de pacotes.
- **Correção:** atualização local para **pip 26.3**, sem mudar pacotes globais. `pip` não foi acrescentado como dependência de runtime da aplicação.
- **Evidência:** `pip check` aprovado e inventário posterior consultado sem avisos conhecidos. A auditoria não certifica o pip que estará em outra máquina ou imagem futura. [Política e avisos oficiais do pip](https://github.com/pypa/pip/security/advisories).

### AT-06 — Auditor perdia o caminho original de arquivos do Git

- **Gravidade:** média. Havia falsos positivos e um falso negativo em uma proteção de publicação.
- **Reprodução:** executar `scripts/audit_publication.py` no repositório com índice/histórico gerou 26 alertas sobre URLs fictícias locais e contatos públicos das fontes já aceitos na cópia de trabalho. Em repositórios fictícios, um `.env.example` com valor não vazio no índice/histórico não era reconhecido pela regra específica, mesmo com a cópia de trabalho limpa.
- **Causa:** `inspect_content` usava rótulos como `index:...` e `history-blob:...` tanto para relatar origem quanto para aplicar regras por caminho. Esses rótulos não correspondiam a `tests/`, aos arquivos das fontes ou ao nome `.env.example`.
- **Arquivos/correção:** `scripts/audit_publication.py` preserva `source_path` separado do rótulo; regras continuam iguais para as três camadas. `tests/test_publication_audit.py` verifica também que senha não aprovada segue sendo sinalizada no índice e no histórico.
- **Evidência:** reprodução com **3 falhas e 8 aprovados** antes da correção; **11 aprovados** depois. Segredos simulados, bancos forçadamente rastreados e chaves privadas continuam bloqueados. Auditoria final do projeto e manifesto estão discriminados em D.

### AT-07 — Documentação misturava etapas históricas e estado atual

- **Gravidade:** baixa, credibilidade e reprodução do portfólio.
- **Reprodução:** README apresentava contagens de etapas anteriores; o relatório de publicação descrevia ausência de commits, embora o projeto já tenha um. O diagnóstico original de produção contém limitações posteriormente implementadas.
- **Causa:** acúmulo de relatórios sem uma referência única para a revalidação atual.
- **Arquivos/correção:** README atualizado, este relatório criado, notas históricas acrescentadas a `AUDIT_REPORT.md`, `GITHUB_READINESS.md` e `PRODUCTION_READINESS.md`; compatibilidade de clientes documentada em `DEPLOYMENT.md`. Conteúdo histórico preservado.
- **Validação:** revisão dos links locais, dos resultados JUnit e do manifesto. Não foram inventados clientes, usuários, métricas comerciais ou certificações.

### AT-08 — Senha na query PostgreSQL exposta nos argumentos do backup

- **Gravidade:** média, exposição local de credencial operacional. Não foi demonstrado acesso remoto nem vazamento de uma credencial real.
- **Reprodução:** SQLAlchemy aceita `password` na query da URL e lhe dá precedência sobre userinfo. Dois testes com subprocesso simulado demonstraram que essa senha entrava no `--dbname` do `pg_dump`, ficando visível em inspeções dos argumentos. Ambos falharam antes da correção.
- **Causa:** `postgres_environment` removia apenas `url.password` dos argumentos, mas copiava toda a query para o conninfo.
- **Arquivos/correção:** `app/services/backup_service.py` extrai também a senha da query, respeita a precedência do driver e remove `password` antes de construir o conninfo. A senha continua somente em `PGPASSWORD` no ambiente do subprocesso, conforme o contrato existente. Nenhuma credencial real foi lida para o teste ou alterada.
- **Evidência:** `test_pg_query_password_not_in_subprocess_arguments` em `tests/test_phase2_operations.py`, com e sem senha em userinfo; confirma que as duas senhas ficam fora dos argumentos e `sslmode` é preservado. **31 testes operacionais aprovados**, seguidos pelas suítes finais completas e pelo dump/restauração PostgreSQL real.
- **Limite:** variáveis de ambiente também precisam da proteção da conta de serviço e do host; a correção não afirma ocultar credenciais de um administrador do sistema operacional.

### AT-09 — Teste Gunicorn interrompia a espera em timeout transitório

- **Gravidade:** baixa, confiabilidade da validação de integração.
- **Reprodução:** primeira suíte Linux: 274 aprovados e uma falha em `test_linux_gunicorn_serves_database_readiness_without_logging_queries`, por timeout de uma sondagem de um segundo durante a inicialização. Repetição isolada passou. Um caso adicional, com o primeiro timeout injetado e HTTP real nas requisições seguintes, reproduziu deterministicamente a falha antes da correção.
- **Causa:** o laço de espera tratava `URLError`, mas não o `TimeoutError` que a leitura de um socket pode lançar diretamente.
- **Arquivo/correção:** `tests/test_postgres.py` trata ambos durante a inicialização. **Mantidos** prazo total de 20 segundos, falha se o processo encerrar, exigência de HTTP 200 real e verificação de que parâmetros privados da URL não entram nos logs. Nenhum timeout de produção foi ampliado.
- **Evidência:** as duas variantes Gunicorn, normal e com timeout inicial, passaram na suíte Linux final. Foi corrigido o teste, com justificativa técnica; não foi mascarado um erro persistente da aplicação.

### AT-10 — Origin: CORRIGIDO; publicação da branch: CONCLUÍDA

Com autorização explícita, origin foi corrigido para https://github.com/mduardo1/EscalaPro-.git e conferido para fetch/push. As bases têm commits iniciais distintos, mas 119 arquivos de blobs idênticos. O [plano de reconciliação](GIT_RECONCILIATION_PLAN.md) foi executado em nova cópia do remoto. Commit bfde09c e push foram autorizados e realizados nessa cópia. A pasta principal preservou seu HEAD e índice; não houve merge ou rebase.

### AT-11 e AT-12 — Interface: CORRIGIDOS


Verificadas **1920 × 1080, 1366 × 768, 768 × 1024 e 390 × 844** em dashboard, funcionários, novo funcionário, turnos, calendário mensal, semanal e configurações: **28 combinações**. Conferidos limites da página, campos rotulados, disposição dos formulários, largura dos selects e menu móvel com Escape. Dez imagens também inspecionadas visualmente. Nenhuma página apresentou transbordamento horizontal nas combinações verificadas; calendários/tabelas podem ter rolagem interna. Trata-se de emulação de viewport no Chromium desktop, sem certificação de Safari/Firefox ou aparelhos físicos.

| Achado | Causa/reprodução | Correção e evidência |
|---|---|---|
| **UI-01, média: formulários comprimidos** | Em 390/768 px, `.schedule-forms` em pages.css sobrescrevia a coluna única de layout.css, mantendo duas colunas e campos cortados. | `app/static/css/pages.css`: coluna única até 980 px; ocultação do rótulo redundante de contagem no cabeçalho mensal estreito. Asserções de posição/largura passaram. |
| **UI-02, baixa: foco perdido ao selecionar dia** | O select recebia foco antes de concluir a navegação por âncora; o foco terminava no BODY. A data selecionada continuava correta. | `app/static/js/schedules.js`: foco em pageshow/hashchange, no próximo quadro, com preventScroll. Seleção e lista completa passaram com o elemento correto focado. |

Reproduções anteriores à correção e resultado final: `tmp/browser-validation-20261123/`. Duas falhas do próprio executor também foram corrigidas durante sua preparação: navegação para a mesma âncora sem resposta HTTP nova e captura durante rolagem suave. Não foram atribuídas ao produto.

## C. Regressões e cobertura depois das correções

| Ambiente | Aprovados | Ignorados | Falhas/erros | Tempo pytest |
|---|---:|---:|---:|---:|
| Linux/Python 3.14.8/PostgreSQL 18.3 | **278** | **0** | **0/0** | 133,85 s |
| Windows/Python 3.14.3 | **264** | **14** | **0/0** | 133,36 s |

Os 14 casos PostgreSQL ignorados no Windows passaram no Linux, incluindo migrações, concorrência, isolamento, backup/restauração e Gunicorn. São **278 casos distintos**, sem somar execuções. As 21 verificações Playwright são adicionais, fora dessa contagem. Nenhum teste foi removido ou enfraquecido para aprovar.

| Cobertura de app, migrations, scripts | Linhas | Ramificações | Combinada |
|---|---:|---:|---:|
| Linux | **1.877/2.033 = 92,33%** | **468/548 = 85,40%** | **90,86%** |
| Windows | 1.754/2.033 = 86,28% | 423/548 = 77,19% | 84,35% |

Coberturas separadas, sem fusão. A medição não inclui HTML/CSS/JS nem o executor de navegador, que fica junto dos testes. Persistem caminhos de configuração, transporte e erros sem cobertura; run_demo.py continua com 0% nessa medição. Black conferiu **66 arquivos**, os cinco JS passaram em node --check, pip check e git diff --check passaram.

Os PDFs baixados foram lidos com pypdf; a regressão completa verifica também relatórios vazios, texto longo e isolamento. A inspeção anterior de 20 páginas renderizadas é histórica (12/11), não uma nova inspeção integral dessas páginas.

## D. Navegador e ambiente isolado

A ferramenta de computador retornou lista vazia de navegadores e `browser access host is unavailable`, apesar de haver Chrome instalado/em execução. A evidência indica indisponibilidade da ponte de automação da sessão; não permite determinar sua causa interna nem indica defeito da aplicação.

Após autorização para a alternativa, foram instalados **Playwright 1.65.2** e **greenlet 3.5.6** em `tmp/browser-tools`, separados do ambiente da aplicação. O instalador oficial colocou Chromium/Chrome for Testing **159.0.8154.6**, revisão 1255, e auxiliares em `tmp/browser-browsers`. Execução com `chromium_sandbox=True`, sem perfil pessoal, sem ignorar erros TLS e sem desativar proteções. Referência: [instalação oficial do Playwright](https://playwright.dev/python/docs/intro).

O executor `tests/browser/run_browser_checks.py` copia uma demo identificada para um arquivo exclusivo e inicia servidor em loopback/porta efêmera. Cadastro e recuperação usam mensagens apenas em memória. Nenhum e-mail real foi enviado. Navegador e servidor foram encerrados ao fim. As capturas não mostram credenciais, códigos, tokens ou abas pessoais.

### Funcionalidades executadas na interface

| Área | Resultado no navegador |
|---|---|
| Contas | **CONCLUÍDO** — páginas privadas, login vazio/inválido/válido, cadastro de empresa, confirmação simulada, cooldown de reenvio, recuperação simulada e logout. |
| Isolamento | **CONCLUÍDO** — nova empresa sem dados da demo; ID de funcionário alheio rejeitado com 404. A suíte cobre as demais operações SQLite/PostgreSQL. |
| Dashboard | **CONCLUÍDO** — indicadores, alertas, próximos turnos e gráfico JavaScript renderizado. |
| Funcionários | **CONCLUÍDO** — validação, cadastro, edição, desativação e reativação. Exclusão física é **PENDENTE como evolução**: não existe no MVP; histórico preservado. |
| Turnos | **CONCLUÍDO** — horário inválido rejeitado, cadastro noturno e edição. Exclusão física é **PENDENTE como evolução**: não existe na interface. |
| Calendário | **CONCLUÍDO** — 28/29/30/31 dias, bissexto, dezembro/janeiro, Hoje, seleção/foco, múltiplas atribuições e lista completa do dia. |
| Escalas | **CONCLUÍDO** — atribuição em 29/02/2028, data conferida diretamente no SQLite, conflito impedido, continuação noturna no próximo mês, edição e remoção com confirmação JS. |
| Indisponibilidades | **CONCLUÍDO** — período de férias, bloqueio de conflito e remoção. |
| Semana/configurações | **CONCLUÍDO** — alternância mensal/semanal e gravação das preferências da empresa. |
| PDF | **CONCLUÍDO** — cliques e downloads mensal/semanal; leitura independente confirmou conteúdo fictício, 12 e 7 páginas; mensal aberto no visualizador real. |

**Console/rede:** zero exceções JavaScript, zero respostas HTTP inesperadas e nenhum 5xx. Os cinco erros de recurso no console correspondem aos testes negativos deliberados: 401, 404 e três 422. Seis eventos `net::ERR_ABORTED` foram registrados durante navegações interrompidas e os dois downloads; ambos os downloads concluíram e o gráfico foi verificado renderizado. Os eventos brutos foram mantidos no JSON; não se alega log inteiramente vazio.

## E. Controles e limitações

### Matriz funcional e de segurança

| Área | Evidência executada |
|---|---|
| Contas | Cadastro pendente, empresa própria após confirmação, código com zero inicial, código errado/expirado/usado/de outro pedido, cinco tentativas, cooldown/reenvio, duplicidade de conta sem sobrescrever credenciais, recuperação, autorização de reset de uso único, revogação de sessões e hashes. `test_account_flows.py`, `test_auth.py`, `test_http_smoke.py`. |
| Segurança web | SQL Injection no login/pesquisa, XSS nos domínios textuais, CSRF ausente/adulterado/de outra sessão/expirado, rotas privadas, IDs de outras empresas, cookies adulterados e reutilizados após logout, expiração absoluta, limites de requisição e erros sem detalhes. `test_audit_modules.py`, `test_audit_regressions.py`, `test_company_isolation.py`. Cookies Secure/HSTS são verificados com HTTPS simulado, não com infraestrutura real. |
| Funcionários | Criar, editar, pesquisar, validar campos, desativar/reativar e preservar histórico. Homônimos/e-mails opcionais repetidos são permitidos pelo modelo; não foram inventadas novas regras de unicidade. |
| Turnos | Criar/editar, dia/noite, meia-noite, horários iguais/inválidos, intervalos e cores; snapshots preservados após edição. A interface não possui exclusão de turno; SQL para remover turno referenciado é bloqueado por FK nos testes SQLite. Sobreposições são proibidas na atribuição do funcionário, não no cadastro abstrato de turnos. |
| Calendário | Meses de 28/29/30/31 dias, 2000 bissexto/2100 não bissexto, início na segunda, dezembro/janeiro, limites 2000–2100, Hoje com relógio simulado, seleção, CRUD, rollback, dia cheio, continuação noturna e isolamento. `test_monthly_schedules.py` tem 33 casos já presentes ao iniciar. Templates e respostas HTTP foram validados; cliques/JS não foram executados. |
| Folgas/férias | Ausências por intervalo, conflitos em ambas as ordens de criação e noturnos, remoção inexistente e manutenção dos valores em erro. O tipo é um motivo textual; não existe motor jurídico de férias. |
| SQLite e PostgreSQL | Integridade/FKs, rollback, migrações, isolamento, concorrência, importação de duas empresas com IDs/hashes/histórico e backup/restauração em destino separado. PostgreSQL também validou códigos/outbox concorrentes, baseline reversível vazia e recusa de downgrade com dados. Não foram simulados disco cheio ou queda abrupta de energia. |
| Outbox | Criptografia, tarefa e desafio atômicos, rotação/cancelamento/expiração, lease abandonado, ACK antigo, limite/retry, credenciais e erros omitidos, worker com transporte desativado preservado. SMTP/API são simulados. |
| HTTP real | Servidor WSGI em loopback e porta efêmera; home, conta/código/reset, login, cadastros, noite atravessando mês, edição, desativação com histórico, PDF, remoção, logout e rejeição de sessão antiga. Servidores de testes encerrados em `finally`. |

Não foram confirmadas falhas críticas ou altas de acesso entre empresas nos cenários executados. Isso não significa ausência de falhas não cobertas.

A inspeção de PDFs de 12/11 cobriu 20 páginas renderizadas, cinco visualmente, incluindo mês vazio. Nesta etapa foram baixados PDFs reais mensal/semanal (12 e 7 páginas), lidos independentemente e o mensal fotografado no Chromium. Não se declara nova revisão visual integral de todas as páginas.

A consulta de vulnerabilidades de 47 pacotes por ambiente em 12/11 é histórica; não foi repetida nesta etapa. pip check atual passou, mas não certifica ausência de CVEs. Não houve varredura de imagens/OS, pentest externo, teste de carga ou homologação de infraestrutura. Não existe lock transitivo completo com hashes, RLS, medição de RPO/RTO ou certificação de acessibilidade. DejaVu não garante CJK/emojis.

## F. GitHub e CI

**Origin CORRIGIDO** mediante autorização explícita, com estes comandos:

```powershell
git remote set-url origin https://github.com/mduardo1/EscalaPro-.git
git remote -v
```

Branch local main, HEAD `53af6e7`; main público consultado: `74e787e62646fe6219b00a508c2e80f0b53c63c1`. Ambos têm a árvore `9c73b9127829246aab2073d84fe9f3b08b908c91`: **119 arquivos com blobs idênticos**. Os commits iniciais são distintos. Foi preparada uma cópia em tmp/publication-review, branch portfolio-validation, a partir desse main remoto; nela foram aplicados somente os 138 candidatos do manifesto, preservando esta pasta. Os arquivos são comparados por SHA-256 com a origem já testada antes de aprovar a publicação. Comandos, efeitos e aprovações: [plano de reconciliação](GIT_RECONCILIATION_PLAN.md).

O YAML local usa Ubuntu 24.04, PostgreSQL 18.3, instalação PGDG de clientes 18, precedência no PATH e conferência de pg_dump/pg_restore. Oito etapas, permissões mínimas e falhas obrigatórias, sem continue-on-error. Docker/Linux passou; a instalação PGDG no runner Ubuntu também foi validada pelo run remoto abaixo.

**Publicação e CI CONCLUÍDOS para a branch [portfolio-validation](https://github.com/mduardo1/EscalaPro-/tree/portfolio-validation)**, com autorização explícita. Commit de implementação `bfde09cac0257ca0037f72539c6fe379ece1f0ee`: 39 arquivos alterados/adicionados. O [run 45399188201](https://github.com/mduardo1/EscalaPro-/actions/runs/45399188201) passou em 24/11/2026: **278 testes aprovados, zero ignorados, zero falhas**, em 50,70 s de pytest. Instalação PGDG e conferência de pg_dump/pg_restore **18.7**, servidor PostgreSQL **18.3**, pip check e Gunicorn passaram no runner Ubuntu 24.04. A cobertura remota, apenas de app, foi reportada como **93% combinada arredondada**; seu escopo é menor que app+migrations+scripts da tabela local, portanto não substituir os percentuais locais por esse valor. O run antigo com falha permanece histórico. **Integração em main PENDENTE**, sem merge, rebase, force push, PR ou deploy.

### Arquivos, capturas e preservação

Alterações desta continuação: `app/static/css/pages.css`, `app/static/js/schedules.js`, `README.md`, `AUDIT_CURRENT.md`, este relatório, `docs/screenshots/README.md` e `PUBLICATION_MANIFEST.txt`. Adicionados `requirements-browser.txt`, `tests/browser/run_browser_checks.py`, `GIT_RECONCILIATION_PLAN.md` e os dez PNGs listados no [guia de capturas](docs/screenshots/README.md). Origin foi corrigido na pasta principal; commit e push foram autorizados e executados somente na cópia de revisão. Os demais diffs recebidos foram preservados; a lista exata dos candidatos está em PUBLICATION_MANIFEST.txt.

**.env e banco principal preservados:** SHA-256 antes/depois sem alteração. A demo fonte não foi modificada pelo executor; alterações ocorreram na cópia browser-run-*.demo.sqlite3. Credenciais e códigos permaneceram privados. O projeto Compose escalapro-browser-regression foi encerrado; consulta final por rótulo não encontrou seus contêineres, redes ou volumes. Outros projetos Docker foram preservados.

Evidências privadas: `tmp/browser-validation-20261123/full-run/browser-results.json`, PDFs baixados, linux.xml, windows.xml, coberturas e baselines. Auditoria de publicação: **138 candidatos, 119 rastreados, zero preparados no índice e zero apontamentos**, incluindo as dez imagens revisadas. Inventário e hashes: `tmp/github-publication-audit.json`; heurísticas e revisão de binários não constituem certificação de ausência de segredos. A consulta de avisos de dependências de 12/11 é histórica, não foi repetida nesta etapa. pip check confirma compatibilidade instalada, não ausência de CVEs.

## G. Próxima ação

Revisar [README e capturas](README.md), [manifesto](PUBLICATION_MANIFEST.txt) e [plano de reconciliação](GIT_RECONCILIATION_PLAN.md). A branch foi publicada e o CI remoto passou. A próxima autorização é para PR/integração em main; até lá, apresentar pelo link direto da branch validada. Licença depende do proprietário; exclusão física de funcionários/turnos e outros navegadores são evoluções pendentes.

Classificação **A — versão da branch pronta para portfólio público**, com integração em main pendente. Produção exige homologação de HTTPS, infraestrutura, e-mail, operação, restauração externa e carga. Não há evidência de clientes reais, SLA ou resultados comerciais para divulgar.
