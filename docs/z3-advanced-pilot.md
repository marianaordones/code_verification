# Piloto: matching, igualdades, dependências e cláusulas do Z3

Este é um teste de **extração**, sem Qwen, sem Verus e sem reparos. Usa consultas SAT/UNKNOWN já salvas, Z3 API 4.12.5 e processos separados por replay. Não executa ainda os dois braços do experimento completo.

## Submissão

Atualize as pastas `diagnostics/`, `scripts/` e `tests/`; `docs/` é opcional. Da raiz de `code_verification_git`:

```bash
bash scripts/submit_z3_advanced_pilot.sh
```

O script cria `logs/` e submete um job CPU com QoS `high`, 2 CPUs, 8 GB de RAM e limite de três horas. Não reserva GPU; pode executar independentemente da disponibilidade de uma L40S. Reutiliza a preparação Python e a instalação isolada do Z3 já adotadas pelo projeto. Não baixa pesos de modelo.

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

## Amostra e comparações

Seleciona deterministicamente três consultas de problemas distintos por categoria, em ordem do manifesto original dos 100: até **18 consultas reais**, mais **cinco controles**. A seleção usa a categoria apenas para cobertura; não usa o reparo publicado nem sua assertion removida. Categorias sem consultas elegíveis ficam explícitas. Os controles incluem SAT, UNSAT, aritmética, um quantificador sem termo ground de trigger e uma cadeia pequena de matching/igualdade.

Cada consulta tem três repetições e cinco modos (até **345 replays**), com ordem rotacionada entre repetições:

| Modo | Callback | Trace | Proof mode |
|---|---|---|---|
| baseline | Não | Não | Não |
| callback | Sim | Não | Não |
| trace | Não | Sim | Não |
| combined | Sim | Sim | Não |
| combined_proof | Sim | Sim | Sim |

O timeout de `check()` é de cinco segundos em todos. O inventário de entrada é calculado em todos os modos. O quinto modo é uma intervenção explicitamente separada para verificar se habilitar provas fornece mais evidências; seus resultados não são silenciosamente misturados ao modo normal. Não ativa `sat.euf` nem troca de engine. Compara resultados, razões de UNKNOWN, tempos de check/processo e custo de extração. Igualdade de resultados não implica mesma sequência de busca.

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

O pacote selecionado usa até **12 explicações de matching** (preferência de 6k), **seis cadeias de até três eventos** (3k), e **24 cláusulas** (5k). Espaço não usado pode ser emprestado entre blocos, com teto global rígido de 14k. Fórmulas do candidato e operações da falha têm prioridade. Eventos repetidos nas cadeias são referenciados por ID, com definições presentes no pacote. A ausência de material relevante não é preenchida artificialmente.

O pacote compacto compartilha fórmulas por checksum, preserva até três passos brutos por caminho de igualdade e até três pares de igualdade por match, informando as omissões. Os caminhos completos dentro dos limites de coleta ficam no arquivo de auditoria. As cotas preferenciais são cobradas pelo aumento efetivo em tokens do pacote, para não contar duas vezes uma fórmula compartilhada.

Custos em tokens são medidos com o tokenizer Qwen fixado, sem rede. Se ele não estiver disponível, bytes/caracteres ainda aparecem, mas a montagem orçamentada fica indisponível explicitamente. Custos são de JSON isolado, não do chat futuro inteiro.

## Limites de coleta

O callback mantém contagens após a amostragem e guarda um reservatório de até 256 cláusulas distintas, com preferência por relevância; eventos acima de 32 mil caracteres são omitidos. O parser salva até 1.000 matches, 200 mil definições de nós, 10 mil links e 100 cadeias. Todas as cotas/omissões relevantes são registradas. IDs reutilizados não são tratados como identidade estável de termos entre definições.

Um monitor interrompe o solver quando o trace ultrapassa 64 MiB; a checagem periódica pode permitir alguma ultrapassagem. Interrupções por esse limite são explícitas, não tempos de execução naturais. A instrumentação pode alterar motivos e resultados. Traces brutos são preservados para auditoria e podem ocupar vários GB no pior caso; o piloto é limitado pela amostra e pelos tetos, não captura todas as buscas do dataset.

## Arquivos a examinar

Envie principalmente `report.md` e `report.json` do destino. Eles mostram cobertura por campo, correspondências ausentes, custos e diferenças entre modos/repetições. `complete` significa completude dos processos e controles, não que todos os campos desejados foram recuperados.

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

O `summary.json` por caso inclui tempo de parsing, montagem do pacote, bytes de trace, pico de RSS quando disponível e custos dos blocos disponíveis/selecionados. A ordem cronológica dos matches/instâncias é preservada no arquivo bruto, sem prometer um grafo causal completo.
