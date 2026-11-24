# EscalaPro — reconciliação segura para publicação

**Atualizado em 24/11/2026. Reconciliação e publicação da branch concluídas com autorização. CI remoto aprovado; PR/integração em main e deploy não realizados.**

## Evidência atual

- Branch local: `main`, commit `53af6e7`.
- Origin corrigido e conferido: `https://github.com/mduardo1/EscalaPro-.git` (fetch e push).
- Repositório pretendido e acessível: `https://github.com/mduardo1/EscalaPro-`.
- `main` remoto consultado pela API: `74e787e62646fe6219b00a508c2e80f0b53c63c1`.
- Comparação dos blobs: **119 arquivos em cada base, todos com conteúdo idêntico**, sem arquivos exclusivos. Os commits são diferentes; isso não exige mesclar históricos sem parentesco para publicar os novos arquivos.
- A pasta principal contém alterações ainda não registradas. Não executar reset, stash, merge ou rebase nela para preparar a publicação.

## Etapa 1 — corrigir somente a URL local de origin

**CORRIGIDO com autorização explícita.** O comando abaixo foi executado e a URL foi conferida. A alteração ficou restrita à configuração local; nenhum arquivo foi enviado e nenhum branch ou commit foi alterado.

```powershell
git remote set-url origin https://github.com/mduardo1/EscalaPro-.git
git remote -v
```

## Etapa 2 — preparar uma cópia com o histórico remoto

A preparação local foi executada sem alterar o repositório principal nem escrever no GitHub. A leitura de rede via clone foi autorizada. Comandos usados:

```powershell
git clone --single-branch --branch main https://github.com/mduardo1/EscalaPro-.git tmp/publication-review
git -C tmp/publication-review switch -c portfolio-validation
```

Usar uma pasta nova; se existir, escolher outro nome. Copiar somente os caminhos aprovados de `PUBLICATION_MANIFEST.txt`, mantendo caminhos relativos. Não copiar `.git`, `.env`, `instance/`, `.venv/`, bancos, credenciais ou artefatos de `tmp/`. Não apagar arquivos da cópia nem substituir a pasta principal. Comparar `main` remoto novamente antes de aplicar, pois o estado pode mudar após esta análise.

Na cópia, comparar todos os arquivos com a origem revisada, conferir o diff e o auditor. Arquivos com bytes idênticos aos já testados não exigem repetir a mesma suíte sem nova alteração; qualquer ajuste de código exige nova validação apropriada. Esse procedimento parte do histórico correto e preserva a pasta principal. Não é necessário `--allow-unrelated-histories` nem force push.

Os 138 arquivos do manifesto foram copiados, comparados por SHA-256 e preparados no índice **apenas da cópia** para tornar o diff final revisável. Comandos locais de revisão:

```powershell
git -C tmp/publication-review add --pathspec-from-file=PUBLICATION_MANIFEST.txt
git -C tmp/publication-review diff --cached --check
git -C tmp/publication-review diff --cached --stat
```

O índice principal continua vazio e seu HEAD continua `53af6e7`. Os bytes de código comparados e testados foram registrados no commit `bfde09cac0257ca0037f72539c6fe379ece1f0ee` da cópia.

## Etapa 3 — commit e publicação de uma branch

**CONCLUÍDO com autorização explícita do proprietário nesta sessão.** A auditoria da cópia conferiu 138 candidatos, 39 caminhos preparados no índice e zero apontamentos. O commit e o push abaixo foram executados após a aprovação do conteúdo final. Os comandos são registro do procedimento, não instrução para repeti-los.

```powershell
# Executados dentro da cópia, após autorização.
python scripts/audit_publication.py
git diff --cached --check
git diff --cached --stat
# Conferir localmente o diff completo antes de continuar.
git commit -m "Valida interface e prepara capturas do EscalaPro"
git push -u origin portfolio-validation
```

O push publicou 39 arquivos alterados/adicionados e disparou o workflow, sem mudar `main`. A [branch pública](https://github.com/mduardo1/EscalaPro-/tree/portfolio-validation) contém código, documentação e dez capturas reais. Uma atualização documental na mesma branch registra a evidência remota. Criar PR, integrar em `main` e fazer deploy são ações separadas, dependentes de autorização. Não houve force push.

## Critério de aprovação

O [run 45399188201](https://github.com/mduardo1/EscalaPro-/actions/runs/45399188201) passou no commit `bfde09c`: **278 testes aprovados, zero ignorados**, em 50,70 s de pytest, clientes PostgreSQL **18.7** selecionados, servidor **18.3**, pip check e Gunicorn aprovados no Ubuntu 24.04. A cobertura remota se restringe a `app` (93% combinada arredondada); não substitui a cobertura local de escopo mais amplo. A execução antiga com falha permanece histórica. Esta preparação de portfólio não aprova uma operação pública em produção.
