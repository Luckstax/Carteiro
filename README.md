# Carteiro

Automacao local para apoiar o gerenciamento de contatos profissionais e o envio manual de candidaturas por Gmail, com perfis separados.

> Estado do projeto: em preparacao para publicacao. O banco de dados atual, os curriculos e as credenciais sao dados locais e nao fazem parte deste repositorio.

## O que existe hoje

- Perfis de usuario armazenados em SQLite.
- Autenticacao Gmail por OAuth, com um arquivo de token separado por ID de usuario.
- Envio de e-mail com anexo e registro do resultado no banco local.
- Validacoes para evitar envio a contatos ja utilizados e exigir mensagens personalizadas.
- Separacao dos contatos por `usuario_id`.

O script principal nao envia mensagens automaticamente ao ser iniciado; ele inicializa/verifica o banco e mostra o perfil padrao.

## Requisitos

- Python 3.10 ou superior (validar a versao minima em testes antes de publicar uma versao estavel).
- Um projeto Google Cloud com a Gmail API habilitada e credenciais OAuth de aplicativo para desktop.
- Uma base SQLite local preparada com as tabelas `usuarios` e `contatos`.

## Instalacao

1. Clone este repositorio.
2. Crie e ative um ambiente virtual:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Instale as dependencias:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Configure suas credenciais OAuth localmente como `credentials.json` na raiz do projeto. Nunca publique esse arquivo.
5. Prepare `dados/contatos.db` com seus proprios perfis e contatos. A base de dados de uso pessoal nao e distribuida neste repositorio.
6. Execute a verificacao inicial:

   ```powershell
   python carteiro.py
   ```

Na primeira autenticacao de um perfil, o navegador sera aberto para autorizacao Google. O token sera salvo em `dados/tokens/usuario_<id>.json`.

## Configuracao por perfil

Cada registro em `usuarios` tem um ID, nome, e-mail, caminho local do curriculo e preferencias. O token OAuth e selecionado pelo ID do perfil. Antes de enviar, confirme que o perfil selecionado corresponde a conta Gmail desejada.

Os caminhos dos curriculos devem ser validos no computador em que o Carteiro sera executado. Os dados de contato, o historico e os curriculos devem permanecer locais.

## Seguranca e privacidade

- Nao versione `credentials.json`, tokens OAuth, banco SQLite, curriculos, arquivos `.env` ou logs pessoais.
- Revise `git status` e os arquivos staged antes de cada `git commit`.
- Use apenas contatos obtidos de forma legitima e respeite as politicas do Gmail e as regras aplicaveis a comunicacoes profissionais.
- O projeto ainda precisa de testes automatizados e de um fluxo inicial de criacao do banco/perfil antes de ser considerado pronto para uso por terceiros.

## Limites conhecidos

A base atual foi desenvolvida para um ambiente local existente. A inicializacao principal nao cria ainda todas as tabelas nem cadastra automaticamente o primeiro perfil. A publicacao deve ser considerada preparatoria ate que a configuracao inicial e os testes sejam concluidos.
