# LLM-Guided Program Verification with SMT Feedback

Projeto de pesquisa sobre geração e reparo de provas de programas por modelos
de linguagem, com foco em Rust/Verus e no solver SMT Z3.

A pergunta central é: **informações internas do solver ajudam um LLM a reparar
uma prova que falhou, além do que ele consegue fazer com os diagnósticos
convencionais do verificador?**

## Visão geral

O projeto reúne experimentos em que um modelo propõe anotações de prova, o Verus
avalia o candidato e o resultado orienta novas propostas. A implementação e os
contratos do programa são preservados conforme a política de edição de cada
experimento. Um reparo só é considerado bem-sucedido quando o candidato atende
às restrições do experimento e passa pela verificação do arquivo completo.

As comparações investigam diferentes modelos, prompts, formatos de edição e
tipos de feedback. Os experimentos incluem geração de arquivos completos,
reparos localizados e estudos pareados com e sem informações internas do Z3.

## Questões de pesquisa

- Qual é a contribuição dos internals em relação aos diagnósticos do Verus?
- Quais informações do solver são úteis e como selecioná-las dentro do contexto
  disponível para o modelo?
- O efeito varia conforme o mecanismo de falha da prova?
- Como o formato de edição influencia repetições, erros e sucesso dos reparos?
- Quais limitações decorrem da capacidade do modelo e quais decorrem do feedback?

## Dados e experimentos

O repositório trabalha com tarefas de **VerusBench** e com os casos Verus/Z3 de
**Identifying What the Solver Needs**. Estes últimos removem uma assertion
essencial de um programa previamente verificado, preservando as outras
anotações. São tarefas diferentes da geração de provas sobre programas sem as
anotações necessárias, e seus resultados devem ser interpretados separadamente.

Os modelos explorados incluem Qwen3-8B, Qwen3-14B e
Qwen2.5-Coder-14B-Instruct. Os estudos pareados utilizam os mesmos candidatos
iniciais e sementes, variando o feedback fornecido ao modelo. Listas fixadas de
IDs, configurações e registros por tentativa apoiam a reprodutibilidade.

## Feedback do solver

Além das mensagens de erro do Verus, o projeto explora consultas SMT completas,
estatísticas de busca e eventos de instanciação de quantificadores. O feedback
compacto pode incluir fórmulas quantificadas, identificadores, triggers, termos
de substituição e literais de cláusulas associados às instanciações.

Parte dessas informações é obtida por **reexecuções diagnósticas instrumentadas**
de consultas capturadas. Elas descrevem essas reexecuções e não garantem
reproduzir a sequência original de busca do Verus. A seleção dos eventos é
heurística; sua presença não demonstra necessidade para a prova, e sua ausência
no feedback não demonstra ausência na busca.

## Organização

| Diretório | Conteúdo |
|---|---|
| `baseline/` | Inferência, verificação, integridade e métricas dos experimentos de geração e reparo. |
| `diagnostics/` | Captura de consultas e extração de informações do Z3. |
| `repair_study/` | Reparos localizados e seleção de eventos por relevância. |
| `local_ablation/` | Comparações pareadas com e sem internals. |
| `solver_needs_study/` | Estudos sobre assertions essenciais do benchmark Solver Needs. |
| `configs/`, `prompts/`, `data/` | Configurações, prompts e seleções de tarefas. |
| `scripts/`, `tests/` | Infraestrutura de execução e validação. |
| `docs/` | Descrição dos protocolos, decisões e documentação operacional. |

Os registros dos experimentos incluem prompts, respostas, candidatos,
diagnósticos, dados do solver, tempos e consumo de tokens. Além da taxa de
sucesso, a análise considera reparos exclusivos de cada braço, erros de edição,
repetições e disponibilidade efetiva do feedback.

## Documentação e referências

- [Arquitetura e referências](docs/architecture.md)
- [Ablação de internals com reparo localizado](docs/localized-internals-ablation.md)
- [Experimentos com Solver Needs](docs/solver-needs-qwen14b.md)
- [Documentação do ambiente de execução](docs/cluster.md)
- [Verus](https://github.com/verus-lang/verus)
- [Z3](https://github.com/Z3Prover/z3)
- [VerusBench e síntese de provas Verus](https://github.com/microsoft/verus-proof-synthesis)
- [Identifying What the Solver Needs](https://github.com/knutsa/solver-needs)
