# Análise parcial do piloto Qwen3-8B

Fonte: `download_2026-10-18_20-56-48.zip`, analisado sem executar seu conteúdo.
O estado abaixo corresponde ao ZIP, não a uma consulta ao job ainda ativo.
As execuções `smoke/` foram separadas das execuções `pilot/`.

## Estado observado

O thinking tem 15 tarefas concluídas, com três tentativas por tarefa (45 tentativas).
O non-thinking tem três tarefas concluídas, duas tentativas completas da quarta
(`diffy_s4lif`) e somente o request da terceira tentativa dessa quarta tarefa.
As demais 11 tarefas não têm resultados nesse arquivo e não são contadas como falhas.

| Medida | Thinking | Non-thinking parcial |
|---|---:|---:|
| Tarefas concluídas | 15/15 | 3/15 |
| Tarefas com pelo menos uma tentativa concluída | 15 | 4 |
| Tentativas concluídas | 45 | 11 |
| Tarefas resolvidas entre as concluídas | 0/15 | 0/3 |
| Success@0 / @1 / @2 entre tarefas concluídas | 0% / 0% / 0% | 0% / 0% / 0% |
| Candidatos aceitos pelo Verus | 0 | 0 |
| Respostas truncadas | 2/45 (4,4%) | 5/11 (45,5%) |
| Tokens gerados | 127.754 | 21.605 |
| Tokens de raciocínio registrados | 116.729 | 0 |
| Tokens finais registrados | 10.981 | 21.605 |
| Inferência média por tentativa | 70,1 s | 49,7 s |
| Inferência mediana por tentativa | 48,4 s | 7,8 s |
| Velocidade agregada de geração | 40,5 tokens/s | 39,5 tokens/s |
| Tempo de inferência acumulado | 52,6 min | 9,1 min |
| Tempo de Verus acumulado | 15,1 min | 3,7 min |
| Tempo ativo dos componentes | 67,7 min | 12,9 min |
| Carga/inicialização do modelo registrada | 25,0 min | 28,7 min |

Os limites e categorias das tarefas diferem entre essas amostras parciais. As médias
brutas não estabelecem uma vantagem entre modos. Custo por tarefa resolvida está
indefinido porque nenhuma tarefa foi resolvida; não deve ser registrado como zero.
Success@3 e @5 não foram medidos.

Thinking: tempo médio por tarefa 4,51 min; mediana 4,26 min. A sessão completa
registrou 94,8 min incluindo carga do modelo, processamento e overhead. Somente os
componentes somados (inferência, Verus e integridade) totalizaram 67,7 min.
Uma extrapolação mecânica de 150 tarefas × 6 tentativas à média observada seria
22,6 horas de componentes ativos, sem fila/carga/interrupções. Isso não prevê
sucesso nem garante que os reparos seguintes tenham a mesma duração.

## Categorias: thinking completo

| Categoria | Resolvidas / concluídas |
|---|---:|
| CloverBench | 0/2 |
| Diffy | 0/4 |
| MBPP | 0/7 |
| Misc | 0/2 |

## Diagnóstico dos fracassos

Ao ler o primeiro erro efetivo do compilador por tentativa thinking, encontram-se
32 erros de sintaxe, 12 outros erros de compilação e uma falha de pós-condição.
Assim, 44/45 candidatos falharam antes de chegar a uma prova bem formada.

Exemplos:

- `cloverbench_array_copy_strong`: invariantes são colocados dentro do corpo do
  `while`, e aparece `variant len - n`, produzindo erro de sintaxe.
- `diffy_brs5`: usa formas como `forall k: usize` e `if ... then ... else`, que o
  Verus rejeita nesse código. Os dois reparos ainda retornam formas inválidas.
- Em 25 tentativas a guarda lexical detectou alteração dos imports; nos exemplos
  inspecionados, o modelo omitiu `use vstd::prelude::*`, e o compilador não encontra
  a macro `verus` ou tipos/funções usados pelo código.
- A única tentativa thinking que passou pela integridade é
  `misc_basic_nonlinear/attempt_02`. O corpo contém somente uma explicação em
  comentários; a pós-condição continua sem prova.
- Thinking gasta aproximadamente 91,4% dos tokens gerados em raciocínio. Esse
  raciocínio não se converteu em código Verus aceito nesta amostra.

No non-thinking, os seis candidatos das duas tarefas CloverBench passam pela
integridade, mas falham nas obrigações de prova. Quatro desses seis candidatos
repetem os tokens da entrada original sem acrescentar uma prova. Os dois reparos
restantes de array_copy também não resolvem as obrigações.

Em `diffy_brs5` e nas duas tentativas disponíveis de `diffy_s4lif`, non-thinking
chega a 4096 tokens e termina com código incompleto. O exemplo inspecionado gera
longas repetições de comentários `// Loop invariant: ...`, sem anotação formal
correspondente. Isso explica a média de tempo muito maior que a mediana.

## Qualidade das métricas do pipeline

O campo atual `error_type` registrou 31 erros syntax e 14 verification no thinking.
Essa classificação é imprecisa: o classificador toma a existência do resumo
`verification results:: 0 verified, 0 errors` como sinal de erro de verificação,
mesmo quando o stderr reporta falha de compilação. Somente uma das 45 tentativas
mostrou uma falha efetiva de pós-condição.

O campo `invalid_modification` marcou 44/45 tentativas thinking. Ele mistura:

- 25 rejeições por mudança nos imports;
- 18 falhas de parsing do comparador;
- 1 panic do Lynette ao ler um candidato inválido.

Portanto, 97,8% é a frequência de rejeição pela checagem atual, não uma estimativa
confiável da frequência de alterações semânticas indevidas. No non-thinking,
cinco candidatos truncados provocaram panic do parser. Esses casos precisam ser
separados de alterações semânticas em uma análise científica. Como nenhum candidato
passou no Verus, essa imprecisão não explica o total de zero soluções aceitas.

## Comparação somente das três tarefas já concluídas nos dois modos

As tarefas pareadas são array_copy_strong, array_sum_strong e diffy_brs5.

| Medida | Thinking | Non-thinking |
|---|---:|---:|
| Resolvidas | 0/3 | 0/3 |
| Tentativas | 9 | 9 |
| Tokens gerados | 25.425 | 13.413 |
| Tempo de inferência | 10,5 min | 5,7 min |
| Tempo dos componentes | 13,4 min | 8,9 min |
| Respostas truncadas | 0/9 | 3/9 |

Nesse subconjunto, non-thinking custa menos em geração, mas trunca mais; nenhum
modo resolveu uma tarefa. Três tarefas não sustentam a escolha definitiva.

## Recomendação

Preservar esta execução como piloto diagnóstico e terminar o protocolo planejado
sem trocar prompts, seeds ou limites no meio. Não iniciar o baseline de 150 tarefas
com base nesses resultados.

O gargalo observado é a geração de sintaxe/anotações Verus utilizáveis. Antes de
atribuir os fracassos à ausência de informações SMT, é necessário distinguir
compilação, prova e integridade. A correção da classificação pode ser feita sobre
os logs existentes, sem regenerar candidatos.

Caso se decida melhorar as instruções de sintaxe Verus, isso deve ser um novo
prompt versionado e um novo piloto nos dois modos, com resultados separados.
Não corrigir automaticamente os candidatos desta execução nem misturar resultados
depois de alterar o prompt. Não escolher um modo com base apenas no custo quando
nenhum dos dois demonstrou resolver tarefas.
