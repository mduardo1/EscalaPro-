# Cadastro administrativo, verificação por e-mail e empresas

> **Atualização Fase 2:** o SMTP local e os fluxos abaixo foram preservados. PostgreSQL, API HTTPS e outbox durável agora estão disponíveis; configuração e procedimentos atuais em [DEPLOYMENT.md](DEPLOYMENT.md). As notas de fila em memória e resultados anteriores abaixo descrevem a etapa original/local. Nenhuma migração foi aplicada ao banco principal nesta fase.

Implementação de 17/10/2026, integrada à arquitetura Flask existente, sem novas dependências de produção.

## Funcionalidades e regras

- Cadastro com nome, empresa, e-mail, senha e confirmação. Senhas novas exigem 12–128 caracteres, maiúscula, minúscula, número e símbolo.
- A solicitação fica pendente. Usuário e empresa só são criados após confirmar o e-mail. O cadastro de um funcionário da equipe não cria uma identidade de acesso.
- Código de seis dígitos com `secrets`, validade de 10 minutos, até 5 tentativas e reenvio após 60 segundos. Reenvios e novas solicitações invalidam os códigos anteriores da mesma finalidade.
- O banco persiste HMAC-SHA256 do código, vinculado ao identificador e à finalidade, com a chave externa da aplicação. Senhas ficam em hash scrypt. Códigos e senhas não são registrados em texto puro no SQLite ou nos logs.
- Recuperação por código seguida de uma autorização aleatória, com uso único e validade de 10 minutos para escolher a nova senha. A alteração revoga todas as sessões antigas da conta.
- Cada conta pública cria uma empresa própria. Nomes iguais não compartilham dados. O identificador da empresa vem da conta autenticada, nunca de um formulário.
- Login com atalhos destacados para cadastro e recuperação. Formulários com mostrar/ocultar senha, indicador de envio, validação nativa acessível e mensagens de erro do servidor.
- E-mails SMTP em `multipart/alternative`, com texto simples e HTML na identidade do EscalaPro, sem imagens externas ou códigos nos logs.
- Funcionários, turnos, escalas, indisponibilidades, configurações, alertas, dashboard e PDF respeitam a empresa. Gatilhos SQLite também rejeitam vínculos entre empresas.
- Um e-mail já existente não cria outra conta, não muda senha e não altera a empresa original. As respostas públicas são neutras para evitar enumeração; o dono pode entrar ou recuperar sua senha.

## Migrar uma instalação existente

Pare todas as instâncias antigas do servidor antes de atualizar. O código antigo não conhece os novos campos de empresa.

```powershell
.\.venv\Scripts\python.exe -m flask --app run migrate-db
.\.venv\Scripts\python.exe run.py
```

`migrate-db` cria um backup SQLite consistente na pasta `backups`, ao lado do arquivo de banco existente, e aplica a migração aditiva em transação. Vincula os usuários, funcionários, turnos, escalas e indisponibilidades anteriores à empresa original, preservando IDs, horários, histórico e hashes de senha. Os administradores existentes permanecem verificados.

As preferências anteriores são copiadas para `company_settings`. A tabela `settings` é preservada como legado; as operações da aplicação passam a usar preferências por empresa. A versão aplicada fica em `schema_migrations`. Repetir o comando não duplica dados. Referências inválidas cancelam e revertem a migração.

O banco principal não foi migrado durante a implementação; preservação, backup, idempotência e rollback foram testados em bancos fictícios. O `.env` real não foi alterado. Não é necessário recriar o administrador existente.

Na revisão posterior da interface, o schema do banco principal foi consultado em modo somente leitura: a versão 1 já estava aplicada. Não foi necessário executar outra migração ou alterar registros nessa revisão.

Em instalação nova, `init-db` também inicializa o schema e aplica a migração. `create-admin` permanece como provisionamento local confiável da empresa original, usando as credenciais do ambiente; ele não é o fluxo de cadastro público. Backups contêm dados do banco, devem continuar protegidos e não devem ser publicados.

## Configurar SMTP

Preencha no seu `.env` com os dados e o remetente autorizado do seu provedor:

```dotenv
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM=
SMTP_STARTTLS=true
SMTP_SSL=false
```

Para SSL direto, utilize a porta indicada pelo provedor, normalmente `465`, com `SMTP_SSL=true` e `SMTP_STARTTLS=false`. Para STARTTLS, normalmente `587`, use a configuração acima. Os modos são exclusivos. Certificados são validados; em produção, SMTP configurado exige TLS. Credenciais vazias só servem se o servidor escolhido aceitar envio sem autenticação.

`SMTP_FROM` deve ser um endereço de remetente aceito pelo provedor. Se ele exigir uma credencial de aplicativo, siga suas instruções. Não inclua credenciais em código, screenshots, commits ou relatórios. Reinicie o processo após alterar as variáveis.

`SECRET_KEY` continua forte, obrigatória e estável. Não a troque para configurar o SMTP: sua rotação invalida cookies e códigos pendentes. Em produção, use HTTPS, `APP_ENV=production` e `FLASK_DEBUG=0`.

Sem host/remetente configurados, cadastro e recuperação respondem com indisponibilidade. O administrador existente continua podendo entrar depois da migração. Não há envio de código pelo console ou credenciais padrão.

## Testar cadastro e recuperação

1. Configure SMTP, migre e abra `http://127.0.0.1:5000`.
2. Clique em **Criar conta gratuitamente**, informe nome/empresa e utilize um endereço seu que possa receber mensagens.
3. Antes de confirmar, o login não libera a área administrativa. Digite o código recebido na confirmação; sua validade é de 10 minutos.
4. Aguarde 60 segundos para reenviar, respeitando também os limites de solicitações. Um reenvio invalida o código anterior.
5. Após confirmar, entre. A equipe, os turnos e as escalas dessa empresa começam vazios.
6. Use **Esqueci minha senha** após sair ou em outro navegador. Confirme o código e escolha a nova senha. Todas as sessões antigas dessa conta serão encerradas; as de outras contas não são afetadas.

Um cadastro duplicado mantém a mesma experiência neutra de confirmação e preserva as credenciais existentes. Recuperação para e-mail desconhecido mostra a mesma resposta pública, sem enviar mensagem ou criar conta.

Para testes automatizados, sem envio real:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
# Com requirements-dev.txt instalado:
.\.venv\Scripts\python.exe -m pytest -v --cov=app --cov-branch --cov-report=term-missing
```

O carregamento do `.env` é desativado nos testes. E-mails fictícios são capturados somente em memória, e os transportes SMTP/SSL são simulados. Foram exercitados cadastro, duplicidade, validações, códigos corretos/incorretos/expirados/reutilizados, reenvio e limites, login antes/depois da confirmação, recuperação, revogação em vários dispositivos, consumo concorrente, migração e acesso indevido entre empresas. Há integração HTTP local do cadastro, confirmação e login.

Os testes anteriores foram preservados e adaptados para informar explicitamente a identidade da empresa em chamadas internas. Os modelos falham sem esse contexto; não há uma empresa padrão automática nas operações administrativas. Os resultados atuais ficam em `tmp/login-fix-tests.xml`, `tmp/login-fix-tests-run.txt` e `tmp/login-fix-coverage.json`, ignorados pelo Git. Os arquivos `tmp/accounts-*` registram a etapa anterior.

Resultado após a revisão do login em 17/10/2026: **147 testes aprovados**, sem avisos, executados com `-W error`. Cobertura Python: **96,23% das linhas**, **90,23% das ramificações** e **95,11% combinada**. `pip check`, compilação dos módulos e verificação de sintaxe do JavaScript concluídos sem erros. Nenhuma nova dependência de produção foi instalada.

Não havia navegador conectado à ferramenta: responsividade visual, foco e execução do contador ainda precisam de conferência manual em desktop/celular. A sintaxe do JavaScript foi verificada. Nenhum e-mail real foi enviado; a chegada à caixa de entrada depende da configuração e do provedor.

## Quando os links não aparecem no login

Na investigação, `http://127.0.0.1:5000/login` respondeu sem os links de cadastro e recuperação, enquanto a factory carregada com o código atual respondeu com ambos e todas as rotas registradas. Foram encontrados três processos servidores iniciados pelo Python do ambiente virtual deste projeto, escutando a mesma porta. Processos antigos mantêm os módulos carregados e podem manter templates em cache.

Encerre as instâncias anteriores com `Ctrl+C` nos terminais correspondentes e inicie uma única instância na raiz do projeto:

```powershell
.\.venv\Scripts\python.exe run.py
```

O comando acima agora verifica se a porta 5000 já responde e interrompe a inicialização com uma mensagem clara se houver outro servidor. A checagem ajuda a evitar a repetição do problema; não substitui o gerenciamento de processos em produção. O comando direto `flask run` não passa por essa checagem.

O login deve exibir **Entrar na plataforma**, **Esqueceu sua senha?** e **Criar conta gratuitamente**, além de **Ainda não possui uma conta?**. Os links usam `url_for()` e não dependem de JavaScript. Recarregue a página após reiniciar.

Os testes da correção incluem os links e formulários renderizados, rotas registradas, conteúdo HTML/texto dos e-mails, leitura de SMTP de um `.env` fictício, prevenção de segunda instância pelo comando local e cadastro/recuperação pela pilha HTTP com CSRF. Evidências em `tmp/login-fix-tests.xml`, `tmp/login-fix-tests-run.txt` e `tmp/login-fix-coverage.json`. Verifique manualmente os estados de envio, mostrar/ocultar senha, navegação pelo teclado, desktop/celular e a renderização da mensagem no cliente de e-mail após autorizar um envio real.

Além dos testes isolados, as instâncias antigas deste projeto foram encerradas e a versão atual foi iniciada na porta 5000, com debug desativado. A resposta HTTP do login passou a incluir ambos os links; o comando recusou uma segunda execução, e foi observado um único processo escutando a porta. As páginas públicas e os redirecionamentos foram conferidos por GET, com resultado em `tmp/login-fix-runtime.json`. O SMTP real foi conferido apenas quanto à presença da configuração e ao modo TLS, sem divulgar valores ou enviar e-mails. A revisão não alterou o `.env` ou os dados do banco.

## Limites operacionais

| Controle | Limite atual |
|---|---|
| Login | 5 falhas por IP/e-mail em 15 minutos; 30 solicitações por IP em 15 minutos |
| Cadastro | 5 solicitações por IP em uma hora; 3 por e-mail em 15 minutos |
| Recuperação | 10 solicitações por IP e 3 por e-mail em 15 minutos |
| Reenvio | Intervalo de 60 segundos; 10 solicitações por IP e 3 por e-mail em 15 minutos |
| Validação | 5 erros por código; 20 solicitações por IP e por e-mail em 15 minutos |
| Autorização para nova senha | 10 minutos, uso único, vinculada à sessão do navegador |

Os limites são persistidos e atualizados atomicamente no SQLite; seus identificadores ficam em hash. É usado o endereço da conexão. Uma implantação atrás de proxy precisa de configuração confiável, sem aceitar diretamente cabeçalhos de endereço fornecidos pelo cliente.

O SMTP roda fora da requisição, em fila limitada em memória, para reduzir diferenças de tempo na recuperação de contas existentes e inexistentes. Há dois trabalhadores e até 32 envios em andamento/espera por processo; timeout de transporte de 10 segundos. A fila não é durável: reiniciar o processo ou perder a conexão pode perder um envio pendente. O usuário pode reenviar após o intervalo. Logs operacionais são genéricos e omitem destinatário, código, senha e conteúdo SMTP. Uma implantação que exija entrega garantida precisa evoluir para fila durável e monitoramento.

Solicitações com mais de 24 horas são removidas ao iniciar uma nova. Os códigos expiram antes disso. Hashes de senha pendentes são apagados ao consumir ou substituir o cadastro. A caixa de e-mail passa a ser parte do controle de acesso e deve ser protegida.

O isolamento é lógico em banco compartilhado e ainda exige revisão de implantação e carga antes de operação pública. Não foram adicionados convites de equipe, compartilhamento de empresas por nome, perfis de funcionário, CAPTCHA, autenticação multifator ou cobrança.

Referências: [recuperação de senha — OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) e [SMTP/TLS — Python 3.14](https://docs.python.org/3.14/library/smtplib.html).

## Arquivos principais

- Novos: `app/migrations.py`, `app/tenant.py`, `app/models/company.py`, `app/models/verification.py`, `app/services/auth_service.py`, `app/services/email_service.py`.
- Novos: templates `flow_base`, `register`, `verify_email`, `forgot_password` e `reset_password` em `app/templates/auth/`; `app/static/js/auth.js`.
- Atualizados: configuração, comandos do banco, segurança, autenticação, modelos de funcionários/turnos/escalas/configurações e serviço de escalas.
- Atualizados: home, login, CSS de páginas, `.env.example`, README, fixtures e testes existentes.
- Novos testes: `test_account_flows.py`, `test_account_migration.py`, `test_company_isolation.py`, `test_email_service.py`.
- Revisão do login: atualizados `app/templates/auth/{login,register,flow_base,forgot_password,verify_email,reset_password}.html`, `app/templates/components/forms.html`, `app/static/js/main.js`, `app/static/css/{components,pages}.css`, `app/services/email_service.py` e `run.py`; novo `app/templates/emails/verification.html`.
- Testes da revisão: novos `tests/test_auth_interface.py` e `tests/test_run.py`; atualizados `tests/test_email_service.py` e `tests/test_http_smoke.py`. Documentação atualizada neste guia e no README.
