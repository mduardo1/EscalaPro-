# Auditoria técnica — EscalaPro

> Relatório histórico da versão anterior ao cadastro público. A implementação posterior de cadastro, recuperação de senha, migrações e isolamento entre empresas está documentada em [ACCOUNT_SETUP.md](ACCOUNT_SETUP.md); consulte o README para os resultados atuais.

**Período:** 16–17/10/2026, America/Sao_Paulo.  
**Situação final:** **Aprovado com ressalvas** para demonstração local, após a atualização aditiva do banco descrita abaixo.

A auditoria inspecionou arquitetura, configuração, rotas, modelos, serviços, schema, templates, JavaScript, CSS, dependências e testes. As correções foram pontuais e preservaram a identidade visual. O `.env` não foi lido pela auditoria; seu carregamento foi desativado nos testes. Nenhuma consulta de auditoria foi feita ao banco principal. Não houve commit ou push.

## Resultado consolidado

| Indicador | Resultado |
|---|---:|
| Testes da suíte original | 47 aprovados |
| Testes adicionais nesta auditoria | 43 |
| Execução final | 90 aprovados |
| Falhas / erros na execução final | 0 / 0 |
| Testes automatizados ignorados ou não executados | 0 |
| Linhas Python exercitadas | 686 de 702 — 97,72% |
| Ramificações Python exercitadas | 131 de 146 — 89,73% |
| Cobertura combinada | 96,34% |
| Dependências | `pip check`: nenhuma incompatibilidade |
| Formatação / sintaxe | Black, compileall e `node --check`: aprovados |
| Revisão visual das telas / execução de JS em navegador | Não executadas: nenhum navegador conectado |

O primeiro comando de testes encontrou bloqueios de permissão do Windows na recriação de `tmp/pytest`; isso impediu a preparação de 44 testes e não foi atribuído ao produto. A repetição com a permissão necessária passou nos 47 testes originais. Em seguida, os testes adicionais reproduziram os defeitos antes das correções, e os testes relacionados foram repetidos após cada grupo de ajustes.

Artefatos locais, ignorados pelo Git:

- `tmp/audit-tests.xml`: resultados JUnit da execução completa.
- `tmp/audit-coverage.json`: contadores e linhas/ramificações não exercitadas.
- `tmp/audit-coverage/index.html`: relatório navegável de cobertura.
- `tmp/audit-pdf/`: PDFs fictícios e páginas renderizadas para inspeção.

Cobertura não significa ausência de defeitos: não inclui a execução de HTML/CSS/JavaScript e ainda há caminhos Python não exercitados, discriminados no relatório HTML. Não foram simuladas falhas de disco, carga sustentada ou múltiplas máquinas.

## Problemas confirmados e corrigidos

Todos os testes citados abaixo passaram na execução final. Os nomes indicam funções em `tests/test_audit_regressions.py`, salvo indicação contrária.

| ID | Gravidade | Arquivos afetados | Causa e comportamento anterior | Correção e evidência |
|---|---|---|---|---|
| A01 | Alta | `app/routes/auth.py`, `app/models/user.py`, `app/schema.sql` | O logout apagava o cookie do cliente, mas uma cópia anterior ainda autenticava e retornava HTTP 200 no dashboard. | Sessões aleatórias registradas por hash no servidor e revogadas no logout. `test_logged_out_cookie_cannot_be_replayed`; verificação também por HTTP real em `test_http_smoke.py`. |
| A02 | Média | `app/config.py`, `app/models/user.py` | A renovação do cookie permitia prolongar a autenticação além do limite de 8 horas descrito no README. | Renovação automática desativada e vencimento absoluto validado no servidor. `test_session_has_absolute_eight_hour_expiration`: acesso em 7h permitido, em 9h rejeitado. |
| A03 | Alta | `app/__init__.py` | O bloqueio de debug em produção reconhecia apenas alguns textos; valores que o Flask interpreta como verdadeiros, como `2` e `enabled`, passavam. `DEBUG=True` explícito também passava. | Verificação pela mesma interpretação do Flask, além de `app.debug`. `test_all_flask_truthy_debug_flags_rejected_in_production` e `test_explicit_debug_rejected_in_production`. |
| A04 | Média | `app/__init__.py`, `app/routes/employees.py`, `shifts.py`, `schedules.py` | IDs maiores que o inteiro de 64 bits alcançavam o SQLite e causavam `OverflowError`, resultando em erro 500. | Conversor de rotas com tamanho e intervalo válidos para SQLite. `test_out_of_range_path_id_is_404`, parametrizado para três módulos. |
| A05 | Média | `app/services/validation.py` | Um inteiro de formulário com centenas de dígitos era convertido em float por `math.isfinite` antes da verificação de limites, causando erro 500. | Verificação do intervalo antes da conversão implícita e tratamento explícito de conversões inválidas. `test_huge_form_integer_is_validation_error`: HTTP 422 sem gravação. |
| A06 | Média | `app/routes/dashboard.py` | O total semanal somava valores diários já arredondados. Três turnos de 20 minutos apareciam como 0,9h. | Soma das durações reais antes do arredondamento final. `test_dashboard_total_uses_unrounded_hours`: total de 1h; métricas completas comparadas com o banco em `test_audit_modules.py`. |
| A07 | Média | `app/services/schedule_service.py` | O salvamento calculava alertas apenas para a semana da data inicial. Uma noite de domingo podia exceder a jornada da próxima semana; uma inclusão no domingo podia reduzir o descanso antes de uma escala de segunda sem notificação imediata. | Verificação das semanas tocadas e das atribuições seguintes dentro do descanso configurado, com identificação da semana nas mensagens. `test_sunday_night_warns_about_next_week_limit` e `test_sunday_assignment_warns_about_rest_before_monday`. |
| A08 | Média | `app/routes/schedules.py` | Todos os alertas eram colocados no cookie de sessão. Uma simulação com 100 avisos de nomes distintos gerou 8.355 bytes serializados, acima do limite usual de cookie. | Prévia limitada do primeiro alerta e contagem dos demais; detalhes continuam no calendário. `test_many_alerts_do_not_overflow_session_cookie`: quantidade limitada e cabeçalhos menores que 4.093 bytes. |
| A09 | Média | `app/templates/schedules/index.html`, `app/routes/schedules.py`, `app/static/js/schedules.js` | “Atribuir” apenas alterava a data do formulário atual. Durante uma edição, o POST continuava apontando para a atribuição existente, com risco de sobrescrevê-la. | Link para criação com data validada no servidor, independente do modo de edição e sem depender do JS para a navegação. `test_add_calendar_link_during_edit_opens_new_assignment`. |
| A10 | Baixa | `app/routes/schedules.py`, `app/services/schedule_service.py` | Remover uma indisponibilidade inexistente retornava uma mensagem de sucesso. | Verificação do número de registros removidos; ausência retorna HTTP 404. `test_removing_missing_unavailability_is_404`. |
| A11 | Média | `app/services/pdf_service.py`, `app/assets/fonts/` | A fonte padrão do PDF não preservava caracteres aceitos no cadastro, como `ř` e `Ł`. | DejaVu Sans regular/negrito incorporadas, com licença e procedência registradas. `test_pdf_special_characters_round_trip` em `test_audit_modules.py`; extração e inspeção visual confirmadas. |
| A12 | Baixa | `app/services/validation.py`, `schedule_service.py`, `app/routes/schedules.py`, `app/templates/schedules/index.html` | Nas bordas do intervalo permitido, a segunda-feira da primeira semana caía em 1999 e links da última semana apontavam para 2101, gerando erros 400. | Âncora da primeira semana aceita sem ampliar as datas permitidas para atribuições; navegação e ações fora dos limites ficam indisponíveis. `test_calendar_date_limits_do_not_generate_broken_week_links`, com mínimo e máximo. |
| A13 | Baixa | `app/routes/schedules.py`, `app/templates/schedules/index.html` | Uma indisponibilidade inválida apagava os valores digitados ao reapresentar o formulário. | Valores e seleção do funcionário preservados com a mensagem de validação. `test_invalid_unavailability_keeps_entered_values`. |
| A14 | Média | `app/services/schedule_service.py` | Após editar os horários de um turno, o snapshot anterior podia deixar de se sobrepor à nova definição. Reatribuir o mesmo funcionário/data/turno ultrapassava a validação de horários e falhava com `IntegrityError`/HTTP 500 pela restrição UNIQUE existente. | A restrição de duplicidade é conferida dentro da transação antes da escrita, sem remover o snapshot. `test_same_shift_reassignment_after_time_change_is_validation_error`: HTTP 422 e registro original preservado. |

Nenhum problema crítico foi confirmado nos cenários executados. Os problemas de gravidade alta identificados foram corrigidos e possuem regressões automatizadas.

## Verificação por módulo

| Módulo | Cenários efetivamente executados |
|---|---|
| Autenticação | Credencial válida, senha errada, conta inexistente, erro genérico, SQL Injection no login, logout, cookie alterado, reutilização após logout, sessões independentes, expiração com relógio simulado, hash scrypt, limitação de tentativas e desbloqueio após a janela. |
| Autorização e CSRF | GETs administrativos e todos os endpoints de escrita testados sem autenticação; ausência de CSRF, token adulterado, token de outro cliente e token vencido. Tokens válidos de uma sessão anônima não concedem acesso administrativo. |
| Funcionários | Cadastro, edição, campos obrigatórios, e-mail inválido/opcional, números inválidos, pesquisa por nome/cargo/setor, curingas literais, XSS, persistência, desativação, reativação e preservação do histórico. Cadastros duplicados foram permitidos conforme o modelo atual. |
| Turnos | Cadastro e edição, duração diurna/noturna, fim à meia-noite, rejeição de início/fim iguais, horários inválidos, intervalo negativo/maior que a duração, cor inválida e duplicados permitidos. Tentativa de apagar um turno referenciado pelo SQL foi bloqueada pela chave estrangeira e revertida. |
| Escalas | Inclusão válida, sobreposição, turnos adjacentes, pessoas diferentes no mesmo horário, noite e continuação no dia seguinte, indisponibilidade, funcionário inativo, edição e rollback em edição conflitante, remoção, semanas e virada de ano, limites de datas, jornada e descanso configuráveis. |
| Folgas | Registro manual de indisponibilidade de um dia, bloqueio nesse período e atribuições válidas antes/depois; não existe geração automática de folgas no MVP. |
| Dashboard | Valores comparados com o SQLite: ativos, turnos, atribuições, alertas, horas líquidas, série diária e próximos turnos, incluindo um turno em andamento e a exclusão de registros fora do horizonte. |
| SQLite | Chaves estrangeiras habilitadas, integridade referencial, `integrity_check`, `foreign_key_check`, conexões encerradas, rollback, inicialização aditiva do schema anterior e duas atribuições simultâneas: uma aceita e uma rejeitada por conflito. |
| PDF | Arquivo válido, conteúdo, empresa, período, datas de início/fim noturnas, acentos e caracteres estendidos, XML literal escapado, vazio, 80 funcionários com campos longos, cabeçalhos repetidos e paginação. |
| HTTP local | Servidor WSGI em `127.0.0.1` com porta temporária: home, proteção do dashboard, login com cookie/CSRF, páginas administrativas, download PDF, logout e rejeição da cópia do cookie antigo. Servidor encerrado ao terminar o teste. |

## Segurança e limites da conclusão

Foram exercitados hash de senha, revogação de sessão, vencimento, cookies HttpOnly/SameSite/Secure, CSRF, autorização, limite de tentativas, SQL parametrizado, escape HTML, limite de requisição e respostas de erro sem traceback ou detalhes internos. Os flags de cookie de produção foram conferidos no `Set-Cookie` de uma requisição HTTPS simulada pelo cliente Flask. HSTS, CSP, anti-frame e `no-store` também possuem verificação de configuração/resposta.

Os testes usaram exclusivamente dados fictícios, bancos temporários e endpoints locais. A leitura de documentação e o download da fonte livre não envolveram testes contra serviços externos. A fonte veio da distribuição oficial no GitHub, após falha de certificado no primeiro servidor; a validação TLS foi mantida e o checksum oficial foi conferido. Consulte `app/assets/fonts/README.md` e a [licença oficial](https://dejavu-fonts.github.io/License.html).

Esta conclusão não certifica implantação pública, infraestrutura HTTPS real ou ausência de CVEs nas dependências. `pip check` verifica consistência de pacotes, não vulnerabilidades conhecidas. A aplicação continua representando uma única empresa por instalação, sem isolamento entre clientes, recuperação de senha, trilha de auditoria ou perfis distintos. O limitador de login continua sendo por combinação de endereço/e-mail, não uma proteção completa contra ataques distribuídos.

O schema adicionou somente `auth_sessions` e seu índice. O token em claro existe no cookie assinado; o banco armazena seu hash. Uma sessão ainda ativa exige proteção do cookie e HTTPS na implantação. O logout revoga somente a sessão corrente.

## Interface e PDF visual

**Telas testadas visualmente: nenhuma.** A ferramenta retornou uma lista vazia de navegadores. Home, login, dashboard, funcionários, turnos, escalas e configurações foram exercitados por HTTP e renderização de templates. Isso não comprova alinhamento, responsividade ou execução dos botões JavaScript em um navegador. Os quatro arquivos JS passaram na verificação de sintaxe; essa verificação também não substitui um teste de interação.

A paleta e a tipografia web não foram alteradas. Foram inspecionadas as definições existentes de cores, componentes, foco, movimento reduzido e breakpoints, mas textos cortados, sobreposições, navegação por teclado e funcionamento do menu móvel ainda exigem revisão em navegador desktop/celular.

Para os PDFs, a verificação visual foi executada: relatório de caracteres especiais (1 página), relatório vazio (1 página) e relatório de estresse com 80 nomes/setores longos (21 páginas). As 23 páginas foram renderizadas. Foram inspecionados visualmente os dois relatórios de uma página e as páginas 1, 11 e 21 do relatório longo, sem cortes ou sobreposições observadas. Todos os blocos de texto das 23 páginas ficaram dentro dos limites físicos das páginas na conferência programática. A fonte incorporada não cobre CJK e emojis; não há promessa de suporte a todo Unicode.

## Regras existentes que não foram ampliadas

- A pesquisa unificada filtra também por texto do setor; não existe seletor exclusivo de setor.
- Funcionários/turnos não têm regra de unicidade de cadastro. Não foi inventada uma restrição que pudesse impedir homônimos ou apagar registros existentes.
- Não há ação de excluir/desativar turnos na interface. A integridade de referências foi testada sem adicionar essa funcionalidade.
- Folgas são cadastradas manualmente. Não há algoritmo automático de distribuição.
- Turnos de 24h, múltiplos fusos e transições de horário de verão continuam fora do modelo temporal documentado. Intervalos sem horário próprio continuam sendo rateados proporcionalmente nas bordas de dia/semana.

## Aplicação das correções ao ambiente existente

Nenhum comando desta auditoria inicializou ou alterou o banco principal, e as credenciais locais não foram usadas nos testes. Para aplicar a tabela de sessões ao seu ambiente:

```powershell
# Pare o servidor atual com Ctrl+C, na janela em que ele está rodando.
.\.venv\Scripts\python.exe -m flask --app run init-db
.\.venv\Scripts\python.exe run.py
```

O `init-db` foi testado sobre um schema sem `auth_sessions`, preservando usuários, funcionários, turnos e atribuições. Faça login novamente após reiniciar. Não é necessário recriar o administrador. Até executar essa atualização, o código novo de autenticação pode responder que o banco está indisponível por falta da tabela de sessões; um processo antigo ainda aberto continua executando o código carregado anteriormente.

Para repetir a auditoria automatizada:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -v --cov=app --cov-branch --cov-report=term-missing
```

**Ressalvas finais:** aplicação da atualização ao banco existente e reinício são etapas locais pendentes; revisão visual e de interação em navegador desktop/celular não foi executada. A aprovação é para demonstração local com essas ressalvas, não para operação pública em produção.
