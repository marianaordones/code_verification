# Correção de triggers, revalidação e execução v4

## O que mudou

O filtro permite acrescentar `#[trigger]`, `#[trigger(N)]` (N numérico) e
`#![auto]`. Os atributos originais continuam obrigatórios. Novos imports,
outros atributos, construções de confiança e alterações de implementação ou
contratos continuam bloqueados. O candidato completo continua passando pelo
Lynette e pelo Verus, sem remoção de atributos ou transformação do programa.
Não há mudança nos fontes Rust: os binários existentes podem ser reutilizados.

O prompt v4 mantém o original e o feedback de integridade do v3, permite
explicitamente os triggers acima e explica subsequências (`subrange`) em vez
de fatiamento Rust em `Seq`, além de corpos booleanos para quantificadores.
O relatório separa erros de sintaxe dos diagnósticos de tipos E0308 e conta
problemas distintos, sem somar reparos como se fossem novos problemas.

## Transferir

Espere a execução v3 terminar antes de substituir os arquivos usados pelo job.
Envie as pastas `baseline/`, `prompts/`, `configs/`, `scripts/` e `tests/` atualizadas.
Mantenha `data/`, `.cluster/` e os resultados existentes. Não precisa repetir
prepare, compilar o Verus/Lynette ou baixar o modelo novamente.

## Revalidar candidatos v3

Execute na raiz do projeto no cluster:

```bash
cd /mnt/users/mariana.soares/code_verification
mkdir -p logs
sbatch scripts/slurm/revalidate.slurm \
  results/qwen25coder14b-v3-150/seed-20261018/full/instruct \
  results/revalidated-v4/qwen25coder14b-v3-150
```

O job executa primeiro testes reais de preservação e de triggers. Se passarem,
reexecuta Verus e integridade nos candidatos de todas as tarefas concluídas,
sem chamar o modelo e sem modificar a execução original. Os resultados são
gravados em `results/revalidated-v4/qwen25coder14b-v3-150/`:

- `report.md`: resultados e contagens de diagnósticos;
- `summary.json`: métricas e IDs com erros;
- `revalidation-summary.json`: sucessos anteriores/atuais e custo da rechecagem;
- `run.json`: hashes dos candidatos, fontes e ferramentas;
- pastas por tarefa/tentativa: cópia idêntica do candidato e novos diagnósticos.

Para revalidar o v2 de 100 tarefas, use o mesmo script com a origem
`results/qwen25coder14b-v2-100/seed-20261018/pilot/instruct` e outro destino,
por exemplo `results/revalidated-v4/qwen25coder14b-v2-100`.

Tentativas com sucesso Verus mas alteração estrutural continuam inválidas.
Uma tarefa com assume na entrada oficial continua bloqueada pela regra atual;
o benchmark não é editado nem a tarefa excluída.

Tokens e tempos de inferência nos relatórios de revalidação são históricos,
não uma nova despesa de geração. Todas as tentativas salvas são auditadas,
mesmo quando uma tentativa anterior passa a contar como sucesso. Isso não
simula um novo experimento com parada antecipada e reparos diferentes.

Pode retomar uma revalidação interrompida reenviando o mesmo comando. Os hashes
precisam permanecer iguais; se o original ganhar novos resultados, escolha outro
destino. Por isso é preferível esperar a execução original terminar.

## Nova execução completa

Depois da revalidação, execute:

```bash
sbatch scripts/slurm/qwen25coder14b_v4_150.slurm
```

Qwen2.5-Coder-14B-Instruct, revisão fixada anterior, BF16, 150 problemas oficiais,
uma geração inicial e até dois reparos, até 450 gerações. Sampling e limite de
4096 tokens permanecem iguais ao v3. Sem informação interna do solver.
O v4 é independente: não reutiliza tentativas antigas como novas gerações.

Resultados: `results/qwen25coder14b-v4-150/seed-20261018/full/instruct/report.md`.
Logs: `logs/verus-coder14-v4-150-ID.out` e `.err`. O limite é 24 horas; reenvie o
mesmo job sem mudanças para retomar. O relatório final aparece ao terminar.

## Validação local e limite

Testes locais cobrem a lista permitida de atributos, rejeição de atributos
perigosos, preservação dos originais, chamada obrigatória do Lynette, separação
de tipos/sintaxe e revalidação retomável sem alterar a origem nem gerar respostas.
Os testes reais com Verus/Lynette estão no início dos dois jobs e precisam
passar no cluster; essas ferramentas não estão instaladas no ambiente local.

A auditoria lexical local dos ZIPs anteriores consta em
`analysis/trigger-policy-v4/lexical-audit.json`. Passar no filtro lexical não é
um sucesso de verificação: nenhuma taxa de sucesso foi recalculada sem ferramentas.
