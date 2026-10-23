# Piloto Qwen3-14B — prompt v2 — 50 tarefas

Esta é a versão solicitada mais recentemente. Mantém thinking e non-thinking,
BF16, uma GPU e geração inicial + até dois reparos; amplia a seleção para 50 IDs.
O modelo, sua revisão, os prompts e o sampling permanecem os do piloto 14B/v2.

## Seleção arbitrária, fixada antes da execução

Não há classificação de dificuldade nem filtro de complexidade. Ordenamos os
150 IDs oficiais e sorteamos 50 sem reposição com `random.Random(20261018).sample`.
A lista final é ordenada por ID para executar nos dois modos na mesma ordem.
Não há exclusões por código, resultados anteriores ou categoria, nem leitura de
soluções de referência. O seed e o hash do inventário ficam no manifest:
`data/pilot-qwen14b-v2-50.json`.

A composição resultante, sem impor cotas, é:

| Categoria | Tarefas |
|---|---:|
| CloverBench | 5 |
| Diffy | 14 |
| MBPP | 23 |
| Misc | 8 |
| Total | 50 |

A seleção inclui `misc_havoc_inline_post`, cuja entrada oficial já contém assume.
Ela é mantida como sorteada, e continua valendo a regra: candidatos com assume são
inválidos. Nenhuma exceção ou remoção foi aplicada depois do sorteio.

## Atualizar e executar

Se já transferiu a versão de dez tarefas, atualize somente:

```text
baseline/benchmark.py
baseline/__main__.py
configs/qwen14b-v2-50-thinking.json
configs/qwen14b-v2-50-nonthinking.json
data/pilot-qwen14b-v2-50.json
scripts/run_experiment.sh
scripts/slurm/pilot14b_v2_50.slurm
```

Se ainda não transferiu a versão 14B/v2, envie também o pacote `baseline/` completo
e `prompts/v2/`. O runtime e as ferramentas já preparados no cluster são reutilizados.
Transfira `tests/` se quiser manter a suíte de testes atualizada. Aguarde jobs antigos
terminarem antes de substituir o código que usam; não cancele nem apague resultados.

```bash
cd /mnt/users/mariana.soares/code_verification
mkdir -p logs
sbatch scripts/slurm/pilot14b_v2_50.slurm
```

Não é necessário reenviar prepare.slurm se o ambiente e as ferramentas já estão
prontos. O cache do modelo 14B é reutilizado se existir; senão será baixado sem
symlinks. Uma GPU, 8 CPUs, 64 GB, high_performance/QOS high, limite de 24 horas.

Monitoramento (troque ID pelo número do job):

```bash
squeue -u "$USER"
tail -f logs/verus-14b-v2-50-ID.out
tail -f logs/verus-14b-v2-50-ID.err
sacct -j ID --format=JobID,State,ExitCode,NodeList,Elapsed
```

## Orçamento e resultados

Até 150 gerações por modo, 300 no total, com parada por sucesso. Thinking:
T=0.6, top-p=0.95, top-k=20, até 8192 tokens. Non-thinking: T=0.7, top-p=0.8,
top-k=20, até 4096 tokens. Seed base 20261018, um candidato por tentativa.

```text
results/qwen14b-v2-50/seed-20261018/pilot/thinking/
results/qwen14b-v2-50/seed-20261018/pilot/nonthinking/
results/qwen14b-v2-50/seed-20261018/pilot/report.md
results/qwen14b-v2-50/seed-20261018/pilot/report.json
```

Para retomar após timeout ou preempção, reenvie o mesmo sbatch com arquivos e
configurações inalterados. Ele reaproveita respostas e tentativas persistidas.
O limite de 24 horas não é uma previsão de duração: se for atingido, reenvie o job.
Os resultados de 8B e do piloto de dez tarefas ficam em outras pastas e não são
misturados nem importados como tentativas desta execução. Os scripts antigos são
mantidos para permitir consultar ou reproduzir experimentos anteriores.

O job gera um relatório de 50 tarefas e para. Não inicia o baseline de 150 tarefas.
A comparação continua sendo entre configurações operacionais completas. A seleção
não foi otimizada por dificuldade; não há garantia de facilidade das provas.
