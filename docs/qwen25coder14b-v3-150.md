# Experimento completo: Coder-14B / v3 / 150 tarefas

Todos os 150 problemas oficiais, sem sorteio ou exclusões. Uma geração inicial
mais dois reparos, até 450 gerações. Mesmo Qwen2.5-Coder-14B-Instruct, revisão
fixada, BF16, sampling e limite de 4096 tokens do piloto anterior.

Mudanças: prompt v3 com exemplos de tipos/índices em provas, original incluído
em todo reparo e diagnóstico de integridade enviado ao modelo. As rejeições por
imports, atributos e macros identificam os itens removidos/adicionados. O programa
não é corrigido automaticamente, e os critérios de aceitação continuam exigindo
Verus e integridade. O original é somente a entrada oficial, nunca solução de
referência. A classificação do relatório agora procura erros de sintaxe nos
cabeçalhos de erro, sem confundir a nota expected int/found usize com parsing.

Este experimento tem feedback de integridade e prompt diferentes do v2. Não é
uma comparação controlada de modelo nem um teste de informação interna do solver.
As execuções anteriores ficam em suas pastas originais. Mudanças não garantem
eliminação de erros: o resultado deve medir sintaxe, tipos, integridade e provas.

Atualize no cluster baseline/, configs/, prompts/ e scripts/. Mantenha data/ já
existente com os 150 problemas. Atualize tests/ para executar os novos testes.
Espere jobs antigos terminarem antes de substituir arquivos que estejam usando.
Não precisa repetir a preparação nem baixar novamente o modelo já disponível.

```bash
cd /mnt/users/mariana.soares/code_verification
mkdir -p logs
sbatch scripts/slurm/qwen25coder14b_v3_150.slurm
```

Recursos: high_performance/QOS high, uma GPU, 8 CPUs, 64 GB RAM, até 24 horas.
Resultados: results/qwen25coder14b-v3-150/seed-20261018/full/instruct/.
Nessa pasta: report.md, summary.json, candidatos, prompts e diagnósticos por tentativa.
Logs: logs/verus-coder14-v3-150-ID.out e .err.
Após timeout/preempção, reenvie o mesmo comando com arquivos inalterados para
retomar. O relatório final é escrito quando a execução chega ao fim; resultados
por tentativa são persistidos durante o job.

A entrada oficial que já contém assume continua sujeita ao bloqueio conservador;
não há exceções, exclusões ou relaxamento para aumentar artificialmente o sucesso.
