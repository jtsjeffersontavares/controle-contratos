# 🤖 Automação do Projeto

Este projeto está totalmente automatizado com validações locais e CI/CD no GitHub.

## 📋 Configuração Local

### Instalação das dependências de desenvolvimento

```bash
pip install -r requirements-dev.txt
```

### Pre-commit Hooks (já instalado)

Os hooks são executados automaticamente **antes de cada commit**:

- ✅ **Black** — Formatação de código
- ✅ **isort** — Organização de imports
- ✅ **Flake8** — Linting
- ✅ **Bandit** — Verificação de segurança
- ✅ **pycln** — Limpeza de imports não utilizados

Se o pre-commit falhar, corrija os arquivos e tente fazer commit novamente.

### Executar validações manualmente

```bash
# Todas as validações
pre-commit run --all-files

# Apenas formatação
black contracts config

# Apenas linting
flake8 contracts config

# Verificação de segurança
bandit -r contracts config
```

## 🧪 Testes

### Rodar localmente

```bash
# Todos os testes
python manage.py test contracts.tests

# Com pytest
pytest

# Com cobertura
pytest --cov=contracts --cov-report=html
```

### Rodar testes no Django (recomendado)

```bash
python manage.py test contracts.tests --verbosity 2
```

## 🔄 CI/CD Pipeline (GitHub Actions)

Quando você faz push para `main` ou abre um PR:

1. **Lint & Format** — Verifica código com Black, isort, Flake8
2. **Security** — Bandit verifica vulnerabilidades
3. **Django Tests** — Executa suite de testes completa
4. **Coverage** — Calcula cobertura de testes

O pipeline falhará se:
- Código não estiver formatado (Black)
- Imports desorganizados (isort)
- Violações de estilo (Flake8)
- Testes falharem

## 📝 Workflow Recomendado

```bash
# 1. Faça suas mudanças
# (edite os arquivos)

# 2. Stage seus arquivos
git add .

# 3. Commit (pre-commit roda automaticamente)
git commit -m "sua mensagem"
# Se falhar: corrija e tente novamente

# 4. Push para o repositório
git push

# 5. GitHub Actions roda automaticamente
# (veja em: https://github.com/pessanhatpbp/controle-contratos/actions)
```

## ⚙️ Configuração de Ferramentas

- **Black** — `setup.cfg` (max-line-length=120)
- **isort** — `setup.cfg` (profile=black)
- **Flake8** — `setup.cfg` + `.flake8`
- **Bandit** — `.bandit`
- **Pytest** — `pytest.ini`
- **Pre-commit** — `.pre-commit-config.yaml`
- **GitHub Actions** — `.github/workflows/tests.yml`

## 🚀 Primeiro Uso

Se está usando este repositório pela primeira vez:

```bash
# 1. Instale as dependências de desenvolvimento
pip install -r requirements-dev.txt

# 2. Pre-commit já está instalado, mas você pode atualizar:
pre-commit autoupdate

# 3. Você está pronto!
# Próximo commit ativará os hooks automaticamente
```

## ❓ Dúvidas Frequentes

**P: O pre-commit não funciona?**
R: Execute `pre-commit install` novamente na raiz do projeto.

**P: Posso ignorar as validações?**
R: Não recomendado, mas pode usar `git commit --no-verify` (evite isso).

**P: Como atualizar as ferramentas?**
R: Execute `pre-commit autoupdate` e faça commit das mudanças.

**P: Testes falharam no GitHub mas passam localmente?**
R: Verifique se rodou todos os testes localmente: `python manage.py test`

---

**Status:** ✅ Totalmente automatizado
**Última atualização:** 2026-08-15
