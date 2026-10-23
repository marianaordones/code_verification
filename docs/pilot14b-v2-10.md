# Piloto Qwen3-14B — prompt v2 — 10 tarefas

Versão anterior mantida para reprodução. A versão atual solicitada usa
[50 tarefas arbitrárias](pilot14b-v2-50.md).

Experimento separado do piloto Qwen3-8B. O job não executa as 150 tarefas.

## Como executar agora

Espere o job antigo terminar antes de atualizar os arquivos usados por ele.
Na raiz do projeto do cluster, atualize:

```text
baseline/                              pacote Python atualizado
configs/qwen14b-v2-thinking.json
configs/qwen14b-v2-nonthinking.json
prompts/v2/                            três prompts novos
data/pilot-qwen14b-v2-10.json
scripts/run_experiment.sh
scripts/slurm/pilot14b_v2_10.slurm
```

O restante do ambiente preparado no cluster é reutilizado: requirements, cache
Python, Verus, Z3 e pacote Lynette. Não apague `.cluster` nem os resultados antigos.
Se quiser executar também a suíte de testes atualizada, transfira `tests/`.

```bash
cd /mnt/users/mariana.soares/code_verification
mkdir -p logs
sbatch scripts/slurm/pilot14b_v2_10.slurm
```

O job pede high_performance, QOS high, uma GPU, 8 CPUs, 64 GB RAM e 24 horas.
Reutiliza o runtime standalone, testa as ferramentas reais, baixa os arquivos do
14B sem symlinks e executa thinking seguido de non-thinking. O primeiro download
do 14B e suas cargas são adicionais; o cache do 8B permanece separado.

Monitoramento (troque ID pelo número retornado):

```bash
squeue -u "$USER"
tail -f logs/verus-14b-v2-10-ID.out
tail -f logs/verus-14b-v2-10-ID.err
sacct -j ID --format=JobID,State,ExitCode,NodeList,Elapsed
```

Resultados:

```text
results/qwen14b-v2-10/seed-20261018/pilot/thinking/
results/qwen14b-v2-10/seed-20261018/pilot/nonthinking/
results/qwen14b-v2-10/seed-20261018/pilot/report.md
results/qwen14b-v2-10/seed-20261018/pilot/report.json
```

Para retomar, reenvie o mesmo sbatch, com arquivos e configs inalterados. Tentativas
e respostas já salvas são reutilizadas. O job para após o relatório comparativo.

## Configuração científica

Modelo: `Qwen/Qwen3-14B`, revisão
`40c069824f4251a91eefaf281ebe4c544efd3e18`, verificada no repositório oficial:
https://huggingface.co/Qwen/Qwen3-14B/commits/main . BF16, tensor parallel 1,
contexto 32768, gpu_memory_utilization 0.90 e max_num_seqs 1. Nenhuma troca
automática para quantização, outro dtype ou contexto menor se faltar memória.
L40S 48 GB é o alvo inicial; capacidade efetiva precisa ser validada no nó.

| Modo | Temperature | Top-p | Top-k | Limite gerado |
|---|---:|---:|---:|---:|
| Thinking | 0.6 | 0.95 | 20 | 8192 |
| Non-thinking | 0.7 | 0.8 | 20 | 4096 |

Uma geração inicial + até dois reparos, um candidato por tentativa. Até 60
gerações no total, com parada antecipada por sucesso. Seed base 20261018 e seed
da tentativa = seed base + índice. As diferenças de sampling e orçamento são
preservadas: compara configurações operacionais, não só o efeito isolado de thinking.

Prompt v2: miniguia de gramática Verus, posicionamento de invariantes, quantificadores,
decreases, imports, wrappers e programa completo. As formas de gramática não são
soluções de tarefas do benchmark. Feedback continua limitado à última saída
convencional do Verus, sem histórico completo nem dados internos do solver.

## Seleção pré-fixada

Interpretação de "10 problemas iniciais": os primeiros dez IDs da lista do piloto
anterior, na ordem já registrada, sem selecionar por sucesso/fracasso ou executar
novo sorteio. O manifest inclui hashes do inventário e da seleção anterior.

1. cloverbench_array_copy_strong
2. cloverbench_array_sum_strong
3. diffy_brs5
4. diffy_s4lif
5. diffy_s5lif
6. diffy_sina2
7. mbpp_task_id_18
8. mbpp_task_id_262
9. mbpp_task_id_414
10. mbpp_task_id_436

Cobertura: CloverBench 2, Diffy 4, MBPP 4, Misc 0. Esses casos já tiveram resultados
analisados com 8B e são conjunto de desenvolvimento; confirmar qualquer melhora
em casos novos antes de generalizar. Como modelo e prompt mudaram juntos, a
comparação com os resultados antigos não isola o efeito do tamanho do modelo.

## Métricas

Success@0/@1/@2 acumulados, tempos, tokens de raciocínio/finais, truncamento,
resultados por categoria e custo por resolvida. Success@3/@5 não são medidos.
Erros de compilação com resumo "0 verified, 0 errors" agora são classificados como
compilação, não falha de prova. Integridade separa valid, invalid, unparseable e
checker_error; parser panic não vira alteração semântica inválida confirmada.
Nenhuma dessas alterações relaxa a aceitação: o candidato precisa passar tanto
no Verus quanto na checagem de integridade.

Validação local inclui testes de configuração, seleção, roteamento do modelo e
prompt, relatório de dez tarefas e classificação de erros. O download dos pesos,
a memória BF16 e o piloto real só podem ser validados no cluster.

Verificação local desta entrega: 29 testes passaram e um teste de ferramentas
reais foi pulado neste Windows. Sintaxe dos 12 scripts Bash/SLURM validada com
`bash -n`; módulos Python também passaram pela compilação de sintaxe.
