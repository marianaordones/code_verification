# Resultado completo v3 — 19/10/2026

Origem: download_2026-10-19_14-06-32.zip. Configuração confirmada:
Qwen2.5-Coder-14B-Instruct, prompt v3, feedback de integridade, seed 20261018,
150 tarefas, uma geração inicial e dois reparos. Não é resultado da v4 nem
de revalidação. O ZIP foi lido como dados; não foi executado.

## Resultado

- 150/150 concluídas; 17/150 sucessos aceitos (11,33%).
- 13 sucessos iniciais; 15 após um reparo; 17 após dois.
- Reparos recuperaram 4 dos 137 fracassos iniciais (2,92%).
- 422 tentativas, zero truncamentos, 133020 tokens gerados.
- 9 problemas com diagnóstico explícito de sintaxe; 31 com E0308.
- Sintaxe em 27 tentativas e E0308 em 77; as categorias podem coexistir.
- Tempo de sessão: 17482 s (aproximadamente 4h51), incluindo 2325 s de carga.

| Categoria | Sucessos | Total |
|---|---:|---:|
| CloverBench | 2 | 11 |
| Diffy | 0 | 38 |
| MBPP | 14 | 78 |
| Misc | 1 | 23 |

## Comparação com o v2 nos mesmos 100 problemas

| Medida | v2 | v3 |
|---|---:|---:|
| Sucessos finais | 14 | 14 |
| Sucessos iniciais | 11 | 12 |
| Problemas com sintaxe inválida | 7 | 4 |
| Problemas com E0308 | 42 | 18 |
| Tentativas com E0308 | 96/276 | 44/275 |
| Integridade válida por tentativa | 196/276 | 228/275 |
| Candidatos iniciais válidos com falha de verificação | 29 | 50 |

Doze sucessos são comuns, dois exclusivos de cada versão. O v3 ganhou
cloverbench_cal_div e mbpp_task_id_804, mas perdeu mbpp_task_id_557 e misc_trigger.
As mudanças de prompt/feedback melhoram tipos e admissibilidade, mas não o
sucesso final nesse conjunto. Uma única seed limita inferências sobre estabilidade.
Comparar 14% de 100 com 11,33% de 150 diretamente confundiria conjuntos diferentes.

## Integridade

339 tentativas válidas, 56 inválidas, 26 não parseáveis e uma falha do checker
(panic do Lynette em misc_filter_weak, tentativa inicial). Nenhuma tarefa ficou
pendente e não houve task_error de infraestrutura registrado.

Das 56 inválidas:
- 30: adição de trigger bloqueada pelo filtro antigo;
- 20: remoção de trigger já presente no original, que continua proibida;
- 3: alteração do corpo executável;
- 3: assume já existente em misc_havoc_inline_post.

33 tentativas passaram no Verus; 16 foram rejeitadas pela integridade. Estas
16 pertencem a oito problemas, dos quais cinco permanecem sem sucesso aceito:
mbpp_task_id_2, mbpp_task_id_251, mbpp_task_id_477, mbpp_task_id_741 e mbpp_task_id_95.
Não se pode contá-los como sucessos sem executar novamente a comparação estrutural.

## Conclusão

Há melhora de tipos e mais candidatos chegam a falhas de prova genuínas. Em
todo o benchmark, 73 candidatos iniciais têm integridade válida e falha de
verificação. São casos adequados para investigar feedback do solver; ainda não
há evidência de benefício desse feedback, que não foi usado nesta execução.

O próximo passo é revalidar os candidatos com a política v4, preservando o
resultado original, e executar o novo experimento separado. A nova política
permite acrescentar triggers, mas mantém a preservação de atributos originais.
As orientações de subsequências no prompt v4 atacam os erros de intervalos/Seq
restantes. A revalidação mede a correção da avaliação; a execução nova mede a
geração com o novo prompt e feedback. Os efeitos devem ser relatados separadamente.
