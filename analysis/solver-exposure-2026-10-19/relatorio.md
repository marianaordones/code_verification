# Análise do estudo de exposição — job 6082

Arquivo analisado: download_2026-10-19_19-30-13.zip. Leitura de dados apenas,
sem execução do conteúdo. Todos os cinco candidatos reais estavam disponíveis;
não houve chamada ao LLM. São candidatos do v3, não resultados da geração v4.

## SAT confirmado nos controles

O controle aritmético retornou SAT por CLI e API. O get-value informou x=0,
(>= x 0)=true e (> x 0)=false. O modelo satisfaz a hipótese e viola o objetivo.
As duas assertions foram avaliadas como true no modelo pela API.

O controle quantificado também retornou SAT, com interpretação constante f(x)=0,
uma instanciação e quatro eventos smt. Três repetições CLI de cada controle
reproduziram SAT. Isso comprova a funcionalidade de extração para esses controles,
não a obtenção de contraexemplos confirmados em consultas reais do Verus.

## Consultas do Verus

| Caso | UNSAT originais | UNKNOWN originais | SAT originais | Motivo no replay selecionado | Instâncias observadas/salvas |
|---|---:|---:|---:|---|---:|
| Controle Verus aritmético | 2 | 1 | 0 | incomplete quantifiers | 0/0 |
| cloverbench_array_copy_strong | 4 | 2 | 0 | incomplete quantifiers | 104/100 |
| diffy_condn | 4 | 8 | 0 | incomplete quantifiers | 96/96 |
| mbpp_task_id_3 | 4 | 1 | 0 | incomplete (theory arithmetic) | 6/6 |
| mbpp_task_id_170 | 4 | 4 | 0 | incomplete quantifiers | 157/100 |
| misc_arg_free | 6 | 3 | 0 | incomplete quantifiers | 9/9 |

Somando somente os cinco casos reais: 22 UNSAT, 18 UNKNOWN, zero SAT, em 40
checks internos. Não são 40 problemas nem necessariamente 40 obrigações-fonte
independentes: o Verus pode fazer verificações auxiliares e localizar erros.
Foi selecionada uma consulta UNKNOWN de cada caso para os replays detalhados.
As estatísticas e instâncias da tabela não cobrem todas as 18 consultas UNKNOWN.

Os resultados selecionados foram UNKNOWN na captura, na CLI e na API; os três
replays CLI adicionais de cada um também foram UNKNOWN. Isso mostra estabilidade
observada da categoria de resultado, não identidade dos modelos/traces. Os
callbacks completaram sem erros. Os motivos são incompletude, não timeout de
cinco segundos: os replays API normais terminaram aproximadamente entre 0,32 e
1,13 segundo considerando todos os casos Verus.

O controle aritmético simples pelo Verus também retorna UNKNOWN. Sua consulta
inclui axiomas de fundo e opções que o controle SMT direto não inclui. A presença
de quantificadores e a configuração capturada, incluindo mbqi=false, são
compatíveis com a diferença; este experimento não isolou a causa. Não se pode
concluir a partir de UNKNOWN que a obrigação é verdadeira ou falsa.

## O que foi obtido e seus limites

- Consultas SMT completas, parâmetros e retornos originais: disponíveis.
- Estatísticas e motivos: disponíveis nos replays selecionados.
- Modelos: confirmados nos dois controles SAT; nos casos Verus, candidatos não
  validados após UNKNOWN. Não devem ser chamados de bugs ou contraexemplos confirmados.
- Quantificadores, bindings e cláusulas de instanciação: disponíveis; quatro e
  57 instanciações foram omitidas pelos limites nos dois casos maiores.
- Outras inferências: callbacks observaram smt, tseitin, rup e del nos casos
  reais. Nos arquivos salvos de cloverbench há 18 smt e 82 tseitin; diffy_condn
  contém 8 smt e 92 tseitin; mbpp_task_id_170 tem 1 smt e 99 tseitin. Nos outros
  três casos Verus, os 100 eventos salvos dessa categoria são todos tseitin.
- Dependências: as listas dos eventos examinados vieram vazias. Não há grafo
  útil de dependências nem justificativa detalhada de cada inferência de teoria.

A lista de literais de uma cláusula representa disjunção, não uma coleção de
fatos que podem ser usados simultaneamente como assertions independentes.
Hints smt genéricos não são lemas Verus prontos ou provas completas.

## Tamanho

Tokens contados com o tokenizer Coder disponível localmente, sem downloads.
São contagens dos blocos, não de uma conversa com templates e programa completo.

| Caso real | Consulta SMT | Modelo candidato | Instâncias | Outras inferências | Prévia limitada |
|---|---:|---:|---:|---:|---:|
| cloverbench_array_copy_strong | 42673 | 8929 | 83648 | 50395 | 6449 |
| diffy_condn | 41233 | 8084 | 66061 | 42002 | 6824 |
| mbpp_task_id_3 | 7684 | 1690 | 3667 | 429018 | 6214 |
| mbpp_task_id_170 | 79661 | 15375 | 42858 | 43363 | 6917 |
| misc_arg_free | 6611 | 1690 | 5145 | 433874 | 6339 |

Três consultas sozinhas excedem o contexto de 32768 tokens usado na inferência.
Mesmo amostras de 100 eventos podem ser enormes, pois os registros repetem
quantificadores, hints e estruturas do prelude. A prévia cabe mais facilmente,
mas corta expressões/JSON: não é um pacote semanticamente completo pronto para
uso pelo modelo.

## Próximo pacote recomendado

Começar com diagnóstico Verus, status/motivo, estatísticas compactas, poucas
instâncias de quantificadores do usuário e pequena amostra de inferências smt.
Modelo de UNKNOWN deve ser opcional e explicitamente não validado. Preservar os
arquivos brutos para análise, sem colocar tudo no contexto do LLM.

Antes da comparação com LLM, trocar o teto da categoria other_inferences por
tetos por regra (smt, rup, tseitin), dar preferência a qids do usuário quando
identificáveis e impor orçamento em tokens. São filtros determinísticos simples;
não exigem JE nem modelo auxiliar. Não reconstruir dependências ausentes.

O estudo já demonstra viabilidade técnica para um teste controlado de feedback.
Não demonstra que esse feedback melhora as provas. Também não encontrou SAT
em Verus: o próximo teste com LLM deve ser apresentado como feedback sobre
UNKNOWN, e não como reparo guiado por contraexemplo confirmado do benchmark.
