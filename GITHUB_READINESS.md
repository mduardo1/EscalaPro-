# EscalaPro — preparação do portfólio e auditoria de publicação

**Data:** 18/10/2026. **Estado:** preparação local; nenhum commit, remoto, push ou deploy autorizado/executado. Nenhuma licença do projeto foi escolhida.

## Escopo e resultado

Foram inspecionados os arquivos candidatos efetivos do Git, incluindo arquivos ocultos, documentação, fontes, configuração, migrações, scripts, testes e workflow. O inventário também identifica ambientes, bancos, backups e artefatos privados ignorados. O `.env` foi lido apenas pelo auditor para comparação em memória; não foi carregado como configuração da demo, impresso ou modificado. Registros reais foram consultados somente em modo leitura para verificar integridade e detectar cópias indevidas nos candidatos públicos.

Não existia repositório Git nesta pasta nem no diretório pai. Foi inicializado um repositório **local**, com branch `main`, sem commits, arquivos adicionados ao índice ou remoto. Não há histórico local anterior para sanear. Isso não permite afirmar nada sobre cópias externas ou outros repositórios do proprietário.

O auditor `scripts/audit_publication.py` consulta candidatos, conteúdo do índice e objetos do histórico existente. Ele detecta formatos conhecidos de tokens/chaves, URLs autenticadas não aprovadas de teste, e-mails fora de domínios fictícios, caminhos pessoais de máquina, cabeçalhos de bancos e correspondências com valores privados locais. Seus relatórios nunca incluem valores encontrados. Credenciais claramente fictícias de PostgreSQL, restritas aos testes locais/CI, têm exceções explícitas. Os metadados e contatos de autoria da licença das fontes DejaVu são atribuições públicas de terceiros, preservadas junto às fontes.

Os únicos ajustes de interface foram dois exemplos de e-mail substituídos por `example.com`. Layout, funcionalidades e registros existentes foram preservados.

**Resultado final:** **119 arquivos candidatos**, **nenhum achado pendente** nas verificações executadas, **zero arquivos rastreados ou adicionados ao índice**, **zero commits** e **zero remotos**. A lista exata está em [PUBLICATION_MANIFEST.txt](PUBLICATION_MANIFEST.txt); esse arquivo também integra a lista. Não é uma declaração de segurança absoluta: a verificação depende do conteúdo e do estado do Git no instante auditado.

## Arquivos privados e proteções

- `.env`, variações de ambiente e configurações locais; apenas `.env.example`, com segredos vazios, é elegível.
- `instance/`, bancos SQLite e seus arquivos auxiliares, dumps PostgreSQL, `backups/`, arquivos de restauração e chaves/certificados privados.
- Credenciais fictícias e base demo em `instance/demo/`; nenhuma base binária é publicada. O repositório contém somente o gerador.
- `tmp/`, relatórios de auditoria/testes/cobertura, PDFs, logs, capturas HAR, mensagens de e-mail, exportações CSV/XLSX e arquivos compactados.
- `.venv/`, outros ambientes virtuais, caches Python/Pytest/formatadores, arquivos temporários, build e configurações locais do editor.

`app/schema.sql` e as revisões Alembic são código público necessário. Arquivos `.sql` são ignorados, com exceção explícita de `app/schema.sql`; novos scripts SQL exigem revisão e exceção consciente. O auditor também reconhece assinaturas de dumps disfarçados de texto e recusa valores privados preenchidos no `.env.example`. O `.dockerignore` acompanha as exclusões de dados e artefatos para imagens.

Arquivos já rastreados podem ignorar o `.gitignore`; por isso o auditor examina também blobs do índice e do histórico. Se detectar um segredo real em qualquer commit, **interromper a publicação**, revogar/rotacionar a credencial junto ao provedor e planejar o tratamento do histórico com autorização. Não executar limpeza destrutiva automaticamente.

Foram verificadas explicitamente 11 exclusões, cobrindo `.env`, variante de ambiente, base principal, demo/credenciais, backup, dump SQL, ambiente virtual, relatório e configuração de serviço. As duas exceções públicas, `.env.example` e `app/schema.sql`, permaneceram elegíveis. O inventário privado encontrou artefato com correspondência a valores locais na área ignorada; seu conteúdo não foi reproduzido no relatório público. Nenhum candidato público apresentou essa correspondência. Dependências/caches foram inventariados como artefatos excluídos, sem alegação de auditoria completa do código de terceiros.

## Preservação da base principal

Antes do trabalho foram registrados hashes SHA-256 privados do `.env`, banco principal e backup existente. A verificação final compara esses arquivos byte a byte por seus hashes, sem divulgar os hashes ou seu conteúdo. `PRAGMA integrity_check` e `PRAGMA foreign_key_check` são executados somente leitura. Não houve migração, seed, atualização de senha ou envio no banco real. A demo foi criada do zero, sem copiar ou anonimizar registros existentes.

**Conferência final:** os **3 arquivos privados originais permaneceram inalterados**; integridade SQLite e referências passaram antes e depois. A criação da demo acrescentou apenas seus arquivos próprios ao diretório reservado.

As evidências privadas ficam em `tmp/github-private-baseline.json`, `tmp/github-private-inventory.json` e `tmp/github-publication-audit.json`. Não publicar esses relatórios nem arquivos antigos de `tmp/`; eles podem conter caminhos, registros, mensagens ou capturas de outras auditorias. A comparação de texto não detecta com garantia dados pessoais em imagens/PDFs comprimidos; esses artefatos são excluídos por inteiro.

## Demonstração fictícia

Base criada: `instance/demo/portfolio.demo.sqlite3`, com duas semanas a partir de **12/10/2026**. Para novas bases, a semana atual é o padrão; `--week AAAA-MM-DD` permite datas reproduzíveis.

- Empresa **TechNova Serviços — demonstração fictícia**, com administrador fictício e e-mail em `example.com`.
- **15 funcionários**, com nomes numerados explicitamente fictícios, cargos/setores demo e e-mails `example.com`.
- **3 turnos:** manhã 06h–14h, tarde 14h–22h e noite 22h–06h; intervalo de 30 minutos.
- **150 atribuições**, em duas semanas, com cobertura dos sete dias e virada da meia-noite.
- **3 indisponibilidades** de folga, sem sobreposição com atribuições. Disponibilidade corresponde aos demais períodos livres; o sistema não tem um cadastro separado de disponibilidade positiva.
- Alertas demonstráveis de jornada individual e descanso mínimo, configurados como avisos, sem inserir conflitos bloqueados.

### Instalação e execução no Windows

Na raiz do projeto, reutilize `.venv`. Em instalação nova, execute primeiro `py -3.14 -m venv .venv`.

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
# Para gerar uma base nova (o arquivo entregue já existe localmente):
python scripts/seed_demo.py --database instance/demo/minha-demo.demo.sqlite3
python scripts/run_demo.py --database instance/demo/minha-demo.demo.sqlite3
```

Sem ativação, use `.\.venv\Scripts\python.exe` no lugar de `python`. Acesse **http://127.0.0.1:5001**. Para a base já criada nesta entrega:

```powershell
.\.venv\Scripts\python.exe scripts/run_demo.py --database instance/demo/portfolio.demo.sqlite3
```

Abra localmente `instance/demo/portfolio.demo.credentials.json` no editor para obter as credenciais fictícias. O gerador cria senha aleatória, armazena somente o hash no banco e não imprime a senha; o arquivo de credenciais é privado/ignorado. Não usar essa credencial em outras contas nem mostrar o arquivo em capturas de portfólio.

Os scripts aceitam somente `instance/demo/<nome>.demo.sqlite3`, recusam links simbólicos e bases existentes no seed, exigem marcador de demonstração antes de servir e não acessam o `.env`. Configuração de banco, segredos e SMTP herdados do processo são descartados. E-mails ficam desativados, o servidor escuta apenas em loopback e não usa debug. A chave de sessão muda ao reiniciar, exigindo novo login. Para reiniciar os dados, escolha outro nome; não existe opção destrutiva de reset.

Cadastro/recuperação com envio não operam na demo, por decisão de segurança. Os fluxos normais continuam presentes e são testados com remetentes simulados, sem rede externa. Não apontar `run.py` para o banco principal para produzir capturas da demonstração.

## Testes e reprodução

```powershell
python -m pytest -q -W error -o cache_dir=tmp/pytest-cache --cov=app --cov=migrations --cov=scripts --cov-branch
```

Os testes usam bancos fictícios isolados, com dotenv desativado e remetentes simulados. O PostgreSQL é opcional na execução nativa; sem `TEST_DATABASE_URL`, seus testes são explicitamente ignorados. Para a suíte completa no Linux com PostgreSQL, clientes de backup e Gunicorn:

```powershell
docker compose -f compose.test.yml -p escalapro-tests up --build --abort-on-container-exit --exit-code-from tests
docker compose -f compose.test.yml -p escalapro-tests down
```

Os novos testes verificam caminhos recusados, arquivos existentes preservados, isolamento de configuração, marcador demo, integridade, dados fictícios, alertas, turno noturno, login com CSRF, dashboard/cadastros/escalas, PDF e isolamento entre empresas. O auditor tem testes de exclusão de arquivos privados, vazamento fictício, conteúdo diferente no índice e banco forçadamente rastreado. Os fluxos anteriores de cadastro, confirmação e recuperação continuam cobertos pela regressão.

### Resultados em 18/10/2026

| Ambiente | Testes | Linhas | Ramificações | Combinada |
|---|---|---|---|---|
| Linux Docker, Python 3.14.8 e PostgreSQL 18.3 | **227 aprovados**, nenhum ignorado, 91,95 s | **91,54%** | **83,58%** | **89,85%** |
| Windows, Python 3.14.3, SQLite isolado | **214 aprovados**, 13 ignorados, 92,33 s | **85,34%** | **75,19%** | **83,18%** |

Ambas as execuções utilizaram `-W error`, sem avisos. Os 13 testes PostgreSQL ignorados no Windows foram executados no Linux, incluindo concorrência, transferência de dados, pg_dump/pg_restore e Gunicorn. A medição inclui **app, migrations e scripts**, com 1.985 linhas executáveis e 536 ramificações; esse escopo é maior que o da Fase 2, portanto seus percentuais não são diretamente comparáveis. Não há alegação de 100% de cobertura nem de cobertura da interface em navegador.

Foram acrescentados **19 testes** nesta etapa. Também foram executados compilação Python, Black e `pip check`, sem erros. O Git foi acrescentado somente ao estágio Docker de testes para validar repositórios fictícios; nenhuma dependência Python nova foi instalada nesta etapa.

O servidor `scripts/run_demo.py` foi iniciado em loopback na porta 5011 para verificação adicional: login com CSRF, dashboard, funcionários, turnos, calendário, PDF e prontidão responderam corretamente via HTTP. A verificação não exibiu credenciais nem enviou mensagens. O servidor de verificação e os contêineres descartáveis foram encerrados; a demo pode ser iniciada novamente pelo comando acima. O design foi preservado, sem nova validação visual em navegador.

Evidências privadas: `tmp/portfolio-linux-tests.{txt,xml}`, `tmp/portfolio-windows-tests.{txt,xml}`, `tmp/portfolio-linux-coverage.json` e `tmp/portfolio-windows-coverage.json`. Nenhuma execução usa o banco principal como banco de teste.

## Arquivos desta etapa

- Criados: `GITHUB_READINESS.md`, `PUBLICATION_MANIFEST.txt`, `scripts/seed_demo.py`, `scripts/run_demo.py`, `scripts/audit_publication.py`, `tests/test_demo.py` e `tests/test_publication_audit.py`.
- Atualizados: `.gitignore`, `.dockerignore`, `.env.example`, `README.md`, `Dockerfile`, `app/templates/auth/login.html` e `app/templates/employees/form.html`.
- Criados somente localmente e excluídos: metadados Git sem commit, base/credenciais demo e evidências em `tmp/`. Os arquivos originais de dados e credenciais foram preservados.

## Conteúdo do primeiro commit

**Lista integral:** [PUBLICATION_MANIFEST.txt](PUBLICATION_MANIFEST.txt). O relatório privado `tmp/github-publication-audit.json` registra o hash de cada candidato e os achados da execução. O manifesto inclui código, assets com licença, testes, scripts, arquivos de dependências/configuração pública, documentação e CI. Não inclui banco, credenciais demo, `.env`, relatórios privados ou cache.

Nenhum `git add` ou commit foi executado no repositório principal. Testes do auditor criam repositórios temporários fictícios e exercitam o índice apenas neles, sem commits ou remotos.

### Comandos recomendados — somente após autorização

```powershell
python scripts/audit_publication.py --manifest
if ($LASTEXITCODE -ne 0) { throw 'Auditoria recusada: não continuar.' }
git status --short
# Revisar PUBLICATION_MANIFEST.txt e os arquivos listados antes de adicionar.
git add --pathspec-from-file=PUBLICATION_MANIFEST.txt
python scripts/audit_publication.py
if ($LASTEXITCODE -ne 0) { throw 'Índice recusado: não criar commit.' }
git diff --cached --check
git diff --cached --stat
# Revisar o diff completo localmente, sem compartilhar valores privados.
git diff --cached
git commit -m "Prepara EscalaPro para portfolio com demonstracao isolada"
```

Não há comando de push nem criação de remoto nesta entrega. Configure identidade Git conscientemente; para privacidade, avalie um endereço noreply da sua conta GitHub antes de criar commits. Escolha de licença depende de autorização explícita.

## Riscos e próximos passos

- Repetir a auditoria imediatamente antes de adicionar arquivos e antes do commit: alterações posteriores invalidam a lista e os hashes.
- Ferramentas heurísticas podem deixar passar segredos desconhecidos ou dados pessoais em formatos não textuais. Revisar manualmente diffs e assets; não publicar capturas reais.
- Um arquivo privado renomeado com extensão pública ainda precisa ser detectado pelo conteúdo/revisão. Não utilizar `git add -f` para contornar proteções.
- Nenhum histórico local anterior existia. Histórico externo, credenciais já compartilhadas e serviços de terceiros não foram auditados.
- Não foi realizada auditoria completa de CVEs nem escolhida licença; CI GitHub ainda não foi executada remotamente.
- Os bloqueios de produção de [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) permanecem aplicáveis: homologação Render/proxy/TLS, e-mail real autorizado, backups externos/monitoramento e transferência real de dados.

**Publicação e primeiro commit aguardam autorização do proprietário.**
