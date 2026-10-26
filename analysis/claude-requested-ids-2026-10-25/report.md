# IDs solicitados: resultados locais com Claude

S1/S2/S3 = sucesso nessa proposta; F = falha final; C1 = sucesso na primeira proposta comum, sem testar reparos;
P/P1 = resposta recebida, avaliação ainda incompleta; — = sem resposta do modelo registrada; IV = já verificava sem modelo.

Pares nas tabelas: **com internals / sem internals**. Dados de preparação sem geração não contam como teste.

## AX

Testados: 4/10.

| Problema | Configuração | Com / sem |
|---|---|---|
| V-329 | Opus 4.8 Low / primeira comum | C1 / C1 |
| VB-18 | Opus 4.8 Low / primeira comum | S2 / S2 |
| VB-30 | Opus 5.5 Low / 60 | F / S1 |
| V-391 | Opus 5.5 Low / 60 | F / F |

**Sem resposta registrada em nenhuma configuração:** V-173, V-15, V-181, V-268, V-140, VB-5.

## INST-forall

Testados: 7/11.

| Problema | Configuração | Com / sem |
|---|---|---|
| V-411 | Opus 5.5 Medium / 6 | S1 / S1 |
| V-411 | Opus 4.8 Low / primeira comum | C1 / C1 |
| V-304 | Opus 4.8 Low / primeira comum | C1 / C1 |
| V-421 | Opus 4.8 Low / primeira comum | C1 / C1 |
| V-430 | Opus 5.5 Low / 60 | S1 / S1 |
| V-341 | Opus 5.5 Low / 60 | S2 / F |
| V-423 | Opus 5.5 Low / 60 | S1 / S1 |
| V-387 | Opus 5.5 Low / 60 | S1 / S1 |

**Sem resposta registrada em nenhuma configuração:** V-325, V-424, VB-21, V-273.

## INST-witness

Testados: 3/10.

| Problema | Configuração | Com / sem |
|---|---|---|
| V-52 | Opus 4.8 Low / primeira comum | C1 / C1 |
| VB-53 | Opus 5.5 Low / 60 | S1 / S1 |
| V-206 | Opus 5.5 Low / 60 | S1 / S1 |

**Sem resposta registrada em nenhuma configuração:** V-139, V-388, VB-32, V-416, V-302, VB-20, V-11.

## FUEL

Testados: 6/9.

| Problema | Configuração | Com / sem |
|---|---|---|
| V-56 | Opus 5.5 Medium / 6 | S1 / S1 |
| V-56 | Opus 4.8 Low / primeira comum | C1 / C1 |
| V-163 | Opus 5.5 Low / 60 | S1 / S1 |
| V-163 | Opus 4.8 Low / primeira comum | C1 / C1 |
| V-362 | Opus 5.5 Low / 60 | S1 / S1 |
| V-361 | Opus 5.5 Low / 60 | S1 / S1 |
| V-161 | Opus 5.5 Low / 60 | S1 / S1 |
| V-229 | Opus 5.5 Low / 60 | S1 / S1 |

**Sem resposta registrada em nenhuma configuração:** V-230, V-221, V-239.

## Other

Testados: 6/10.

| Problema | Configuração | Com / sem |
|---|---|---|
| V-368 | Opus 5.5 Low / 60 | S1 / S1 |
| V-368 | Opus 4.8 Low / primeira comum | C1 / C1 |
| VB-61 | Opus 5.5 Low / 60 | S1 / S1 |
| VB-61 | Opus 4.8 Low / primeira comum | C1 / C1 |
| VB-69 | Opus 5.5 Low / 60 | S1 / S1 |
| V-105 | Opus 5.5 Low / 60 | S1 / S1 |
| V-97 | Opus 5.5 Low / 60 | S1 / S1 |
| V-413 | Opus 5.5 Low / 60 | S1 / S1 |

**Sem resposta registrada em nenhuma configuração:** V-48, V-178, V-129, V-286.

## Additional missing assertion

Testados: 1/1.

| Problema | Configuração | Com / sem |
|---|---|---|
| V-47 | Opus 5.5 Low / 60 | S1 / S1 |

**Sem resposta registrada em nenhuma configuração:** nenhum.

## VerusBench

Testados: 15/50.

| Problema | Configuração | Com / sem |
|---|---|---|
| cloverbench_array_append_strong | Sonnet 5.5 Low / 20 | S1 / S1 |
| cloverbench_array_concat_strong | Opus 5.5 Low / 5 | S1 / S1 |
| cloverbench_array_concat_strong | Sonnet 5.5 Low / 5 | S1 / S1 |
| cloverbench_array_copy_strong | Sonnet 5.5 Low / 20 | S1 / S1 |
| cloverbench_array_product_strong | Sonnet 5.5 Low / primeira comum | C1 / C1 |
| cloverbench_array_sum_strong | Sonnet 5.5 Low / primeira comum | C1 / C1 |
| cloverbench_is_prime | Sonnet 5.5 Low / primeira comum | C1 / C1 |
| cloverbench_two_sum | Sonnet 5.5 Low / 20 | F / S1 |
| diffy_s22if | Opus 5.5 Low / 5 | S1 / S1 |
| diffy_s22if | Sonnet 5.5 Low / 5 | S1 / S1 |
| misc_binary_search | Sonnet 5.5 Low / primeira comum | S2 / S2 |
| misc_fib | Sonnet 5.5 Low / 20 | S1 / S1 |
| misc_filter | Sonnet 5.5 Low / 20 | S3 / S2 |
| misc_findmax | Opus 5.5 Low / 5 | S1 / S1 |
| misc_findmax | Sonnet 5.5 Low / 5 | S1 / S1 |
| misc_len_intersect | Sonnet 5.5 Low / 20 | S1 / S1 |
| misc_map | Sonnet 5.5 Low / primeira comum | C1 / C1 |
| misc_reverse | Sonnet 5.5 Low / primeira comum | C1 / C1 |

**Sem resposta registrada em nenhuma configuração:** diffy_brs3, diffy_brs4, diffy_brs5, diffy_condn, diffy_ms1, diffy_ms2, diffy_ms3, diffy_ms5, diffy_res1o, diffy_s1if, diffy_s1lif, diffy_s32if, diffy_s3if, diffy_s42if, mbpp_task_id_161, mbpp_task_id_240, mbpp_task_id_262, mbpp_task_id_273, mbpp_task_id_290, mbpp_task_id_424, mbpp_task_id_445, mbpp_task_id_476, mbpp_task_id_572, mbpp_task_id_616, mbpp_task_id_618, mbpp_task_id_769, mbpp_task_id_798, mbpp_task_id_94, misc_basic_nonlinear, misc_bubble, misc_conditional_average, misc_linearsearch, misc_remove_all_greater, misc_sum, misc_tail_triangle.

Desses, apenas selecionados/preparados: diffy_s42if, misc_bubble, misc_remove_all_greater.
