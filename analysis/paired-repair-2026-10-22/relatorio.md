# Análise dos experimentos pareados — 22/10/2026

Fonte: download_2026-10-22_08-15-15.zip. Auditoria dos arquivos salvos; sem reexecutar Verus, Z3 ou inferência.

Os dois braços concluíram os mesmos 114 candidatos inicialmente falhos elegíveis, com até dois reparos. A comparação independente confirmou igualdade do payload inicial nos 114 pares e os hashes do candidato inicial em ambos os braços. Isso não é uma execução nova dos 150 problemas. As categorias selecionadas foram MBPP 51, Diffy 34, Misc 20 e CloverBench 9; 36 candidatos iniciavam com falha de compilação e 78 com falha de verificação.

| Métrica | Arquivo completo | Edição localizada |
|---|---:|---:|
| Candidatos reparados | 0/114 | 5/114 (4,39%) |
| Reparados após primeiro reparo | 0 | 4 |
| Reparados após até dois reparos | 0 | 5 |
| Tentativas | 228 | 224 |
| Sem mudança efetiva | 141 (61,84%) | 44 (19,64%) |
| Compilação ou sintaxe | 86 (37,72%) | 104 (46,43%) |
| Rejeições de integridade | 12 | 14 |
| Tokens de saída | 72.049 | 19.091 |
| Tokens de entrada | 2.629.722 | 2.648.251 |
| Feedbacks com internals disponíveis | 141 | 129 |
| Saídas truncadas | 0 | 0 |

## Os cinco reparos

Todos os cinco candidatos finais têm Verus returncode 0, `2 verified, 0 errors` e integridade válida nos artefatos salvos. Os diffs estão em examples/.

- mbpp_task_id_760, reparo 1: acrescenta trigger explícito a arr[i]; sem internals disponíveis.
- mbpp_task_id_557, reparo 1: troca índice `i as usize` por `i as int` na expressão de prova; sem internals disponíveis.
- mbpp_task_id_145, reparo 1: substitui usos indevidos de `old(arr)` pela visão `arr@`; sem internals disponíveis.
- cloverbench_cal_div, reparo 1: troca invariante `y < 191` por `y <= 191`, permitindo o estado inicial; com internals disponíveis, três grupos de biblioteca e nenhum grupo de anotação do candidato.
- mbpp_task_id_457, reparo 2: adiciona propriedade universal do mínimo sobre o prefixo já processado `0 <= k < index`. No primeiro reparo usou o vetor inteiro e falhou na entrada do loop; o segundo restringiu ao prefixo e verificou. Com internals disponíveis, incluindo um grupo de anotação do candidato no reparo bem-sucedido.

## Seleção de internals

No full, 29 feedbacks tinham eventos salvos com qid user_candidate; todos os 29 expuseram ao menos um grupo de anotação do candidato. No local foram 32/32. Não houve omissão total desse tipo nos eventos salvos auditados. Isso não garante que todos os eventos possíveis da busca tenham sido capturados nem que todo evento relevante tenha sido selecionado.

As métricas do resumo contam também definições do candidato: 35 feedbacks full e 38 local tinham grupos de candidato (anotações OU definições). Não confundir com os 29/32 de anotações user_candidate.

Todos os 87 feedbacks indisponíveis do full e os 95 do local correspondiam a relatórios sem consultas. Não identifiquei entre esses feedbacks um caso de consulta existente descartada por replay ou divergência. Nos primeiros reparos, 75/114 receberam internals em ambos os braços. As trajetórias posteriores divergiram.

O maior prompt observado teve 30.065 tokens de entrada no full e 31.817 no local, abaixo do limite de 49.152 incluindo a reserva de 4.096 tokens. Foram expostos no máximo 18 grupos por feedback; até 30 instâncias totais no full e 31 no local. Os tetos de 24 grupos e quatro instâncias por grupo não são garantias de preenchimento. A ausência de truncamento da saída não significa exposição de todos os eventos capturados.

## Como interpretar os erros locais

O contador de 44 edições locais inválidas contém 40 respostas sem mudança efetiva e quatro tentativas que violaram a regra de substituir apenas invariantes. Não significa 44 JSONs malformados. Todas as 44 mantiveram o candidato idêntico, explicando a igualdade dos contadores. Essas tentativas consomem orçamento e os erros do candidato anterior podem reaparecer no resumo.

A edição localizada aumentou a frequência de mudanças, mas não reduziu os erros de compilação/sintaxe nem as rejeições de integridade. As regiões permitem editar anotações existentes; isso não garante a validade sintática, de tipos ou de preservação segundo o checker.

## Custo e limites da comparação

Tempo de inferência acumulado: full 58,4 min; local 14,4 min. Redução de aproximadamente 73,5% nos tokens de saída. Não atribuir a diferença de velocidade só à interface: full usou NVIDIA L40S e local NVIDIA A100 80GB PCIe.

Sessões registradas: full 2h20min, incluindo 25,2min de carga do modelo; local 5h44min, incluindo 2h06min de carga. Preparação compartilhada: 31,5min, separada desses tempos. Os tempos não incluem fila Slurm. O local teve cerca de 3h29min de processamento contabilizado contra 1h54min full, apesar de inferência mais curta; a infraestrutura e as verificações merecem análise separada antes de concluir qual braço é mais rápido.

O resultado mais forte é uma melhora observada de reparo e redução de repetição com edição localizada. Não há controle sem internals nesta comparação. Três sucessos ocorreram sem internals disponíveis; nos dois restantes as correções também são coerentes com os diagnósticos normais. Portanto, ainda não há evidência causal de benefício dos internals. Uma única seed e cinco sucessos são evidência exploratória.

Próximo teste recomendado: manter a edição localizada e os mesmos candidatos/diagnósticos, comparando com e sem internals, de preferência na mesma classe de GPU e com sementes pareadas. Sem criar ou executar esse teste nesta análise.
