# Tarefas pendentes

## Concluídas nesta etapa

- Implementado módulo de pregões com itens e locais de entrega por OM com quantidade.
- Implementada cópia de itens do pregão para contrato na criação e por ação manual no contrato.
- Integrada importação SDAP para criar/vincular pregão e itens de pregão automaticamente.
- Adicionadas validações de consistência para evitar soma de destinos maior que a quantidade do item.
- Adicionadas exportações de pregões em CSV, XLSX e PDF.
- Ampliada a suíte de testes cobrindo importação, cópia de itens, páginas e relatórios de pregões.
- Removido o campo "OM do termo de referência" da edição de pregões.
- Removido o botão de copiar itens do pregão no contrato.
- Removidos da edição de contrato os campos "Fim da garantia" e "OM do termo de referência".
- Ajustada edição de ordem para listar somente itens do próprio contrato e exibir OMs de referência do item do pregão.
- Removido o atalho "Ordens de fornecimento" do menu lateral.

## Pendências priorizadas

1. Segurança de autorização por perfil para documentos: restringir download por escopo de contrato e perfil.
2. Endurecimento de configuração de produção: remover defaults inseguros de debug/chave/cookies.
3. Revisar uso de is_staff como bypass de grupo em permissões de negócio.
4. Melhorar desempenho do painel com agregações no banco e menos processamento em memória.
5. Adicionar métricas e filtros no painel para visão de pregões (status, valor estimado, itens sem contrato).
6. Incluir relatório consolidado de cobertura de contratação por pregão (quantidade licitada versus contratada).

## Sugestão de ordem

1. Segurança (itens 1, 2, 3).
2. Performance (item 4).
3. Evoluções de produto de pregões (itens 5, 6).
