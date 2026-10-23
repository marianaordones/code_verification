# Ablação de internals: análise detalhada — 22/10/2026

Fonte: `download_2026-10-22_15-51-32.zip`. Análise dos artefatos salvos;
nenhuma inferência, execução do Verus ou execução do Z3 foi realizada.
`audit.json` contém as contagens reconstituídas; `examples/` contém os candidatos
iniciais, candidatos finais bem-sucedidos e seus diffs por braço. `audit.py`
permite repetir a análise do ZIP.

## Conclusão principal

O pacote atual de internals não melhorou a taxa agregada de reparo nesta
execução: 7/114 com internals contra 8/114 sem eles. Há um caso exclusivo com
internals, mas dois exclusivos sem eles. Não há base para afirmar superioridade
de nenhum braço: somente três pares têm desfechos diferentes e existe uma
única semente de execução. O resultado negativo se refere ao modelo, formato,
seleção, orçamento e estados de prova testados, não à utilidade geral de
informação interna de SMT.

Os eventos adicionais alteraram muitas respostas e reduziram repetições, mas
isso não se converteu em mais provas. Alterar uma resposta não demonstra que
o modelo extraiu uma informação relevante dos eventos.

## Validade da comparação

- Os dois braços concluíram os mesmos 114 candidatos inicialmente falhos.
- Conferimos os 570 hashes de arquivos congelados.
- Conferimos os 114 pares de requests iniciais: candidato, semente, parâmetros,
  regiões editáveis e sistema são iguais; o texto do usuário difere somente
  pelo bloco de internals nos 75 casos em que esse bloco existe.
- Nos outros 39 casos, os prompts iniciais são idênticos.
- O braço de controle não recebeu bloco de internals nos requests auditados.
- Um único modelo foi carregado em uma NVIDIA L40S, em uma única sessão.
- Todos os 15 registros de sucesso (sete mais oito) têm Verus aprovado e
  integridade válida. Correspondem a nove problemas distintos.
- Não houve saídas truncadas ou timeouts de verificação nas tentativas.

Essa é uma avaliação de reparo dos 114 candidatos selecionados, não uma nova
taxa de sucesso de geração sobre os 150 problemas do VerusBench.

## Resultados

| Métrica | Com internals | Sem internals |
|---|---:|---:|
| Sucessos | 7/114 (6,14%) | 8/114 (7,02%) |
| Sucessos até o primeiro reparo | 4 | 6 |
| Sucessos até o segundo reparo | 7 | 8 |
| Tentativas | 224 | 222 |
| Sem alteração efetiva, incluindo edição recusada | 46 (20,54%) | 59 (26,58%) |
| Erros de compilação | 86 | 90 |
| Erros de sintaxe | 16 | 12 |
| Tentativas com E0308 | 53 | 47 |
| Problemas com alguma tentativa E0308 | 35 | 30 |
| Problemas com alguma tentativa de sintaxe inválida | 10 | 8 |
| Tokens de entrada | 2.629.566 | 1.430.461 |
| Tokens de saída | 19.098 | 18.691 |
| Inferência acumulada | 19,47 min | 14,34 min |
| Processamento acumulado registrado | 77,61 min | 69,81 min |

O braço com internals usou aproximadamente 83,8% mais tokens de entrada,
35,7% mais tempo de inferência e 11,2% mais processamento contabilizado.
O carregamento compartilhado foi de 25,3 minutos; a sessão durou cerca de
2h54min, sem incluir fila Slurm. Não somar a carga do modelo duas vezes.

Os contadores de integridade não representam mudanças indevidas na
implementação: foram 16 `unparseable` com internals e 14 sem, e zero
classificados como `invalid`. Ambos tiveram 208 registros de integridade
válida. Erros de sintaxe podem simultaneamente impedir o checker de analisar
o arquivo; essas contagens se sobrepõem.

As 46 edições recusadas com internals foram 40 sem mudança efetiva e seis que
violaram a restrição de substituir apenas os invariantes. As 59 sem internals
foram 54 sem mudança, quatro com essa violação e uma que não era exatamente
um bloco de prova. Não foram 46/59 JSONs malformados.

## Sobreposição de sucessos

Seis problemas foram reparados por ambos:
`mbpp_task_id_760`, `mbpp_task_id_557`, `mbpp_task_id_457`,
`mbpp_task_id_477`, `mbpp_task_id_145` e `cloverbench_cal_div`.

Exclusivo com internals: `mbpp_task_id_8`.

Exclusivos sem internals: `misc_trigger` e `mbpp_task_id_472`.

Em 105 problemas nenhum braço resolveu. A união dos sucessos é nove,
mas obter essa união usa o custo dos dois braços e não corresponde ao mesmo
orçamento de duas tentativas de uma configuração isolada.

### mbpp_task_id_8: melhor caso para investigação mecanística

O programa constrói o vetor dos quadrados. O candidato inicial não preservava
explicitamente no loop os limites do índice e a hipótese que garante que o
quadrado de cada entrada cabe em i32. O diagnóstico inicial já apontava
postcondição de comprimento, preservação de invariante e possível overflow.

Com internals:

1. Adicionou `0 <= index <= nums.len()`; a prova continuou falhando.
2. Acrescentou ao invariante a condição aritmética já existente no `requires`:
   `forall|k: int| 0 <= k < nums.len() ==> (0 <= #[trigger] nums[k] * #[trigger] nums[k] < i32::MAX)`.
   Verus e integridade aprovaram.

Sem internals, o primeiro reparo usou o nome de retorno `squared` dentro do
loop, onde ele não está em escopo. No segundo, removeu as expressões inválidas
e voltou essencialmente aos invariantes iniciais, sem corrigir a prova.

O pacote com internals reportava `unknown`, incompletude aritmética, axiomas
de multiplicação, comprimento/indexação e representação. Não continha grupos
de anotações do candidato, inclusive no reparo bem-sucedido. Portanto, existe
uma solução exclusiva, mas não uma ligação demonstrada entre uma instância
interna específica e a correção. O diagnóstico de overflow e a pré-condição
original já davam pistas suficientes. O dado adicional pode ter ajudado a
focar aritmética, mas também pode apenas ter alterado a amostragem.

### mbpp_task_id_472: problema semelhante com resultado inverso

O programa verifica elementos consecutivos; o erro também incluía overflow.
Sem internals, o modelo preservou no loop a hipótese original sobre
`arr[i] + 1` caber em i32, resolvendo na primeira tentativa.

Com internals, acrescentou `arr[index] + 1 == arr[index + 1]` como invariante:
primeiro houve E0308; depois de corrigir o cast, a propriedade falhou antes e
depois do loop. A condição que o programa está justamente verificando não
pode ser presumida para o próximo par ainda não examinado.

O pacote era predominantemente de biblioteca e representação, sem anotações
do candidato. Aqui o tratamento não levou ao mesmo reparo simples e correto
observado em `mbpp_task_id_8`. A comparação dos dois exemplos enfraquece uma
interpretação causal baseada apenas no sucesso exclusivo do primeiro.

### misc_trigger: correção útil presente, mas erro extra impede sucesso

Sem internals, o modelo acrescentou `assert(f(arr@, i as int));` antes da
assertion já existente e verificou. Com internals, também acrescentou essa
assertion, mas adicionou uma expressão de bounds que o Verus não conseguiu
analisar. A segunda tentativa continuou com erro sintático. Os dados extras
não eram instâncias do quantificador de `f`; eram axiomas genéricos de
aritmética, comprimento, indexação e representação.

Esse caso não demonstra incapacidade de identificar a assertion útil: ela
apareceu nos dois braços. Mostra que ruído ou erros adicionais podem anular
um reparo conceitualmente adequado. Não reconstruímos nem revalidamos uma
versão corrigida manualmente; a análise usa somente os resultados salvos.

## O que realmente foi exposto

- 125 feedbacks com internals disponíveis, em 78 problemas distintos.
- 117 replays com motivo `(incomplete quantifiers)` e oito com
  `(incomplete (theory arithmetic))`.
- Todos esses 125 pares de resultados original/replay eram `unknown`.
  Não são contagens de todas as consultas capturadas ou de problemas distintos.
- Tempo de solver reportado nesses replays: mínimo 0,020s, mediana 0,108s,
  máximo 0,299s. Esses dados não apontam esgotamento do timeout diagnóstico;
  não descrevem necessariamente o custo de toda a chamada original do Verus.
- 1.312 grupos e 2.019 instâncias enviados, somados entre feedbacks.
  Os tetos observados por feedback foram 19 grupos e 30 instâncias totais.
- O maior prompt com internals teve 31.688 tokens de entrada; o controle,
  9.693. Não há evidência de que aumentar de novo o contexto resolva o gargalo.

Distribuição dos grupos enviados:

| Tipo | Grupos |
|---|---:|
| Anotações do candidato | 46 |
| Definições do candidato | 12 |
| Biblioteca relacionada às operações, por heurística | 768 |
| Outros axiomas de fundo | 248 |
| Representação | 238 |

Anotações mais definições do candidato são somente 58/1.312 = 4,42% dos
grupos. Contagens repetem fórmulas que reaparecem em feedbacks diferentes.
Isso não torna os axiomas de biblioteca inúteis: expõe a distância entre uma
classificação lexical como “relacionado a array” e um sinal útil para o reparo.

Dos 75 candidatos inicialmente com internals disponíveis, apenas 17 receberam
grupos de anotações do próprio candidato; 20 receberam anotações ou definições.
Nos 17 com anotações, ambos os braços resolveram um, `mbpp_task_id_457`.
Portanto, mesmo o subconjunto com esse sinal não mostrou ganho nesta semente.

O código escolhe a primeira consulta `sat`/`unknown` capturada. O pacote
declara que o alinhamento consulta–localização da falha não foi estabelecido.
Um programa com vários erros pode receber o contexto-fonte de mais de uma
falha e internals de apenas uma consulta. Resultado concordante no replay não
prova que seus eventos explicam a obrigação que o modelo tenta reparar.

## Controle negativo e variabilidade

Nos 39 prompts iniciais idênticos, 37 respostas textuais e candidatos aplicados
foram idênticos. `diffy_brs5` e `diffy_brs4` produziram respostas e alterações
distintas apesar do mesmo prompt e semente. Nenhum gerou diferença de sucesso
final entre os braços. A origem da variabilidade não foi diagnosticada;
não atribuímos automaticamente a um kernel específico. Ainda assim, isso mostra
que igualdade de semente não garantiu identidade absoluta nesta infraestrutura.

Três candidatos inicialmente sem internals passaram a recebê-los no segundo
reparo do tratamento: `mbpp_task_id_798`, `misc_bubble` e `mbpp_task_id_424`.
Nenhum foi resolvido. Os quatro sucessos do grupo inicialmente sem dados
permaneceram sem internals no reparo bem-sucedido em ambos os braços.

## Próximo passo proposto: evidência antes do treinamento enriquecido

Não recomendo outra execução de 114 problemas apenas aumentando contexto ou
adicionando eventos. O próximo objetivo deve ser verificar se o pacote contém
um sinal operacional interpretável e se o modelo consegue aproveitá-lo.

1. Auditar semanticamente alguns estados congelados: começar por `mbpp_task_id_8`
   após o primeiro reparo, `mbpp_task_id_472`, `misc_trigger` e casos dos 17 com
   anotações. Conferir a obrigação da consulta, o quantificador de origem, o
   trigger, os bindings e a cláusula. Não usar ausência em uma amostra limitada
   como prova de que uma instância nunca ocorreu.
2. Preparar feedback curto, determinístico, sem LLM auxiliar: poucos grupos
   ligados ao candidato, suas instâncias e somente as pontes de biblioteca
   necessárias. Preservar guardas/polaridades e indicar mapeamentos desconhecidos.
   O código completo, diagnósticos e política de edição ficam iguais.
3. Fazer um piloto pequeno com estados fixos e várias sementes pareadas. Três
   condições ajudam a separar conteúdo de perturbação: sem internals, internals
   relevantes e um controle de internals não relacionados com comprimento
   semelhante e mesma estrutura. O último é um controle experimental, não um
   diagnóstico confiável para uso normal; rotular os resultados separadamente.
   Resultado/motivo do solver podem ser mantidos em todas as condições para
   isolar especificamente estatísticas e instanciações. Essa fronteira precisa
   estar definida antes da execução.
4. Usar primeiro os casos auditáveis como exploração, incluindo os exemplos
   selecionados porque divergem neste resultado; não apresentá-los como teste
   independente. Confirmar um sinal positivo em outros problemas/sementes.
   A seleção dos demais casos deve depender dos dados de entrada, não de qual
   braço já sabemos que resolve.
5. Se o 14B não aproveitar um sinal que um humano consegue explicar com
   clareza, testar um modelo mais capaz apenas como controle de capacidade,
   com a mesma ablação. Isso pode distinguir representação ruim de limitação
   do modelo; não garante que LoRA transferirá a habilidade ao 14B.

Sucesso deve continuar significando Verus + integridade. Menos repetições,
menos contadores ou menos mensagens de erro não substituem esse critério.
O uso de algumas sementes não torna cada tentativa um problema independente;
o pareamento e a incerteza devem respeitar o agrupamento por problema.

## Relação com SAFE + internals

A hipótese “o modelo sem treino aproveita internals” é diferente de “um modelo
treinado com internals pode aprender a aproveitá-los”. O resultado atual não
refuta a segunda. Também não justifica ainda enriquecer e treinar todo o SAFE
sem um controle que meça o valor desses dados.

O SAFE oficial tem aproximadamente 11 mil exemplos de geração e 14 mil de
debugging. O enriquecimento faz mais sentido nos inputs de candidatos falhos
que chegam ao solver; erros de compilação não devem receber eventos inventados.
Para cada exemplo, coletar somente da tentativa falha, sem usar a solução-alvo
na seleção de internals. Verificar compatibilidade da versão do Verus e manter
os problemas de avaliação fora do conjunto de treinamento.

Quando avançar ao fine-tuning, manter o mesmo conjunto de exemplos, saída,
hiperparâmetros e orçamento entre SAFE convencional e SAFE enriquecido. Uma
comparação útil é treinar dois adaptadores e avaliar cada um com/sem internals;
isso distingue domínio Verus aprendido de uso efetivo dos dados do solver.
Não comparar SAFE completo com um subconjunto enriquecido sem controlar a
mudança de exemplos. O formato de saída do SAFE e o JSON de edição localizada
também devem ser alinhados; o ganho de uma mudança de interface não pode ser
atribuído aos internals.

Referências primárias:

- Dataset: https://huggingface.co/datasets/microsoft/Verus_Training_Data
- Instanciação e extração de informações: https://z3prover.github.io/papers/z3internals.html
- Quantificadores: https://microsoft.github.io/z3guide/docs/logic/Quantifiers/
