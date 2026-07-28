# Gestão de Contratos — SDAP

Sistema web multiusuário para cadastro, acompanhamento e auditoria de contratos, itens, notas de empenho, ordens de fornecimento, entregas, alterações contratuais, PAAI e documentos.

## Recursos entregues

- Painel com contratos, valores, vigências, atrasos, entregas e PAAI;
- contratos, empresas, OMs e responsáveis;
- itens do pregão e códigos TDV;
- empenhos com Ação Orçamentária, PTRES, origem do crédito e PI;
- ordens de fornecimento por OM destino;
- entregas, notas fiscais e aceite;
- aditivos, reajustes, repactuações, apostilamentos e prorrogações;
- PAAI/processos administrativos e sanções;
- documentos de até 10 MB;
- perfis Administrador, Gestor, Fiscal e Consulta;
- trilha de auditoria;
- importação da estrutura `SDAP_CONTRATOS_2026_v2.xlsx`, com prévia;
- exportação para XLSX, PDF e CSV;
- implantação preparada para Render e Docker/PostgreSQL, com backup SQLite.

## Execução local

Para testes locais, o projeto pode ser executado com SQLite e o servidor Django:

```bash
python manage.py migrate
python manage.py bootstrap_system --no-admin
python manage.py runserver
```

Também é possível usar Docker Compose:

```bash
docker compose up -d --build
```

## Deploy no Render

O projeto já está preparado para deploy no Render por meio de `render.yaml`.

### Variáveis de ambiente mínimas

- `DJANGO_SECRET_KEY`: chave secreta forte.
- `DJANGO_DEBUG`: defina como `0` em produção.
- `DJANGO_ALLOWED_HOSTS`: adicione `localhost`, `127.0.0.1` e o domínio público do Render.
- `DB_ENGINE=postgresql`
- `DATABASE_URL`: URL completa do PostgreSQL gerada pelo Render.

### Passos

1. Conecte este repositório ao Render.
2. Crie um banco PostgreSQL e associe a variável `DATABASE_URL` ao serviço web.
3. Defina as variáveis acima no painel do Render.
4. Faça o deploy; o container iniciará automaticamente com o script de entrada do projeto.

## Comandos úteis

```bash
python manage.py test
python manage.py check
python manage.py seed_demo
python manage.py preview_import caminho/planilha.xlsx --sheet Planilha1
python manage.py backup_system
```

## Observação sobre dados

Nenhum dado real da planilha fornecida acompanha o pacote. O arquivo foi utilizado apenas para validar a modelagem e o importador. A inclusão dos dados ocorre dentro do sistema, após login e revisão da prévia.

## Backlog técnico

As pendências priorizadas e o status recente de evolução estão em `docs/TAREFAS_PENDENTES.md`.
