---
name: system-data-collection
user-invocable: true
description: '**WORKFLOW SKILL** — Colete e armazene dados abrangentes do sistema em memória para continuidade do projeto. USE FOR: reunir informações completas do ambiente (SO, Python, workspace, dependências) organizadas por seções para solução de problemas e replicação de configuração. DO NOT USE FOR: tarefas gerais de codificação; use o agente padrão. Não coleta dados sensíveis.'
---

# Habilidade de Coleta de Dados do Sistema

## Fluxo de Trabalho

Esta habilidade coleta informações detalhadas sobre o ambiente de desenvolvimento e as armazena em memória para uso futuro na continuidade do projeto.

### Passos:

1. **Coletar informações básicas do sistema**
   - Sistema operacional, versão, arquitetura
   - Hardware básico (CPU, memória, disco)
   - Variáveis de ambiente relevantes (PATH, PYTHONPATH, etc.)

2. **Detalhes do ambiente Python**
   - Versão do Python
   - Ambiente virtual ativo e caminho
   - Pacotes instalados com versões
   - Configurações do Pylance e análise Python

3. **Estrutura e conteúdo do workspace**
   - Lista completa de diretórios e arquivos
   - Conteúdo de arquivos de configuração (requirements.txt, config.ini, package.json, etc.)
   - Informações de build e compilação
   - Status do Git (se aplicável)

4. **Dados específicos do projeto**
   - Versão do projeto (VERSION.md, version.py)
   - Documentação (README.md, docs/)
   - Scripts de build e execução

5. **Armazenar dados em memória**
   - Salvar todas as informações coletadas em `/memories/repo/system-data.md`
   - Organizar em seções claras: Sistema, Python, Workspace, Projeto

### Implementação

- Use comandos do terminal para obter informações do sistema (ex: `systeminfo`, `wmic`, `python --version`)
- Utilize ferramentas Python para detalhes do ambiente
- Leia arquivos de configuração e documentação com read_file
- Liste estrutura do workspace com list_dir
- Use a ferramenta de memória para armazenar os dados coletados, organizados por seções

### Exemplo de Uso

Quando precisar diagnosticar problemas, configurar um novo ambiente ou continuar o desenvolvimento em outro local, invoque esta habilidade para ter todos os dados necessários prontamente disponíveis.