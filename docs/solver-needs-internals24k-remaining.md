# Completar os 362 casos com a configuração original 24k/50x3

Este lote executa os 362 IDs de `configs/solver-needs-tasks-remaining362.json`,
sem repetir os primeiros 100. As listas juntas cobrem os 462 casos Verus/Z3 do
benchmark do artigo, não os 468 registros da extração mais ampla.

Usa exatamente `configs/solver-needs-qwen14b-internals24k.json`:

- Qwen2.5-Coder-14B-Instruct, mesma revisão;
- contexto total 49.152, até 24.576 tokens de internals e reserva de saída 4.096;
- até 50 grupos e três instanciações por grupo;
- temperatura 0,7, top-p 0,8, top-k 20 e semente 20261018;
- quatro propostas totais, como na configuração original;
- mesmos parâmetros de captura/replay; o coletor usa seu padrão histórico de
  até quatro eventos salvos por grupo, dos quais no máximo três são enviados.

O teto de quatro não muda o resultado acumulado até a terceira proposta. Para
a análise principal, compare as três primeiras propostas de ambos os lotes.
O job também registra a quarta para preservar a configuração de origem.

## Referência e verificações

O script exige a execução original concluída de 100 tarefas em
`results/solver-needs-qwen14b-100-internals24k/seed-20261018`.
Confere que a configuração local coincide com a configuração salva e congela
o system prompt do primeiro pedido de controle. Confere também o formato das
mensagens comuns, catálogo e identidades das ferramentas Verus/Z3.

Não copia candidatos ou eventos desses 100 para os 362: são problemas diferentes.
Cada novo candidato é preparado normalmente e verificado para obter seus próprios
diagnósticos e replays. Os dois braços, com e sem internals, são executados.
As quatro checagens de validação publicadas no dataset não são repetidas.

A referência e seus hashes ficam registrados em `settings_reference` no manifesto.
O manifesto também registra a versão atual da implementação: preservar parâmetros
e prompt não significa restaurar automaticamente todo o código de uma versão antiga.
Nenhum resultado anterior é sobrescrito.

## Executar

Atualize `solver_needs_study/`, `scripts/`, `tests/` e mantenha as versões atuais
de `configs/`, `repair_study/` e `prompts/`. Faça isso após encerrar jobs ativos
e seus relatórios. Configurações de 32k não são usadas neste lote.

```bash
cd /home/mariana.soares/code_verification_git
mkdir -p logs
bash scripts/submit_solver_needs_internals24k_remaining.sh
```

Se a referência estiver em outra pasta, forneça destino e referência:

```bash
bash scripts/submit_solver_needs_internals24k_remaining.sh \
  results/solver-needs-qwen14b-remaining362-internals24k/seed-20261018 \
  /caminho/para/solver-needs-qwen14b-100-internals24k/seed-20261018
```

O script agenda preparação CPU, execução dos dois braços em uma GPU e relatório,
com QoS `high`. O limite GPU é 24 horas. Resultados:

```text
results/solver-needs-qwen14b-remaining362-internals24k/seed-20261018/
```

Para retomar o job GPU, mantendo o código que preparou esse estudo:

```bash
sbatch scripts/slurm/solver_needs_run.slurm results/solver-needs-qwen14b-remaining362-internals24k/seed-20261018
```

Após uma retomada, atualize o relatório:

```bash
python3 -m solver_needs_study compare --study results/solver-needs-qwen14b-remaining362-internals24k/seed-20261018
```

## Agregar os 462 casos de 24k

O analisador pode somar os 100 originais e os 362 novos, rejeitando IDs duplicados:

```bash
sbatch scripts/slurm/solver_needs_analysis.slurm \
  --initial results/solver-needs-qwen14b-100-internals24k/seed-20261018 \
            results/solver-needs-qwen14b-remaining362-internals24k/seed-20261018 \
  --expanded results/solver-needs-qwen14b-100-internals24k/seed-20261018 \
  --output analysis/solver-needs-24k-462
```

Nesse relatório, `initial` significa os dois lotes de 24k agregados, não a
configuração antiga de 12k. O bloco separado `internals24k` repete apenas os
100 originais para referência. Use as linhas das propostas 1–3 na análise.
