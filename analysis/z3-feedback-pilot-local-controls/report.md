# Piloto de novos blocos de feedback Z3

Sem inferência LLM ou chamadas ao Verus. Replays API isolados, não a busca original.
Os termos listados são da AST de entrada; não afirmam disponibilidade no E-matching.

| Caso | Fórmulas encontradas | Sem evento observado | Eventos de teoria salvos | Hints específicos observados | Perfil nativo |
|---|---|---|---|---|---|
| sat_ground | 0 | 0 | 1 | {} | 0 |
| unsat_arithmetic | 0 | 0 | 0 | {} | 0 |
| unsat_quantified | 1 | 0 | 0 | {} | 1 |
| quantifier_without_ground_trigger | 1 | 1 | 0 | {} | 0 |

## Custo dos blocos

| Caso | Bloco | Bytes | Tokens Qwen |
|---|---|---|---|
| sat_ground | theory_inferences | 147 | 53 |
| sat_ground | triggers_and_input_terms | 2 | 1 |
| sat_ground | quantifier_profile | 2 | 1 |
| sat_ground | other_search_inferences | 147 | 53 |
| unsat_arithmetic | theory_inferences | 2 | 1 |
| unsat_arithmetic | triggers_and_input_terms | 2 | 1 |
| unsat_arithmetic | quantifier_profile | 2 | 1 |
| unsat_arithmetic | other_search_inferences | 2 | 1 |
| unsat_quantified | theory_inferences | 2 | 1 |
| unsat_quantified | triggers_and_input_terms | 621 | 214 |
| unsat_quantified | quantifier_profile | 1097 | 355 |
| unsat_quantified | other_search_inferences | 2 | 1 |
| quantifier_without_ground_trigger | theory_inferences | 2 | 1 |
| quantifier_without_ground_trigger | triggers_and_input_terms | 597 | 205 |
| quantifier_without_ground_trigger | quantifier_profile | 715 | 251 |
| quantifier_without_ground_trigger | other_search_inferences | 2 | 1 |

## Campos vazios e correspondências ausentes

| Caso | Sem padrões explícitos | Sem exemplos de termos da entrada | Qids de eventos fora do inventário | Qids ambíguos | Eventos com dependências não vazias | Erros callback |
|---|---|---|---|---|---|---|
| sat_ground | 0 | 0 | 0 | 0 | 0 | 0 |
| unsat_arithmetic | 0 | 0 | 0 | 0 | 0 | 0 |
| unsat_quantified | 0 | 0 | 0 | 0 | 0 | 0 |
| quantifier_without_ground_trigger | 0 | 1 | 0 | 0 | 0 | 0 |

## Efeito da instrumentação

| Caso | Modo | Resultados | Mediana check (s) | Razão para baseline | Resultados diferentes do baseline pareado |
|---|---|---|---|---|---|
| sat_ground | baseline | {'sat': 1} | 0.03952419999768608 | 1.0 | 0 |
| sat_ground | callback | {'sat': 1} | 0.03223970000180998 | 0.8156951944301828 | 0 |
| sat_ground | profile | {'sat': 1} | 0.04218409999884898 | 1.0672980098602531 | 0 |
| sat_ground | combined | {'sat': 1} | 0.006545599997480167 | 0.16560993006470404 | 0 |
| unsat_arithmetic | baseline | {'unsat': 1} | 0.03799120000257972 | 1.0 | 0 |
| unsat_arithmetic | callback | {'unsat': 1} | 0.0059819000016432256 | 0.15745488432155438 | 0 |
| unsat_arithmetic | profile | {'unsat': 1} | 0.03399550000176532 | 0.894825643819014 | 0 |
| unsat_arithmetic | combined | {'unsat': 1} | 0.006772400000045309 | 0.17826233442443098 | 0 |
| unsat_quantified | baseline | {'unsat': 1} | 0.04090809999979683 | 1.0 | 0 |
| unsat_quantified | callback | {'unsat': 1} | 0.17991259999689646 | 4.397970084110237 | 0 |
| unsat_quantified | profile | {'unsat': 1} | 0.038703399997757515 | 0.9461060278514459 | 0 |
| unsat_quantified | combined | {'unsat': 1} | 0.02698919999966165 | 0.6597519806540927 | 0 |
| quantifier_without_ground_trigger | baseline | {'unknown': 1} | 5.065481400000863 | 1.0 | 0 |
| quantifier_without_ground_trigger | callback | {'unknown': 1} | 0.055944000003364636 | 0.011044162555478954 | 0 |
| quantifier_without_ground_trigger | profile | {'unknown': 1} | 5.097269999998389 | 1.0062755338510414 | 0 |
| quantifier_without_ground_trigger | combined | {'unknown': 1} | 0.027273699997749645 | 0.005384226659631008 | 0 |

## Limites de interpretação

- Ausência de evento não prova descarte pelo solver nem trigger incorreto.
- Hints smt genéricos não são justificativas detalhadas de aritmética/igualdade.
- Perfil nativo preserva campos brutos: não inferimos a semântica de colunas não validada.
- Fórmulas/termos/eventos grandes são omitidos inteiros, com limites registrados.
- Igualmente SAT/UNKNOWN/UNSAT não significa sequência de busca idêntica.
- Tempos muito curtos e execuções limitadas por timeout exigem cautela nas razões.
- O custo medido é de JSON isolado; não inclui programa, prompt ou saída do modelo.
- Dados ausentes e sem correspondência são detalhados no report.json.
Categorias reais sem consulta elegível: []
Controles com resultado diferente do esperado: []
Tokenizer: C:\Users\mario\OneDrive - csr.ufmg.br\Documents\GitHub\code_verification\.cluster\audit-python\qwen-coder-tokenizer.json
