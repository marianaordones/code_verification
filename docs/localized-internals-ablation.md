# Edição localizada: com e sem internals

Esta execução compara o pacote de internals, mantendo a interface de edição
localizada em ambos os braços. Usa todos os candidatos iniciais congelados
do estudo anterior; a pasta `all-eligible` enviada em 22/10/2026 contém 114.
Não gera candidatos iniciais novos nem importa os cinco reparos bem-sucedidos.

## O que fica igual

- Qwen2.5-Coder-14B-Instruct, mesma revisão fixada e BF16.
- Mesmos arquivos iniciais, originais, diagnósticos e integridade, verificados
  pelos hashes do manifesto anterior.
- Contexto de 49.152 tokens, saída reservada de 4.096, até dois reparos.
- Mesmos parâmetros de amostragem e sementes: 20261019 no primeiro reparo,
  20261020 no segundo, como no estudo anterior.
- Mesmo prompt de sistema, incluindo o guia de interpretação dos internals,
  mesmo contexto-fonte e mesmo contrato JSON de edição localizada.
- Mesma aplicação mecânica, Verus e checker de integridade. Erros e ausência
  de mudança consomem tentativas; não existem novas tentativas escondidas.

O primeiro candidato/feedback vem de `inputs/`, não de `local/` ou `full/`.
O código valida os arquivos usados contra o manifesto anterior. Não exige que
o código atual tenha o mesmo hash do código histórico: não estamos retomando
a execução antiga, apenas importando seus dados congelados. Os binários e a
biblioteca Z3 API precisam ser os mesmos do estudo congelado.

## A diferença entre os braços

`with_internals`: recebe, quando disponível, o pacote selecionado por relevância:
estatísticas, quantificadores, instâncias e metadados do replay, incluindo
resultado/motivo e limites de amostragem. Não recebe a consulta SMT completa.
O teto permanece 24.576 tokens de feedback, até 24 quantificadores distintos e
quatro instâncias por grupo, respeitando contexto e reserva de saída. A checagem
final usa o prompt desta ablação e remove instâncias inteiras se necessário.

`without_internals`: não recebe esse bloco, nem valores, fórmulas, resultado,
motivo, disponibilidade ou metadados de amostragem do replay. Recebe os mesmos
diagnósticos normais do Verus e contexto extraído do código. O guia de sistema
explica expressamente que ausência do bloco não implica ausência de instâncias
ou um resultado específico do solver.

Quando não há internals disponíveis, o bloco é omitido também no primeiro braço.
Para um mesmo candidato e diagnósticos, os prompts são então idênticos. É um
controle útil, embora a mesma semente não garanta determinismo bit a bit em GPU.

Depois do primeiro reparo, candidatos e diagnósticos podem divergir. Só o braço
com internals reexecuta o replay diagnóstico para seu novo candidato. O controle
continua sem replay API; ambos capturam as consultas da verificação em disco,
para auditoria, sem enviá-las ao modelo.

Esta comparação mede a contribuição do pacote completo de feedback do solver,
não separa o efeito de cada contador ou das instâncias individualmente.

## Organização do job

Um único job GPU carrega o modelo uma vez e executa os dois braços. A ordem
alterna por candidato: com/sem, depois sem/com. Cada braço termina seus até
dois reparos daquele candidato antes de executar o outro. Isso evita comparar
uma L40S com uma A100, como ocorreu na execução anterior, e compartilha o custo
de carregamento. Não são dois jobs GPU simultâneos.

Os resultados ficam separados por braço. Uma retomada reutiliza requests,
respostas e resultados concluídos; casos ausentes permanecem explícitos.
A classe da GPU é parte do fingerprint: se o Slurm colocar uma retomada em
outra classe, o programa recusa misturar os resultados. Uma retomada pode
usar outra placa física da mesma classe; a identidade e o tempo de cada sessão
ficam registrados. Uma única semente continua sendo evidência exploratória.

## Arquivos para atualizar no cluster

Copie os novos arquivos:

- `local_ablation/`
- `prompts/local-ablation/`
- `scripts/submit_local_ablation.sh`
- `scripts/slurm/local_ablation_prepare.slurm`
- `scripts/slurm/local_ablation_run.slurm`
- `scripts/slurm/local_ablation_compare.slurm`
- `tests/test_local_ablation.py`

Mantenha as versões atuais de `repair_study/`, `prompts/repair-study/`,
`prompts/v4/`, `configs/repair-study-48k.json`, `baseline/`, `diagnostics/` e
`scripts/cluster/`. Estes arquivos existentes não foram alterados para esta
ablação. Não é necessário recompilar Verus nem baixar outro modelo.

Preserve no cluster a pasta anterior:
`results/paired-repair-study-48k/all-eligible`.
O importador precisa do `manifest.json` e dos cinco arquivos de cada `inputs/ID/`:
`candidate.rs`, `original.rs`, `verification.json`, `integrity.json`, `payload.json`.
Os resultados antigos permanecem intactos. O launcher não extrai ZIPs.

## Executar

Na raiz do projeto no cluster:

```bash
cd /mnt/users/mariana.soares/code_verification
bash scripts/submit_local_ablation.sh
```

Esse comando submete:

1. Preparação CPU: testes e cópia/validação dos inputs congelados. Não executa
   Verus, replay ou inferência.
2. Um job GPU após o sucesso da preparação, contendo ambos os braços.
3. Comparação CPU após o job GPU terminar, inclusive se ele falhar ou for
   interrompido, para mostrar pendências. O job GPU também compara ao finalizar.

O job GPU pede uma GPU, 8 CPUs, 64 GB de RAM e 24 horas. O contexto de 48k já
foi inicializado na L40S no estudo anterior; ainda não executamos esta ablação.
Tempos de fila, carga do modelo e verificação podem variar.

Para escolher pastas diferentes:

```bash
bash scripts/submit_local_ablation.sh \
  results/paired-repair-study-48k/all-eligible \
  results/localized-internals-ablation-48k/run-01
```

Destino padrão:
`results/localized-internals-ablation-48k/seed-20261018`.

## Retomar e ler os resultados

Para retomar após limite de tempo ou falha, sem mudar código/configuração:

```bash
sbatch scripts/slurm/local_ablation_run.slurm \
  results/localized-internals-ablation-48k/seed-20261018
```

Se a retomada falhar por classe de GPU diferente, consulte `run.json` e use o
mecanismo de seleção de GPU disponível no cluster para pedir a classe original.
Não há uma constraint inventada no script, pois não conhecemos os nomes de
features configurados no Slurm. Não misture silenciosamente classes na mesma run.

Para regenerar somente a comparação, sem GPU ou execução de solver:

```bash
python3 -m local_ablation compare \
  --study results/localized-internals-ablation-48k/seed-20261018
```

Arquivos principais no destino:

- `manifest.json` e `inputs/`: origem, hashes, ferramentas, config e candidatos.
- `with_internals/` e `without_internals/`: cada tentativa com request, payload
  realmente exposto, resposta, candidato aplicado, Verus e integridade.
- `run.json` e `session-*.json`: ambiente, classe/identidade da GPU, custo
  compartilhado de carga do modelo e duração das sessões.
- `comparison.md` e `comparison.json`: sucesso pareado, casos exclusivos,
  repetições, erros, tokens, ausentes e validação do primeiro par.

O relatório separa os candidatos com e sem internals disponíveis inicialmente.
No estudo importado são 75 e 39, respectivamente. Olhe especialmente os 75
em que o primeiro reparo realmente recebe informação adicional. O grupo dos 39
não estabelece que internals nunca ficarão disponíveis: depois de corrigir uma
compilação, por exemplo, o braço com internals pode obter replay no segundo reparo.

`first_pair_check_passed` exige todos os requests iniciais presentes e iguais
em candidato, contexto comum, sementes, parâmetros e regiões. O controle não
pode expor internals. `first_prompts_identical` é esperado quando não há dados
disponíveis; com internals disponíveis, espera-se diferença somente nesse bloco.
`withheld_by_design` não deve ser contado como falha de captura.

Taxas usam os candidatos inicialmente falhos selecionados como denominador;
não são taxas novas de geração sobre 150 tarefas. Custos de modelo/sessão são
compartilhados e não devem ser somados duas vezes.
