# Dois experimentos pareados de reparo com internals relevantes

## O que está sendo comparado

1. `full`: internals selecionados por relevância; resposta = arquivo Verus inteiro.
2. `local`: mesmo pacote e candidato no primeiro reparo; resposta = edição JSON
   de UMA região de prova. O código aplica a edição e valida o arquivo completo.

Não há nova geração inicial. São reutilizados candidatos `attempt_00` falhos
do Coder da execução anterior. Ambos usam o mesmo original, candidato,
diagnóstico, ferramentas e payload inicial congelado. Depois do primeiro
reparo as trajetórias podem divergir: cada novo candidato gera seus próprios
diagnósticos e replay. Não se fornece feedback antigo como se fosse atual.

É um piloto padrão de 30 tarefas, não uma nova taxa sobre os 150 problemas.
`--count 0` na preparação permite todas as tarefas inicialmente falhas elegíveis.
Não usa soluções de referência, resultados de reparos futuros ou dificuldade
presumida para selecionar tarefas.

## Mais contexto e mais eventos, abaixo de 96k

- Contexto total: 49152 tokens (48k), saída reservada: 4096.
- Pacote de internals: até 24576 tokens (24k), com metadados e contexto-fonte.
- Até 24 quantificadores distintos e quatro instâncias por quantificador.
- No máximo dois grupos de representação e dois de background não relacionado.
- Uma primeira rodada prioriza diversidade (uma instância por grupo); as
  rodadas seguintes acrescentam outras instâncias até os limites.
- Nenhuma fórmula ou arquivo-fonte é cortado. Se o pacote mínimo não couber,
  o caso é registrado como erro de infraestrutura, sem mudar o orçamento.
- O mesmo payload é selecionado para caber nos prompts das DUAS interfaces,
  mesmo quando uma delas usa menos tokens.

Modelo/revisão e sampling iguais ao C: Qwen2.5-Coder-14B-Instruct BF16,
temperature 0.7, top_p 0.8, top_k 20, seed 20261018; dois reparos por caso,
com seeds 20261019 e 20261020 em ambos. Sem tentativas extras escondidas.

48k exige extensão de contexto: YaRN estático fator 2, base 32768, sem editar
os arquivos do modelo. O motor usa chunked prefill de 2048 tokens, uma sequência
por vez, sem quantização e sem offload CPU. A alocação real do cache precisa
passar na inicialização do vLLM no cluster. Não foi validada localmente na L40S.
As duas condições usam exatamente a mesma configuração de contexto/memória.

Referências da configuração:
https://huggingface.co/Qwen/Qwen2.5-Coder-14B-Instruct#processing-long-texts
https://docs.vllm.ai/en/v0.8.5/serving/engine_args.html

YaRN pode alterar a geração mesmo em prompts curtos. A comparação causal entre
os DOIS novos braços controla esse fator; comparar com resultados antigos de
32k não isola somente a seleção de internals.

## Relevância: regras simples e auditáveis

A captura original continua usando o proxy transparente do Verus. Para cada
candidato, reexecuta no máximo a primeira consulta SAT/UNKNOWN em API isolada
Z3 4.12.5, com cinco segundos e limite externo de 20 s. Não muda a aceitação:
somente Verus + integridade do candidato completo decidem sucesso.

Ordem de prioridade dos grupos, calculada ANTES do limite do pacote:

1. qid começando por `user_candidate`: anotações do candidato, por convenção
   observada nesta ferramenta.
2. qid contendo `candidate` e não classificado como representação: definições
   do candidato.
3. qids relacionados às operações no trecho de falha: Seq/Vec/index/len/update
   para acessos, aritmética/mod/div para operações aritméticas.
4. Outros grupos de background.
5. Representação: box/unbox, raw_ptr, fuel e has_type, com cota pequena.

São heurísticas pelo nome, não análise semântica ou prova de relevância. Não
se interpreta o número de um qid como linha do programa. Uma biblioteca pode
ser relevante e um quantificador do candidato pode não ajudar.

O novo worker observa toda a busca e mantém um reservatório de até 128 grupos,
com até quatro eventos distintos por grupo. Um grupo tardio mais prioritário
pode substituir um grupo de pior prioridade: corrige o viés dos primeiros 200
eventos. Eventos individuais maiores que 64000 caracteres são omitidos inteiros.
Contagens por qid continuam sendo registradas mesmo após atingir os tetos.

`source_context` acrescenta as primeiras quatro localizações de erro do Verus,
a linha correspondente e linhas vizinhas. Não reconstrói o objetivo lógico
nem estabelece automaticamente correspondência entre a consulta e essa linha.
Não envia a consulta SMT inteira. As sete estatísticas anteriores ficam em
um objeto compacto, junto do resultado/motivo do replay. Só expõe eventos se
o resultado do replay coincidir com o original. Divergências são explícitas.

## Seleção dos 30 candidatos

Seleciona apenas `attempt_00` com fracasso e integridade válida, do mesmo modelo
Coder/revisão. Exige pelo menos uma região reconhecida para permitir a comparação.
Isso exclui alguns candidatos sintaticamente inválidos, provas com formas não
suportadas e alterações indevidas de implementação. A conclusão vale para
esse subconjunto, não para todos os fracassos do benchmark.

Divide candidatos em quatro estratos com base somente nos dados da tentativa
inicial: eventos do candidato omitidos, incompletude aritmética, outros casos
SMT e falhas de compilação com integridade válida. Embaralha cada estrato com
seed fixa e intercala os estratos. Os IDs, motivos e hashes são congelados
antes de qualquer reparo. A preparação revalida candidato e integridade;
se uma seleção deixou de ser falha válida, interrompe em vez de substituí-la
silenciosamente. Nenhuma escolha usa sucesso posterior como critério.

## Edição localizada

O modelo recebe o mesmo original/candidato/diagnóstico/payload e uma lista
`editable_sites`, com ID, tipo, offsets, linha e texto existente.

Resposta exata:

```json
{"site_id":"R1","replacement":"invariant\n    i <= n,\n    0 <= i,\n"}
```

Esse exemplo apenas ilustra o formato. Os pontos disponíveis são:

- `loop_invariants`: substituir a lista de invariantes de um `while` ou
  inseri-la se ausente. A condição, corpo e decreases não fazem parte da região.
- `proof_block`: substituir um bloco `proof { ... }` existente.
- `insert_proof`: inserir exatamente um bloco `proof { ... }` antes de um
  statement reconhecido, sem substituir o statement.

O reconhecedor é lexical e conservador, não um parser Verus completo. Evita
comentários/strings e não adivinha casos ambíguos, como invariante com `if {}`.
Não cobre todos os `for`, formas complexas ou locais possíveis. Verus e Lynette
continuam obrigatórios mesmo quando a edição passa pela checagem de formato.
O prefixo/sufixo fora da região são preservados mecanicamente.

JSON inválido, site inexistente, saída vazia, texto extra fora de um proof
block e edição sem mudança efetiva consomem uma tentativa e são registrados.
Nesse caso, o candidato fica igual; o próximo reparo recebe o erro de edição.
Não se gera novamente fora do orçamento. A limitação de uma região por resposta
pode atrapalhar provas que precisem de mudanças em vários pontos; `region_id`,
`editable_site_count` e erros de edição ficam registrados para examinar isso.

O braço full também detecta igualdade de tokens e informa ausência de progresso
na tentativa seguinte. Mudanças apenas de comentários/espaços não contam.

## Executar os dois jobs

Envie `repair_study/`, `prompts/repair-study/`, `configs/repair-study-48k.json`,
os scripts novos e `tests/test_repair_study.py`. Mantenha as versões atuais
de `baseline/`, `diagnostics/` e `scripts/cluster/`, incluindo a correção IPC.
Se não tiver certeza, atualize essas pastas também. Não precisa recompilar
Verus ou baixar outro modelo.

Na raiz do projeto no cluster:

```bash
cd /mnt/users/mariana.soares/code_verification
bash scripts/submit_repair_study.sh
```

Esse comando SUBMETE quatro jobs:

1. Preparação CPU: seleciona/revalida/congela os 30 candidatos e o primeiro
   feedback. Não carrega pesos do modelo; abre somente o tokenizer local.
2. Experimento full: uma GPU, dependente do sucesso da preparação.
3. Experimento local: outra GPU, mesma dependência. Os dois ficam elegíveis
   simultaneamente; o Slurm decide quando há recursos para executá-los.
4. Comparação CPU após os dois jobs terminarem, mesmo que algum tenha falhado,
   para mostrar casos ausentes em vez de ocultá-los.

Origem padrão:
`results/qwen25coder14b-c-internals-150/seed-20261018/full/instruct`.
Destino padrão: `results/paired-repair-study-48k/seed-20261018`.

Para escolher origem, destino e quantidade:

```bash
bash scripts/submit_repair_study.sh \
  results/qwen25coder14b-c-internals-150/seed-20261018/full/instruct \
  results/paired-repair-study-48k/run-01 30
```

Use `0` no último argumento para todas as tarefas inicialmente falhas elegíveis.
Não extrai o ZIP automaticamente: a origem é a pasta de resultados já presente
no cluster. Os arquivos anteriores permanecem intactos.

Os jobs GPU pedem uma GPU, 8 CPUs, 64 GB e 24 h cada. Para retomar somente um:

```bash
sbatch --job-name=verus-repair-full scripts/slurm/repair_study_run.slurm \
  results/paired-repair-study-48k/seed-20261018 full
```

Troque `full` por `local` para retomar o outro. Reutilize os mesmos arquivos e
configurações. Se mudar código/prompts/modelo/entrada, use outro destino.

## Saídas e leitura dos resultados

- `manifest.json`: IDs, estratos, hashes de todos os arquivos congelados,
  modelo/configuração, binários e biblioteca Z3 API.
- `inputs/ID/`: candidato e original congelados, diagnósticos revalidados,
  consulta capturada, replay e payload inicial comum.
- `full/ID/repair_01/` e `local/ID/repair_01/`: request, resposta, prompt,
  `payload-used.json`, arquivo aplicado, Verus, integridade e resultado.
- `repair_02/`: segunda tentativa, quando necessária, com feedback atualizado.
- `full/summary.json`, `local/summary.json`: sucessos após um/dois reparos,
  repetições, erros de edição, compilação/sintaxe, integridade, tokens e tempo.
- `comparison.md` e `comparison.json`: resultados pareados, casos exclusivos,
  ausentes e confirmação de igualdade do payload do primeiro reparo.

O sucesso tem denominador de candidatos inicialmente falhos selecionados.
Não chamar de taxa sobre 150 problemas nem comparar com os 19 sucessos iniciais
como se fossem novas soluções. Ambos os braços têm somente dois reparos.
O custo da preparação/replay inicial é compartilhado e salvo à parte; tempos
de inferência/Verus e feedback posterior são registrados por braço. Sessões
registram tempo de carregamento e parede, inclusive em retomadas.

Não é uma ablação de internals versus ausência deles: os dois braços recebem
internals. Mede principalmente o efeito da interface de edição. Comparar o
full com o C antigo é exploratório, pois seleção, contexto, instruções e
feedback mudaram. Um controle sem internals exigiria um terceiro braço.

## Validação

Testes locais cobrem preservação fora da região, recusa de JSON inválido,
strings/comentários, ambiguidade de regiões, ranking de eventos tardios,
igualdade dos dados de entrada, detecção de ausência de progresso, retomada
sem gerar/verificar de novo, hashes congelados e callback real do Z3 isolado.
Não executamos os jobs, o benchmark ou a inferência real de 48k localmente.
