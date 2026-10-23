# Análise dos resultados de 19/10/2026

## Correção após auditoria detalhada dos candidatos

As 96 tentativas com E0308 correspondem a 42 problemas distintos. As 65
rejeições de integridade correspondem a 23 problemas; 14 tentativas têm
simultaneamente erro de tipos e rejeição de integridade.

Ao comparar os elementos protegidos, as 61 rejeições com mensagem agregada
são acionadas por atributos adicionados: `#[trigger]` e/ou `#![auto]`, não
por mudanças de imports. São anotações legítimas de controle de quantificadores,
mas o filtro atual bloqueia toda alteração de atributos. Essa rejeição é
excessivamente conservadora; como ocorre antes da comparação AST, não permite
concluir que o restante de cada candidato preserva o programa. É necessário
revalidar os candidatos completos antes de recalcular sucessos.

Uma rejeição AST em cloverbench_array_concat_strong/attempt_02 decorre da
substituição de `if 0 <= n && n < a.len()` por `if n < a.len()`: mesmo redundante
para usize, a remoção altera o código executável e viola a regra estrutural.
As outras três rejeições são misc_havoc_inline_post, cuja entrada oficial já
contém assume; não são três introduções de assume pelo modelo.

Por tentativa, os pares de tipos extraídos dos diagnósticos incluem int/usize
em 64, int/Range<int> em 8, int/Range<usize> em 7 e int/RangeTo<usize> em 7.
Essas contagens se sobrepõem. Há também erros em cascata de elemento versus
Seq e quantificadores com corpo numérico em vez de bool.

A configuração v3 melhora feedback e prompts, mas ainda mantém o bloqueio
genérico de atributos. Ela, por si só, não corrige a rejeição de triggers.
Uma revisão posterior deve permitir somente atributos de prova explicitamente
aprovados, no contexto apropriado, preservando o bloqueio de construções de
confiança e reexecutando a comparação AST e o Verus.

---

Os ZIPs não são execuções independentes. O arquivo 08-09-53 contém o piloto
Qwen3-14B do arquivo 08-09-46 e o experimento Qwen2.5-Coder. As 3370 entradas
compartilhadas são idênticas. Não devem ser somadas como repetições.

Todas as execuções terminaram, sem tarefas pendentes, falhas de infraestrutura
registradas ou respostas truncadas. Usaram L40S e os mesmos hashes de Verus,
Z3 e Lynette. Isso não implica equivalência estatística entre populações de
50 e 100 tarefas.

| Configuração | Tarefas | Sucesso inicial | Após 2 reparos | Tentativas | Inferência média por tentativa |
|---|---:|---:|---:|---:|---:|
| Qwen3-14B thinking | 50 | 2 (4%) | 3 (6%) | 145 | 39,02 s |
| Qwen3-14B nonthinking | 50 | 4 (8%) | 4 (8%) | 142 | 11,55 s |
| Qwen2.5-Coder-14B-Instruct | 100 | 11 (11%) | 14 (14%) | 276 | 12,51 s |

Nas mesmas 50 tarefas, o Coder resolveu 5, contra 4 do Qwen3 nonthinking e
3 do thinking. Coder e nonthinking compartilharam apenas um sucesso; houve
4 sucessos exclusivos do Coder e 3 exclusivos do nonthinking. A vantagem
global de 14% contra 8% envolve populações diferentes e não demonstra
superioridade estatística. O Coder resolveu 1/9 CloverBench, 0/23 Diffy,
11/51 MBPP e 2/17 Misc. Os sucessos concentram-se em MBPP.

## Sintaxe e tipos

A classificação automática de erros é imprecisa: procura `expected` seguido
de crase no texto inteiro, incluindo diagnósticos como `expected int, found
usize`. Portanto confunde erro de tipos com sintaxe.

Uma auditoria dos cabeçalhos de erro, contando tentativas com diagnóstico
explícito de parsing (unexpected token, expected token/braces, unclosed
delimiter), encontrou:

| Configuração | Rótulo automático syntax | Diagnóstico explícito de sintaxe | Tentativas com E0308 |
|---|---:|---:|---:|
| Qwen3 thinking | 86/145 | 81/145 (55,9%) | 5 |
| Qwen3 nonthinking | 82/142 | 72/142 (50,7%) | 10 |
| Coder | 104/276 | 14/276 (5,1%) | 96 |

As categorias auditadas podem coexistir numa tentativa; não são uma partição.
No subconjunto comum de 50 tarefas, o Coder teve 3/140 tentativas com
diagnóstico explícito de sintaxe. Os erros de sintaxe foram bastante reduzidos
no Coder, mas não eliminados; continuam frequentes no Qwen3.

Exemplo de erro de tipos: `a[j as usize]` dentro de expressão de prova em
diffy_brs1; o diagnóstico pede índice int. Isso deve ser tratado como erro de
tipos anterior à prova SMT, não como evidência de falha do solver.

## Integridade e eficácia dos reparos

Tentativas com integridade válida: 33/145 thinking, 54/142 nonthinking e
196/276 Coder. No Coder, 65 tentativas foram inválidas e 15 não puderam ser
parseadas pelo verificador de integridade. Dentre as inválidas, 61 foram
rejeitadas pela política conservadora de preservação de imports, atributos
e macros. Essa mensagem agregada não identifica sozinha qual elemento mudou.

No Coder, 28 tentativas passaram no Verus, mas 14 delas foram rejeitadas
pela integridade. Esses eventos não são 28 tarefas resolvidas. Os 14 sucessos
aceitos exigem simultaneamente Verus e integridade.

Reparos recuperaram 1/48 fracassos iniciais no thinking, 0/46 no nonthinking
e 3/89 no Coder. A recuperação continua baixa. No Coder, 117 tentativas
foram classificadas como falha de verificação e 3 como timeout: há casos
apropriados para estudar feedback além do diagnóstico convencional.

## Próximo experimento recomendado

Usar Coder-14B-Instruct, revisão, prompt v2 e sampling atuais, mantendo
uma geração inicial e dois reparos. Comparar dois braços nas mesmas 100
tarefas: feedback convencional e feedback enriquecido. Manter candidatos
iniciais idênticos nos dois braços; variar apenas o conteúdo do feedback.
Registrar custo adicional de coleta e tamanho do feedback.

Para um piloto mecanístico, congelar os 29 candidatos iniciais do Coder que
passaram na integridade e falharam em verificação. A lista está em
metrics.json, instruct.eligible_initial_verification_failures. Comparar reparos
convencionais e enriquecidos a partir desses mesmos candidatos. Essa seleção
condiciona em falha de prova inicial e deve ser relatada separadamente da taxa
de sucesso no benchmark completo.

Começar com localização da obrigação, condição esperada, invariantes relevantes
e decomposição do erro. O Verus documenta --expand-errors para diagnósticos
mais específicos: https://verus-lang.github.io/verus/guide/checklist.html.
Validar a disponibilidade na revisão antiga fixada antes de implementar.
Isso é feedback ampliado do verificador, não acesso interno ao Z3.

Numa segunda condição, estudar valores de um modelo/contraexemplo associados
às variáveis e hipóteses da obrigação, se a instrumentação da revisão permitir.
Um modelo SMT pode descrever estado abstrato impossível na execução original;
não deve ser apresentado automaticamente como bug concreto do programa.
Logs completos de SMT e perfis de quantificadores devem ser guardados para
análise, resumindo apenas informações ligadas à obrigação que falhou.

Antes disso, corrigir a taxonomia do relatório e reduzir erros de tipos e
alterações de elementos protegidos. Essas mudanças devem ser compartilhadas
pelos dois braços e fixadas antes da comparação. Não há evidência aqui de
que informação interna do solver já melhorou qualquer resultado.
