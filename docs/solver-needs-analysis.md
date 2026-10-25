# Análise das propostas e do contexto

O script `scripts/analyze_solver_needs.py` lê resultados salvos sem carregar
modelos, executar Verus/Z3 ou validar hashes do código atual. Pode analisar
execuções antigas mesmo após atualizações do repositório. Escreve somente na
pasta de análise, preservando os estudos de origem.

Por padrão, compara:

- `../code_verification/results/solver-needs-qwen14b-100/seed-20261018` e
  `../code_verification/results/solver-needs-qwen14b-remaining362/seed-20261018`, agregados como
  experimento inicial de 462 tarefas, rejeitando IDs duplicados;
- `results/solver-needs-qwen14b-100-internals24k/seed-20261018`, como experimento
  independente de 100 tarefas.

Os caminhos são calculados a partir da localização do script, considerando o
projeto atual em `code_verification_git/` e o anterior em `code_verification/`,
na pasta ao lado. Não é necessário copiar os dois lotes antigos. O tokenizer
também é procurado no cache do projeto anterior se não estiver no atual.

## Executar

Atualize `scripts/` no cluster. A estrutura já usada pelos experimentos é suficiente;
não é necessário reorganizar `results/`. Depois de concluir a retomada dos casos
pendentes, na raiz do projeto:

```bash
mkdir -p logs
sbatch scripts/slurm/solver_needs_analysis.slurm
```

Esse job usa apenas CPU. Reutiliza o runtime Python existente e o tokenizer
local do modelo, sem inferência ou execução do solver. Para executar diretamente,
sem os recursos opcionais de tokenização do runtime:

```bash
python3 scripts/analyze_solver_needs.py
```

Mesmo sem tokenizer, os tokens de entrada/saída registrados permitem conferir
o contexto total. A contagem do bloco interno fica explicitamente indisponível,
em vez de aparecer como zero. O job Slurm é a opção recomendada para medir também
esse bloco, pois disponibiliza a biblioteca `tokenizers` do runtime existente.

Se os caminhos forem diferentes, passe-os como argumentos:

```bash
python3 scripts/analyze_solver_needs.py \
  --initial results/LOTE100/seed-20261018 results/LOTE362/seed-20261018 \
  --expanded results/LOTE24K/seed-20261018 \
  --output analysis/solver-needs-attempts
```

Os mesmos argumentos também podem ser passados após o arquivo `.slurm`.
`--tokenizer` aceita o caminho de um `tokenizer.json` offline da revisão exata
do Qwen usada no experimento.

## Resultados

Em `analysis/solver-needs-attempts/`:

- `report.md`: tabelas acumuladas após cada proposta e resumo dos tokens;
- `success_by_attempt.csv`: curvas de ambos os braços e experimentos;
- `initial.json`: detalhes dos lotes iniciais agregados;
- `internals24k.json`: detalhes da versão ampliada e auditoria de contexto.

**Proposta 1 é a primeira resposta do modelo.** Propostas 2, 3 e 4 são reparos
posteriores. A coluna de sucessos acumulados conta tarefas resolvidas até aquela
proposta; a coluna de novos sucessos conta somente a primeira resolução naquela
proposta. Não são taxas de pass@k com amostras independentes: há feedback entre
propostas.

O denominador principal contém todas as tarefas selecionadas elegíveis. Pendentes
não contam como sucessos conhecidos; casos já verificados antes do modelo são
excluídos. O JSON inclui também a curva restrita aos pares com `task.json` final
nos dois braços, a lista de pendências e resultados por categoria. Sucessos já
registrados em `result.json` são preservados mesmo se a tarefa ainda não tiver
resumo final. Arquivos ausentes são indicados e não transformados em resultados
completos. Recomenda-se executar ao fim dos jobs para obter um snapshot estável.

A auditoria distingue:

1. entrada + reserva de saída acima do contexto;
2. entrada + saída efetivamente gerada acima do contexto;
3. saída truncada pelo limite de geração;
4. bloco interno acima de seu orçamento, quando há tokenizer;
5. mensagens de erro salvas relacionadas a contexto, inclusive rejeições antes
   da resposta. Arquivos `error.json` antigos de casos depois concluídos são
   marcados como potencialmente obsoletos.

O script audita as respostas e erros persistidos. Um erro presente apenas nos logs
Slurm, sem arquivo de erro salvo, não pode ser identificado por esta análise.
A contagem de grupos omitidos é descrita abaixo; caber no contexto é diferente
de enviar todos os eventos relevantes. A auditoria anterior, com testes marginais
de inclusão de eventos, continua documentada em
`analysis/solver-needs-100-context-audit/`.

## Quantificadores disponíveis e enviados

O relatório inclui uma tabela por proposta com média, mediana, P90 e máximo de
grupos disponíveis nos eventos salvos e de grupos efetivamente enviados. Mostra
quantos pedidos atingiram o teto configurado e quantos omitiram grupos associados
ao candidato. Os detalhes estão em `quantifier_audit` e `quantifier_rows` no JSON.

Para a proposta 1, a origem da evidência é `inputs/ID/`. Para as seguintes, é a
tentativa anterior: os eventos de `attempt_01` alimentam a proposta 2, por exemplo.
A contagem considera replays concordantes que alimentaram pedidos efetivamente
respondidos, sem executar novos replays. Um grupo é o par (consulta, fórmula SMT),
como no empacotador; o JSON também informa quantas fórmulas distintas há ignorando
a identidade da consulta.

As médias não representam todos os quantificadores criados pelo Z3. Há limites
anteriores: consultas selecionadas, timeout diagnóstico e reservatório de eventos.
Muitas fórmulas salvas são axiomas genéricos, portanto uma média acima de 80 não
demonstra que 80 seja insuficiente para fornecer material relevante. Omissões de
grupos do candidato são um indicador mais específico, mas ainda heurístico.

O relatório identifica omissões abaixo do teto não explicadas pelas cotas de
axiomas genéricos. Elas motivam investigar o orçamento de tokens; não são uma
atribuição causal exata, pois a análise não reproduz cada decisão cronológica do
empacotador. Instanciações observadas e salvas são contadas separadamente dos
grupos de quantificadores. Dados ausentes não são registrados como zero.

Para auditar a variante 80x3:

```bash
sbatch scripts/slurm/solver_needs_analysis.slurm \
  --expanded results/solver-needs-qwen14b-100-internals32k-samples/seed-20261018/80x3 \
  --output analysis/solver-needs-32k-80x3
```

Para 50x5, substitua `80x3` por `50x5` nos dois caminhos. O nome de saída
`internals24k.json` é histórico: ele contém a variante informada em `--expanded`.
