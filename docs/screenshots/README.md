# Capturas reais do EscalaPro

**CONCLUÍDO — 24/11/2026.** Dez imagens produzidas pela aplicação real em Chromium 159.0.8154.6/Playwright 1.65.2, com sandbox habilitada e dados inteiramente fictícios. Todas foram inspecionadas visualmente. Os PNGs entregues são capturas diretas, sem montagem ou edição do conteúdo.

## Arquivos e dimensões

| Captura | Viewport | Imagem PNG | Modo |
|---|---|---|---|
| [01-login.png](01-login.png) | 1920 × 1080 | 1920 × 1080 | Campos vazios |
| [02-dashboard.png](02-dashboard.png) | 1920 × 1080 | 1920 × 1516 | Página completa |
| [03-funcionarios.png](03-funcionarios.png) | 1920 × 1080 | 1920 × 1536 | Página completa |
| [04-turnos.png](04-turnos.png) | 1920 × 1080 | 1920 × 1080 | Página completa |
| [05-calendario-mensal.png](05-calendario-mensal.png) | 1920 × 1080 | 1920 × 3471 | Página completa |
| [06-atribuicao-escala.png](06-atribuicao-escala.png) | 1920 × 1080 | 1920 × 1080 | Viewport com formulário e foco |
| [07-calendario-semanal.png](07-calendario-semanal.png) | 1920 × 1080 | 1920 × 4087 | Página completa |
| [08-relatorio-pdf.png](08-relatorio-pdf.png) | 1920 × 1080 | 1920 × 1080 | PDF real baixado, aberto no visualizador |
| [09-versao-tablet.png](09-versao-tablet.png) | 768 × 1024 | 768 × 1024 | Dashboard |
| [10-versao-mobile.png](10-versao-mobile.png) | 390 × 844 | 390 × 844 | Dashboard |

Página completa pode ultrapassar a altura do viewport. Não confundir dimensão do PNG com tamanho da janela. O relatório mensal tem 12 páginas; a imagem mostra o início no visualizador, não todas as páginas simultaneamente. O calendário semanal mostra a semana de 23–29/11/2026.

## Validação

O executor verificou sete páginas nas resoluções **1920 × 1080, 1366 × 768, 768 × 1024 e 390 × 844**, totalizando 28 combinações. Também executou 21 verificações funcionais: contas com mensagens simuladas, isolamento, funcionários, turnos, escalas, conflitos, indisponibilidades, datas, foco, menu, configurações e downloads PDF. Resultado detalhado e limites: [relatório de portfólio](../../PORTFOLIO_READINESS_REPORT.md).

Foram corrigidos os formulários comprimidos no tablet/celular e a perda de foco após navegação pelo dia. A revisão cobre Chromium desktop com viewports emulados; outros motores e aparelhos físicos continuam pendentes.

## Reproduzir sem dados reais

Requer Python 3.14 e as dependências opcionais. Em instalação de desenvolvimento, após as autorizações de instalação/rede aplicáveis:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-browser.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe scripts/seed_demo.py --database instance/demo/minha-validacao.demo.sqlite3 --week 2026-11-16
.\.venv\Scripts\python.exe tests/browser/run_browser_checks.py --database instance/demo/minha-validacao.demo.sqlite3 --artifacts tmp/minha-validacao --screenshots tmp/minha-validacao/screenshots
```

Use um nome novo: o gerador recusa bases existentes. O executor lê as credenciais privadas da demo fonte e cria uma cópia exclusiva; somente essa cópia recebe dados e contas de teste. As mensagens de verificação/reset ficam em memória. Não utiliza .env, banco principal ou perfil pessoal e não envia e-mails reais.

Os comandos acima colocam as novas capturas em tmp para preservar a entrega revisada. Usar `--screenshots docs/screenshots` substitui os PNGs de demonstração, portanto só fazê-lo ao renovar e revisar a galeria. Data, semana atual e horários mudam entre execuções; não se espera identidade binária das novas capturas.

Na auditoria, ferramentas e navegador foram instalados somente em tmp/browser-tools e tmp/browser-browsers; o executor reconhece essas pastas se existirem. Em outra máquina usa a instalação opcional normal. PDFs, logs, bancos e credenciais permanecem fora da galeria pública. Não publicar tmp/ ou instance/.

Antes de publicar, conferir novamente login vazio, ausência de senhas/códigos/tokens, dados fictícios, diff e manifesto. A entrega de imagens não representa publicação no GitHub nem aprovação de produção.
