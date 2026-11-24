# EscalaPro — reconciliação segura para publicação

**Atualizado em 24/11/2026. Origin corrigido com autorização explícita. Cópia local de revisão preparada; commit e push ainda não executados.**

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

O índice principal continua vazio e seu HEAD continua `53af6e7`. Os testes aprovados pertencem exatamente aos mesmos bytes de código, não a um commit novo que ainda não existe.

## Etapa 3 — commit e publicação de uma branch

**Exigem outra autorização explícita sobre o conteúdo final.** Primeiro revisar a lista exata e a auditoria de segredos, inclusive o índice da cópia. Não executar os comandos a seguir apenas por constarem neste plano.

```powershell
# Executar dentro da cópia revisada, somente após autorização.
python scripts/audit_publication.py
git diff --cached --check
git diff --cached --stat
# Conferir localmente o diff completo antes de continuar.
git commit -m "Valida interface e prepara capturas do EscalaPro"
git push -u origin portfolio-validation
```

O push publica o código e as capturas dessa branch no repositório público e dispara o workflow de testes. Não envia mudanças diretamente para `main`. Uma falha no CI precisa ser investigada e corrigida antes de solicitar integração. Criar PR, integrar em `main` e fazer deploy são ações separadas, também dependentes de autorização. Não haverá force push.

## Critério de aprovação

O YAML local seleciona clientes PostgreSQL 18 e a suíte é exercitada em Linux/PostgreSQL. A execução GitHub do workflow corrigido só poderá ser marcada como concluída quando houver um run real bem-sucedido no commit publicado. A execução antiga não comprova a correção nova. Esta preparação de portfólio também não aprova uma operação pública em produção.
