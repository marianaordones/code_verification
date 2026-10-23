# Experimento B com contexto de 96k

Replica o B nos 150 problemas, mas permite 98304 tokens totais:
até 94208 de entrada, reservando os mesmos 4096 tokens de saída.
A contagem de inclusão da consulta e o motor vLLM usam o mesmo limite.
Mantém modelo/revisão, BF16, prompt v4, seed, sampling, uma geração inicial,
até dois reparos, ferramentas, integridade e política de seleção da primeira
consulta completa de falha que caiba. Consultas não são cortadas ou reduzidas.
Tentativas sem consultas continuam recebendo somente os diagnósticos disponíveis.

## Ajustes para contexto longo

O modelo é configurado para 32768 tokens por padrão. A recomendação oficial
para textos maiores é YaRN com fator 4 e comprimento original 32768:
https://huggingface.co/Qwen/Qwen2.5-Coder-14B-Instruct#processing-long-texts

O código passa `rope_scaling` ao vLLM, sem editar os arquivos locais do modelo.
O limite efetivo deste experimento continua sendo 98304, não 131072.
YaRN estático também afeta prompts curtos: os textos da geração inicial são
iguais aos do B, mas não se deve exigir respostas iniciais idênticas. Portanto
não é uma comparação em que somente os tokens expostos nos reparos mudam.

Para a L40S usada anteriormente, configura 12 GiB de offload de pesos para a
RAM, preservando BF16 e uma GPU. O cache KV permanece na precisão padrão,
sem quantização. Usa chunked prefill com blocos de até 2048 tokens para
limitar memória temporária no processamento dos prompts. Esses ajustes ficam
registrados na configuração e no fingerprint da execução.

Documentação dos parâmetros na versão usada:
https://docs.vllm.ai/en/v0.8.5/serving/engine_args.html

O offload transfere pesos entre CPU e GPU durante a inferência e pode aumentar
bastante o tempo de execução. Não há redução automática do contexto ou da
precisão se faltar memória. A capacidade real de cache é validada pelo vLLM
ao inicializar no cluster; os testes locais não substituem essa validação.

## Transferência e execução

Envie as pastas atualizadas `baseline/`, `configs/`, `scripts/` e `tests/`.
Mantenha `diagnostics/z3_probe.py`, `diagnostics/__init__.py`, `prompts/v4/`,
`data/`, o modelo em `.cluster/models/` e os binários preparados.
Não é necessário recompilar ou baixar os pesos novamente.

```bash
cd /mnt/users/mariana.soares/code_verification
mkdir -p logs
sbatch scripts/slurm/qwen25coder14b_b_96k_150.slurm
```

Slurm: uma GPU, 8 CPUs, 64 GB de RAM e limite de 24 horas, mesma partição/qos.
O job executa os testes de ferramentas/captura e os testes da configuração
96k antes de carregar o modelo. Os testes da configuração usam um motor
simulado; a inicialização subsequente valida a alocação real do cache.

Resultados novos, sem reutilizar candidatos do B anterior:

`results/qwen25coder14b-b-96k-150/seed-20261018/full/instruct/`

Consulte `report.md`, `summary.json` e `solver/exposure.json` de cada tentativa.
Este último registra `context_limit: 98304` e a consulta selecionada ou a
omissão. Os requests/prompts completos continuam salvos para auditoria.

Se o job atingir 24 horas, reenvie o mesmo comando sem alterar arquivos ou
configuração para retomar. Não use o diretório do experimento anterior:
o fingerprint muda com os fontes e com a configuração de contexto.

A auditoria anterior indicou cobertura potencial de 164/261 feedbacks em 96k.
Isso é uma referência dos candidatos antigos; respostas diferentes podem
alterar as consultas e a cobertura na nova execução.

Os testes locais cobrem configuração, parâmetros enviados ao motor e inclusão
integral de uma consulta maior que 32k. Não foi executada inferência real de
96k localmente.
