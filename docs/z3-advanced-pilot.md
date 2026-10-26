# Piloto: matching, igualdades, dependências e cláusulas do Z3

**Coleta corrigida (v3):** o inventário é calculado uma única vez por consulta, em processo sem trace. Durante a busca, o callback guarda referências limitadas a ASTs, sem chamar `.sexpr()`. Um marcador AST nativo identifica o fim da captura; isso funciona mesmo com o buffering do arquivo. As cláusulas são traduzidas para um contexto sem trace e só então formatadas. O parser ignora tudo após o marcador e rejeita traces antigos em que detecta colisões entre IDs de quantificadores e estruturas de formatação. A presença de um ID, sozinha, não torna um termo resolvido.

Use **um destino novo** ao repetir este piloto. Os arquivos antigos não são sobrescritos nem misturados aos resultados corrigidos. Casos de controle agora verificam automaticamente o `qid`, o número zero e `(f 0)`, além dos dois quantificadores do controle de cadeia.

Este é um teste de **extração**, sem Qwen, sem Verus e sem reparos. Usa consultas SAT/UNKNOWN já salvas, Z3 API 4.12.5 e processos separados por replay. Não executa ainda os dois braços do experimento completo.

## Submissão

Atualize as pastas `diagnostics/`, `scripts/` e `tests/`; `docs/` é opcional. Da raiz de `code_verification_git`:

```bash
bash scripts/submit_z3_advanced_pilot.sh
```

O script cria `logs/` e submete um job CPU com QoS `high`, 2 CPUs, 8 GB de RAM e limite de uma hora. Não reserva GPU; pode executar independentemente da disponibilidade de uma L40S. Reutiliza a preparação Python e a instalação isolada do Z3 já adotadas pelo projeto. Não baixa pesos de modelo.

Origem padrão:

```text
results/solver-needs-qwen14b-100-internals24k/seed-20261018
```

Destino padrão:

```text
results/z3-advanced-pilot/job-JOBID/
```

Para escolher origem/destino, passe ambos:

```bash
bash scripts/submit_z3_advanced_pilot.sh \
  results/solver-needs-qwen14b-100-internals24k/seed-20261018 \
  results/z3-advanced-pilot/pilot01
```

Para retomar o piloto, repita com o mesmo destino explícito e código inalterado. Novos testes com configurações ou código diferentes devem usar outro destino. Não atualize arquivos no checkout de uma execução de reparo ainda ativa: a inclusão de módulos em `diagnostics/` também pode alterar o fingerprint registrado por ela.

Para começar apenas pelos cinco controles, com uma repetição:

```bash
bash scripts/submit_z3_advanced_pilot.sh \
  results/solver-needs-qwen14b-100-internals24k/seed-20261018 \
  results/z3-advanced-pilot/controls-v3 \
  --controls-only --repetitions 1
```

Os argumentos após os dois caminhos são encaminhados à análise. `--include-proof-mode` habilita o modo experimental com provas. `--measure-all-tokens` pede também a tokenização dos blocos brutos completos, que pode ser cara. Nenhuma dessas opções é necessária para a execução padrão.

## Amostra e comparações

Por padrão, seleciona **somente cinco problemas reais**, sem acrescentar controles sintéticos: `V-329` (AX), `V-444` (INST-forall), `V-381` (INST-witness), `V-245` (NLA) e `V-368` (Other). Inclui os dois casos que atingiram o teto de trace anteriormente (`V-329` e `V-368`) e casos que apresentaram dificuldades de correspondência. Usa a primeira consulta SAT/UNKNOWN elegível de cada problema, em ordem do manifesto. Não usa o reparo publicado nem sua assertion removida. IDs ausentes ou consultas não disponíveis são sinalizados, sem substituir silenciosamente os casos.

Use `--problem-ids ID1 ID2 ...` para escolher outra lista. A amostra antiga de até 18 consultas reais é opcional via `--full-sample`; acrescente `--include-controls` se também desejar os cinco controles. `--controls-only` executa apenas os cinco controles, independentemente da lista de problemas reais.

Cada consulta tem três repetições e quatro modos padrão: **60 replays**, além de cinco inventários sem busca. A ordem dos modos é rotacionada entre repetições:

| Modo | Callback | Trace | Proof mode |
|---|---|---|---|
| baseline | Não | Não | Não |
| callback | Sim | Não | Não |
| trace | Não | Sim | Não |
| combined | Sim | Sim | Não |
| combined_proof (opcional) | Sim | Sim | Sim |

O timeout de `check()` é de cinco segundos em todos. Um inventário de entrada sem trace é compartilhado por todos os modos, com hash da consulta verificado em cada worker. Seu tempo separado aparece como `inventory_process_seconds`; `inventory_seconds` nos workers mede leitura/cópia desse inventário. O modo opcional com provas é uma intervenção separada e não entra no padrão após ter falhado nos casos reais do piloto anterior. Não ativa `sat.euf` nem troca de engine. Compara resultados, razões de UNKNOWN, tempos de check/processo e custo de extração. Igualdade de resultados não implica mesma sequência de busca.

O custo de `check()` nos modos com trace inclui escrita no filesystem do destino. Portanto, a razão de tempos também depende do custo de I/O nesse filesystem, e não apenas de alterações na busca.

## Campos e limites de interpretação

O parser segue a documentação oficial de [Equality Explanation Logging](https://github.com/Z3Prover/z3/wiki/Equality-Explanation-Logging).

- **Matching:** fingerprint, quantificador, trigger, termos ligados, termos de topo que fizeram matching, pares de igualdade explicitamente registrados e caminhos de substituição até a raiz. Faz correspondência com fórmulas de entrada por qid único; fórmulas transformadas continuam identificadas como tal. Qids ambíguos/sem correspondência e referências não resolvidas são contados.
- **Igualdades:** preserva passos `lit`, `cg`, `th` e `root`, termos, suportes, IDs e linhas originais. Caminhos limitados a 12 passos; caminhos faltantes, cíclicos ou afetados por IDs reutilizados não são declarados resolvidos. Chegar à mesma raiz não constitui uma prova independente completa: suportes de congruência/teoria não são verificados recursivamente.
- **Dependências:** liga um termo explicitamente nomeado por um match a um `attach-enode` anterior, dentro de uma instanciação efetivamente observada. Exige o mesmo ID e versão da definição e não infere ligação por ordem, igualdade textual ou símbolos comuns. São **associações temporais registradas**, não prova de que a instanciação criou o termo ou foi necessária. Rollbacks de escopo limpam os vínculos de forma conservadora. Limitação motivada também pela [discussão oficial sobre ciclos e attach-enode](https://github.com/Z3Prover/z3/issues/6735).
- **Cláusulas não-instanciação:** preserva literais, regra/hint e dependências brutas do callback; exclui `inst`, assumptions, deleções e Tseitin. Conta separadamente `smt` genérico e `euf`/`farkas`/`bound`/`implied-eq`. Dependências de cláusulas não são mapeadas automaticamente aos IDs do trace. O escopo de validade de branches não é reconstruído.

Os arquivos mostram também matches registrados sem instanciação observada. Não confundir uma oportunidade de matching com uma instanciação realizada. Termos renderizados podem ser parciais, com IDs e registros brutos preservados; não são reconstruções SMT-LIB garantidamente executáveis.

## Orçamento planejado e pacote de teste

| Parte do futuro experimento | Tokens máximos |
|---|---:|
| Base 50x3 | 24.576 |
| Complemento anterior reduzido | 12.288 |
| Três novos blocos | 14.336 |
| Resposta | 4.096 |
| Programa, instruções, diagnósticos e histórico | 10.240 |
| **Total** | **65.536** |

Neste piloto, **somente os três blocos novos são construídos e medidos**. O código não altera ainda o experimento completo nem repacota o complemento anterior. Os 10k são uma divisão nominal; o futuro runner precisará medir o chat completo e reduzir os blocos novos se programa/histórico exigirem mais espaço. Não há aqui teste de viabilidade de KV cache na L40S.

O pacote selecionado usa até **12 explicações de matching** (preferência de 7k), **seis cadeias de até três eventos** (4k), e **24 cláusulas** (3k). A divisão favorece matching e cadeias, em vez das numerosas cláusulas genéricas. Espaço não usado pode ser emprestado entre blocos, com teto global rígido de 14k. Fórmulas do candidato e operações da falha têm prioridade. Eventos repetidos nas cadeias são referenciados por ID, com definições presentes no pacote. Uma primeira seleção tenta representar cada bloco disponível antes de preencher o restante. A ausência de material relevante não é preenchida artificialmente.

O pacote compacto compartilha fórmulas por checksum, preserva até três passos brutos por caminho de igualdade e até três pares de igualdade por match, informando as omissões. Os caminhos completos dentro dos limites de coleta ficam no arquivo de auditoria. Compactação, ranking e custos individuais são calculados uma vez e reutilizados. O empacotamento considera até 64 matches, 24 cadeias e 64 cláusulas após o ranking; distingue quantidades disponíveis, consideradas e selecionadas. As estimativas aditivas servem somente para seleção rápida: o JSON completo é tokenizado exatamente no final e unidades inteiras são removidas até caber, se necessário. Não são feitas cópias profundas e tokenizações do pacote completo a cada candidato.

Custos do pacote final e dos blocos selecionados são medidos com o tokenizer Qwen fixado, sem rede. Fórmulas compartilhadas têm custo separado; a soma dos blocos isolados não é o custo exato do JSON completo. A tokenização dos blocos brutos, que podem ser muito grandes, fica desativada por padrão; use `--measure-all-tokens` para medi-la. Seus bytes/caracteres continuam disponíveis. Se o tokenizer não estiver disponível, a montagem orçamentada fica indisponível explicitamente. Custos são de JSON isolado, não do chat futuro inteiro. O piloto monta 14k **por consulta**; o futuro runner ainda precisará compartilhar os 14k entre todas as consultas do pedido.

## Limites de coleta

O callback mantém contagens após a amostragem e guarda até 512 candidatos como referências AST, priorizados por símbolos acessados sem pretty-printing. Depois da busca serializa até 256 cláusulas distintas. Há limites de 128 literais e 4.096 nós por candidato; eventos acima de 32 mil caracteres são omitidos. Cláusulas repetidas por permutação de literais são deduplicadas sem confundir hints/dependências diferentes. O parser salva até 1.000 matches, 200 mil definições de nós, 10 mil links e 100 cadeias. Todas as cotas/omissões relevantes são registradas. IDs reutilizados não são tratados como identidade estável de termos entre definições.

Um monitor interrompe o solver quando o trace ultrapassa 64 MiB; a checagem periódica pode permitir alguma ultrapassagem. Interrupções por esse limite são explícitas, não tempos de execução naturais. A instrumentação pode alterar motivos e resultados. Traces brutos são preservados para auditoria e podem ocupar vários GB no pior caso; o piloto é limitado pela amostra e pelos tetos, não captura todas as buscas do dataset.

## Arquivos a examinar

Envie principalmente `report.md` e `report.json` do destino. Eles mostram cobertura por campo, correspondências ausentes, custos e diferenças entre modos/repetições. `complete` exige processos/controles concluídos e validações semânticas dos controles aprovadas, mas não significa que todos os campos desejados foram recuperados. As falhas incluem agora código de saída, timeout, erro do worker e trecho de stderr no relatório agregado.

Por consulta, repetição e modo:

```text
input-quantifiers.json
report.json
process.json
stderr.txt
trace.log                 # apenas modos de trace
trace-evidence.json
clauses.json
new-feedback-14k.json
```

O `summary.json` por caso inclui tempo de parsing, montagem do pacote, formatação das cláusulas, bytes de trace, pico de RSS quando disponível e custos dos blocos selecionados. A seleção registra chamadas ao encoder, volume de caracteres tokenizados e número de verificações exatas do pacote completo. A ordem cronológica dos matches/instâncias é preservada no arquivo bruto, sem prometer um grafo causal completo.
