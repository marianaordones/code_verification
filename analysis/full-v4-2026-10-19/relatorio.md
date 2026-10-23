# Resultado completo v4 — 19/10/2026

Fonte: download_2026-10-19_19-22-40.zip. Execução qwen25coder14b-v4-150, prompt
v4, Qwen2.5-Coder-14B-Instruct na mesma revisão do v3. Não é revalidação de
candidatos antigos. Foram usados os mesmos 150 IDs, a mesma classe de GPU e os
mesmos hashes de Verus, Z3 e Lynette. Nenhum conteúdo do ZIP foi executado.

| Medida | v3 | v4 |
|---|---:|---:|
| Problemas concluídos | 150 | 150 |
| Sucessos iniciais | 13 | 19 |
| Sucessos após um reparo | 15 | 20 |
| Sucessos após dois reparos | 17 | 20 |
| Taxa final | 11,33% | 13,33% |
| Tentativas | 422 | 411 |
| Problemas com algum erro de sintaxe | 9 | 8 |
| Problemas com E0308 | 31 | 29 |
| Tentativas com E0308 | 77 | 60 |
| Integridade válida por tentativa | 339/422 | 370/411 |
| Tentativas inválidas | 56 | 16 |
| Tentativas não parseáveis | 26 | 24 |
| Falhas do checker | 1 | 1 |
| Tentativas com timeout | 0 | 5 |
| Respostas truncadas | 0 | 0 |
| Tentativas aprovadas pelo Verus | 33 | 23 |
| Problemas com alguma tentativa aprovada pelo Verus | 22 | 21 |

O ganho final é de três tarefas (+2 pontos percentuais). Há 16 sucessos comuns,
quatro ganhos e uma perda. Com uma seed e apenas cinco pares discordantes, não
há evidência suficiente de superioridade generalizável. Como prompt e filtro
mudaram juntos, não é possível atribuir causalmente o ganho a um deles.

Ganhos: mbpp_task_id_251, mbpp_task_id_624, mbpp_task_id_741 e mbpp_task_id_95,
todos na tentativa inicial. Perda: misc_arg_free, resolvido após um reparo no v3.

| Categoria | v3 | v4 |
|---|---:|---:|
| CloverBench | 2/11 | 2/11 |
| Diffy | 0/38 | 0/38 |
| MBPP | 14/78 | 18/78 |
| Misc | 1/23 | 0/23 |

## Reparos

No v4, 19 problemas foram resolvidos inicialmente e somente mbpp_task_id_804
foi recuperado no primeiro reparo. Nenhum novo sucesso no segundo. A recuperação
é 1/131 (0,76%), contra 4/137 (2,92%) no v3. O ganho inicial não demonstra que
o mecanismo de reparo melhorou. Os conjuntos de fracassos iniciais também diferem.

## Integridade

Não houve rejeição lexical por adicionar triggers permitidos. As 16 tentativas
inválidas restantes são:
- 6 rejeições estruturais agregadas em macros Verus;
- 5 rejeições em corpos executáveis (3 delas em mbpp_task_id_2);
- 2 remoções de trigger presente no original;
- 3 pela presença de assume na entrada oficial misc_havoc_inline_post.

As três tentativas aprovadas pelo Verus mas rejeitadas pela integridade pertencem
ao mesmo problema, mbpp_task_id_2. Na tentativa inicial, a diferença além dos
invariantes é adicionar `;` a `index += 1` no final do corpo do laço. O comparador
estrutural rejeita a diferença entre expressão final e statement com semicolon.
Isso parece uma restrição excessiva para esse caso de expressão de tipo unit,
não uma mudança do algoritmo. Não foi relaxado o critério nem contado sucesso
automaticamente. As demais rejeições não foram declaradas falsas positivas.

A queda de 33 para 23 aprovações brutas do Verus não mede isoladamente qualidade:
no v3, candidatos aprovados mas barrados pelo filtro podiam ser repetidos nos
reparos. Mesmo contando problemas distintos, o resultado é 22 versus 21. Portanto
o v4 melhora a aceitação conjunta, sem demonstrar aumento da capacidade bruta de
provar obrigações independentemente da integridade.

## Tipos e preparação para feedback SMT

Erros E0308 caíram de 77 para 60 tentativas, mas ainda atingem 29 problemas.
Continuam presentes intervalos em indexação de Seq e conflitos int/usize.
São melhorias parciais; não é correto afirmar que o problema de tipos acabou.

Foram identificados 79 candidatos iniciais com integridade válida e rótulo de
falha de verificação, excluindo diagnósticos de compilador `error[E...]`. A lista
está em metrics.json, v4_audit.initial_valid_verification_failures. Esse critério
é mais estrito que a triagem anterior dos 73 do v3; aplicado retrospectivamente
ao v3, deixa 64. Não se deve comparar 79 e 73 como se fossem o mesmo filtro.
Essa triagem ainda não substitui capturar os resultados SAT/UNSAT/UNKNOWN.

Nenhuma informação interna de SMT foi fornecida nesta execução. O v4 é uma base
operacional mais adequada para comparar feedback convencional e enriquecido a
partir dos mesmos candidatos iniciais, com o mesmo orçamento. Ainda é necessário
separar o efeito da correção da avaliação por revalidação dos resultados antigos.

Tempo ativo acumulado: 14842,7 s no v3 e 13782,7 s no v4. O tempo de sessão foi
17482,2 s e 17761,8 s, respectivamente (aproximadamente 4h51 e 4h56). A média de
tempo por tarefa caiu, mas não houve redução do tempo total de sessão observado.
Não há tarefas pendentes nem task_error registrado; houve uma falha interna do
Lynette em uma tentativa, separada de rejeição de integridade confirmada.
