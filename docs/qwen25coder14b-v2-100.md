# Qwen2.5-Coder-14B-Instruct: 100 tarefas

Experimento independente, sem comparação thinking/nonthinking. Prompt v2,
BF16, uma GPU, uma geração inicial e até dois reparos com feedback do Verus.
100 IDs sorteados sem reposição dentre os 150, semente 20261018, sem filtro de
dificuldade. Lista congelada em data/pilot-qwen25coder14b-v2-100.json.

Modelo Qwen/Qwen2.5-Coder-14B-Instruct, revisão
`aedcc2d42b622764e023cf882b6652e646b95671`.
Sampling preserva a configuração nonthinking anterior: temperatura 0.7,
top-p 0.8, top-k 20, até 4096 tokens, um candidato. O template do modelo
é usado sem parâmetro enable_thinking. Até 300 gerações no total.

Atualize baseline/, configs/, data/, prompts/, scripts/ e, opcionalmente, tests/.
Espere jobs que estejam usando o código antigo terminarem antes de substituí-lo.
O ambiente e as ferramentas já preparados são reutilizados. O novo modelo será
baixado na primeira execução, em pasta própria, sem symlinks.

```bash
cd /mnt/users/mariana.soares/code_verification
mkdir -p logs
sbatch scripts/slurm/qwen25coder14b_v2_100.slurm
```

Recursos: high_performance, QOS high, uma GPU, 8 CPUs, 64 GB de RAM e 24 horas.
Resultados: results/qwen25coder14b-v2-100/seed-20261018/pilot/instruct/.
O relatório report.md e as métricas summary.json ficam nessa pasta.
Logs: logs/verus-coder14-v2-100-ID.out e .err.
Para retomar após timeout, reenvie o mesmo job sem alterar código/configuração.
Tentativas persistidas são reutilizadas. Não inicia outra execução de 150 tarefas.

Os resultados anteriores são preservados em outras pastas. Como a seleção agora
contém 100 tarefas, uma comparação posterior com o piloto de 50 deve considerar
apenas IDs comuns e as diferenças entre modelos/configurações.
