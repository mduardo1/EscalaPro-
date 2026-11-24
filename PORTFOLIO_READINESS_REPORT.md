# EscalaPro — validação final para portfólio

**Execução: 23–24/11/2026, America/Sao_Paulo. Classificação B — pronto para demonstração local, com publicação e novo CI pendentes.**

O bloqueio de navegador foi contornado com Playwright autorizado. A interface real passou por 21 verificações funcionais e 28 combinações de página/resolução. Dez capturas reais foram geradas e revisadas. Duas falhas de interface foram reproduzidas e corrigidas. As regressões completas Windows/Linux passaram depois das correções.

## 1. Checklist principal

| Item | Status | Evidência e limite |
|---|---|---|
| Navegador | **CORRIGIDO** | Chromium real, sandbox habilitada, perfil temporário e TLS padrão. Cliques, formulários, diálogos, foco, console e rede executados. A ponte original do host continua indisponível. |
| Responsividade | **CORRIGIDO** | Quatro viewports e sete páginas por viewport; corrigida a cascata CSS que comprimia formulários em até 980 px. |
| Capturas | **CONCLUÍDO** | Dez PNGs reais revisados em `docs/screenshots/`; PDF fotografado no visualizador do Chromium. |
| Preparação GitHub | **CORRIGIDO** | Origin corrigido com autorização; bases comparadas e plano seguro documentado. Publicação **PENDENTE**, com autorização separada. |
| GitHub Actions | **BLOQUEADO** | Workflow local revisado e backend Linux aprovado; novo run remoto depende de publicação autorizada. |
| Testes | **CONCLUÍDO** | Linux: 278 aprovados/0 ignorados. Windows: 264 aprovados/14 ignorados. Mais 21 verificações de navegador, separadas da suíte pytest. |
| Segurança e preservação | **CONCLUÍDO** | Regressões defensivas, isolamento, CSRF, sessão, auditor de publicação e comparação dos arquivos privados; conclusão restrita aos cenários executados. |
| Documentação | **CONCLUÍDO** | Este relatório, auditoria atual, README com imagens reais, guia reproduzível, manifesto e plano de reconciliação. |

São **quatro CONCLUÍDOS, três CORRIGIDOS e um BLOQUEADO**, sem somar as subtarefas abaixo.

## 2. Navegador e ambiente isolado

A ferramenta de computador retornou lista vazia de navegadores e `browser access host is unavailable`, apesar de haver Chrome instalado/em execução. A evidência indica indisponibilidade da ponte de automação da sessão; não permite determinar sua causa interna nem indica defeito da aplicação.

Após autorização para a alternativa, foram instalados **Playwright 1.65.2** e **greenlet 3.5.6** em `tmp/browser-tools`, separados do ambiente da aplicação. O instalador oficial colocou Chromium/Chrome for Testing **159.0.8154.6**, revisão 1255, e auxiliares em `tmp/browser-browsers`. Execução com `chromium_sandbox=True`, sem perfil pessoal, sem ignorar erros TLS e sem desativar proteções. Referência: [instalação oficial do Playwright](https://playwright.dev/python/docs/intro).

O executor `tests/browser/run_browser_checks.py` copia uma demo identificada para um arquivo exclusivo e inicia servidor em loopback/porta efêmera. Cadastro e recuperação usam mensagens apenas em memória. Nenhum e-mail real foi enviado. Navegador e servidor foram encerrados ao fim. As capturas não mostram credenciais, códigos, tokens ou abas pessoais.

## 3. Funcionalidades executadas na interface

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

## 4. Resoluções e correções

Verificadas **1920 × 1080, 1366 × 768, 768 × 1024 e 390 × 844** em dashboard, funcionários, novo funcionário, turnos, calendário mensal, semanal e configurações: **28 combinações**. Conferidos limites da página, campos rotulados, disposição dos formulários, largura dos selects e menu móvel com Escape. Dez imagens também inspecionadas visualmente. Nenhuma página apresentou transbordamento horizontal nas combinações verificadas; calendários/tabelas podem ter rolagem interna. Trata-se de emulação de viewport no Chromium desktop, sem certificação de Safari/Firefox ou aparelhos físicos.

| Achado | Causa/reprodução | Correção e evidência |
|---|---|---|
| **UI-01, média: formulários comprimidos** | Em 390/768 px, `.schedule-forms` em pages.css sobrescrevia a coluna única de layout.css, mantendo duas colunas e campos cortados. | `app/static/css/pages.css`: coluna única até 980 px; ocultação do rótulo redundante de contagem no cabeçalho mensal estreito. Asserções de posição/largura passaram. |
| **UI-02, baixa: foco perdido ao selecionar dia** | O select recebia foco antes de concluir a navegação por âncora; o foco terminava no BODY. A data selecionada continuava correta. | `app/static/js/schedules.js`: foco em pageshow/hashchange, no próximo quadro, com preventScroll. Seleção e lista completa passaram com o elemento correto focado. |

Reproduções anteriores à correção e resultado final: `tmp/browser-validation-20261123/`. Duas falhas do próprio executor também foram corrigidas durante sua preparação: navegação para a mesma âncora sem resposta HTTP nova e captura durante rolagem suave. Não foram atribuídas ao produto.

## 5. Regressões e cobertura depois das correções

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

## 6. GitHub e CI

**Origin CORRIGIDO** mediante autorização explícita, com estes comandos:

```powershell
git remote set-url origin https://github.com/mduardo1/EscalaPro-.git
git remote -v
```

Branch local main, HEAD `53af6e7`; main público consultado: `74e787e62646fe6219b00a508c2e80f0b53c63c1`. Ambos têm a árvore `9c73b9127829246aab2073d84fe9f3b08b908c91`: **119 arquivos com blobs idênticos**. Os commits iniciais são distintos. Foi preparada uma cópia em tmp/publication-review, branch portfolio-validation, a partir desse main remoto; nela foram aplicados somente os 138 candidatos do manifesto, preservando esta pasta. Os arquivos são comparados por SHA-256 com a origem já testada antes de aprovar a publicação. Comandos, efeitos e aprovações: [plano de reconciliação](GIT_RECONCILIATION_PLAN.md).

O YAML local usa Ubuntu 24.04, PostgreSQL 18.3, instalação PGDG de clientes 18, precedência no PATH e conferência de pg_dump/pg_restore. Oito etapas, permissões mínimas e falhas obrigatórias, sem continue-on-error. Docker/Linux passou; isso não valida a instalação PGDG no runner Ubuntu.

A consulta atual ao GitHub encontrou apenas o [run antigo 40416904360](https://github.com/mduardo1/EscalaPro-/actions/runs/40416904360), de 26/10, com falha. A correção ainda é local. **Publicação PENDENTE e CI BLOQUEADO** até autorização para commit/push da cópia revisada e novo run bem-sucedido. Não houve commit, push, merge, rebase, force push, PR ou deploy.

## 7. Arquivos, capturas e preservação

Alterações desta continuação: `app/static/css/pages.css`, `app/static/js/schedules.js`, `README.md`, `AUDIT_CURRENT.md`, este relatório, `docs/screenshots/README.md` e `PUBLICATION_MANIFEST.txt`. Adicionados `requirements-browser.txt`, `tests/browser/run_browser_checks.py`, `GIT_RECONCILIATION_PLAN.md` e os dez PNGs listados no [guia de capturas](docs/screenshots/README.md). Origin foi a única escrita autorizada na configuração Git. Os demais diffs recebidos foram preservados; a lista exata dos candidatos está em PUBLICATION_MANIFEST.txt.

**.env e banco principal preservados:** SHA-256 antes/depois sem alteração. A demo fonte não foi modificada pelo executor; alterações ocorreram na cópia browser-run-*.demo.sqlite3. Credenciais e códigos permaneceram privados. O projeto Compose escalapro-browser-regression foi encerrado; consulta final por rótulo não encontrou seus contêineres, redes ou volumes. Outros projetos Docker foram preservados.

Evidências privadas: `tmp/browser-validation-20261123/full-run/browser-results.json`, PDFs baixados, linux.xml, windows.xml, coberturas e baselines. Auditoria de publicação: **138 candidatos, 119 rastreados, zero preparados no índice e zero apontamentos**, incluindo as dez imagens revisadas. Inventário e hashes: `tmp/github-publication-audit.json`; heurísticas e revisão de binários não constituem certificação de ausência de segredos. A consulta de avisos de dependências de 12/11 é histórica, não foi repetida nesta etapa. pip check confirma compatibilidade instalada, não ausência de CVEs.

## 8. Reprodução e próxima ação

Instruções opcionais completas: [guia do navegador](docs/screenshots/README.md). Execuções principais realizadas:

```powershell
.\.venv\Scripts\python.exe tests/browser/run_browser_checks.py --database instance/demo/browser-validation-20261123.demo.sqlite3 --artifacts tmp/browser-validation-20261123/full-run --screenshots docs/screenshots
.\.venv\Scripts\python.exe -m pytest -q -W error --basetemp=tmp/browser-validation-20261123/pytest --cov=app --cov=migrations --cov=scripts --cov-branch --cov-report=json:tmp/browser-validation-20261123/windows-coverage.json --junitxml=tmp/browser-validation-20261123/windows.xml
docker compose --env-file .env.example -f compose.test.yml -p escalapro-browser-regression run --build --name escalapro-browser-regression-tests tests python -m pytest -q -W error --cov=app --cov=migrations --cov=scripts --cov-branch --cov-report=json:tmp/browser-regression-coverage.json --junitxml=tmp/browser-regression.xml
```

**Próxima ação:** revisar o conjunto e autorizar commit e push da branch portfolio-validation já preparada na cópia, conforme o plano. O índice e o diff da cópia são locais; nenhum arquivo foi publicado. Exigir novo CI verde antes de anunciar validação remota no GitHub/LinkedIn. A licença depende de decisão do proprietário. Exclusão física de funcionários/turnos e outros navegadores são evoluções pendentes.

Mantida a **classificação B** até fechar publicação e CI. Produção continua sem aprovação: faltam homologação de infraestrutura, HTTPS, e-mail real, operação, restauração externa e capacidade de carga. Não há evidência de SLA, clientes reais ou certificação de segurança.
