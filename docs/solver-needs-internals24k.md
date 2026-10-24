# Solver Needs: primeiros 100 casos, internals de até 24k

Esta variante repete a comparação com e sem internals nos mesmos 100 IDs de
`configs/solver-needs-tasks100.json`. Não inclui os 362 casos complementares.

| Parâmetro | Valor |
|---|---:|
| Contexto total | 49.152 tokens |
| Orçamento do bloco de internals | 24.576 tokens |
| Grupos de quantificadores | Até 50 |
| Instanciações por grupo | Até 3 |
| Reserva para saída | 4.096 tokens |
| Propostas por tarefa e braço | 4 |

A configuração é `configs/solver-needs-qwen14b-internals24k.json`. Somente o
orçamento de internals, o teto de grupos e o identificador do experimento mudam
em relação à configuração anterior. Modelo, revisão, prompt, sementes, temperatura,
ações e política de relevância permanecem iguais. Os dois braços usam a mesma
configuração de geração; o braço sem internals continua omitindo o bloco.

São limites máximos: o empacotador conta tokens com o tokenizer real e respeita
tanto os 24.576 tokens do bloco quanto o contexto total com reserva de saída.
Não há garantia de receber 50 grupos nem todas as três instanciações. A seleção
continua limitando axiomas genéricos e de representação. Os limites de captura
e replay não foram ampliados: até três consultas falhas, cinco segundos de replay
por consulta e reservatório de 128 grupos com até quatro eventos salvos por grupo.

## Execução

Espere execuções anteriores terminarem, incluindo os relatórios, antes de
atualizar o código no cluster. A validação de hashes não permite mudanças durante
execução ou retomada. Preserve a versão antiga se precisar retomar os estudos antigos.

Atualize `solver_needs_study/`, `configs/`, `scripts/` e `tests/`. Mantenha
`prompts/solver-needs/system.txt` disponível; o conteúdo do prompt não mudou.

```bash
cd /mnt/users/mariana.soares/code_verification
bash scripts/submit_solver_needs_internals24k.sh
```

O script agenda preparação CPU, uma execução GPU com os dois braços e relatório,
com QoS `high`. O modelo é carregado uma vez na sessão GPU. A preparação gera
novos diagnósticos e replays; não reutiliza os resultados nem os eventos da
execução anterior, portanto não garante traces de busca idênticos aos anteriores.
O arquivo do candidato inicial é reconstruído da mesma fonte e dos mesmos IDs.

Resultados separados:

```text
results/solver-needs-qwen14b-100-internals24k/seed-20261018/
```

`selected_ids.json` e `selection.json` registram as tarefas. O `manifest.json`
congela a configuração nova e os hashes. O job GPU lê a configuração desse
manifesto; não é preciso passar o orçamento novamente na retomada.

```bash
sbatch scripts/slurm/solver_needs_run.slurm results/solver-needs-qwen14b-100-internals24k/seed-20261018
```

Para atualizar o relatório após uma retomada:

```bash
python3 -m solver_needs_study compare --study results/solver-needs-qwen14b-100-internals24k/seed-20261018
```

O limite GPU continua sendo 24 horas, com uma GPU e 64 GB de RAM. O orçamento
maior pode aumentar a duração por proposta; a execução salva respostas e resultados
para retomada. A preparação continua executando apenas o candidato com a assertion
removida, sem repetir as quatro checagens publicadas no dataset.

## Interpretação

A auditoria anterior encontrou folga no contexto de 48k, mas omissões de grupos
do candidato pelo orçamento de 12k. Esta variante testa um pacote mais amplo.
Como orçamento e teto de grupos aumentam juntos, o resultado mede o efeito dessa
combinação; não isola qual desses dois limites causou uma eventual melhora.
Mais eventos enviados não implicam necessariamente mais reparos corretos.
