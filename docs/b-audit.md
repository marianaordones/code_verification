# Auditoria offline do experimento B

Esta análise executa somente os passos 1 e 2: classifica tentativas sem
consultas e mede o contexto necessário para incluir consultas completas.
Não reduz consultas, não executa Verus/Z3, não carrega pesos nem gera respostas.
Os resultados originais permanecem intactos.

Envie `diagnostics/b_audit.py` e `scripts/slurm/audit_experiment_b.slurm`.
Mantenha o runtime, o tokenizer do Coder em `.cluster/models/` e os resultados
do experimento B já existentes. Na raiz do projeto no cluster:

```bash
cd /mnt/users/mariana.soares/code_verification
mkdir -p logs
sbatch scripts/slurm/audit_experiment_b.slurm
```

O job usa CPU, 8 GB e até 2 horas. Reutiliza a inicialização e o cache Python
da infraestrutura existente sem pedir GPU. O tokenizer é aberto apenas de
arquivos locais. Não baixa modelos. Se o tokenizer não estiver disponível,
salva a classificação, informa o erro e não inventa contagens de tokens.

Saída: `analysis/b-audit-ID_DO_JOB/`. Para escolher origem e destino:

```bash
sbatch scripts/slurm/audit_experiment_b.slurm \
  results/qwen25coder14b-b-150/seed-20261018/full/instruct \
  analysis/b-audit-01
```

Escolha uma pasta de saída nova e fora dos resultados. Não precisa repetir
o experimento B. O tempo depende principalmente do volume dos arquivos SMT.

## Arquivos produzidos

- `report.md`: resumo da classificação e cobertura por tamanho de contexto.
- `summary.json`: métricas e eventuais erros detalhados.
- `missing-queries.csv`: uma linha por tentativa sem consultas, com categoria,
  códigos de erro Rust, cabeçalhos de diagnóstico, integridade e indicação
  de feedback de reparo preparado.
- `query-token-budgets.csv`: tokens do prompt completo para cada consulta
  candidata, reserva de saída, contexto total necessário e hash da consulta.
- `repair-context-coverage.csv`: contexto mínimo por feedback e a primeira
  consulta que caberia em cada contexto, mantendo a política do experimento B.

A classificação distingue captura com erro, timeout externo, sintaxe, E0308,
outras falhas de compilação, sucesso sem consultas, falha de verificação sem
consultas e casos sem classificação segura. Sintaxe e E0308 são sinais dos
diagnósticos salvos; outras causas não são adivinhadas. Integridade válida
não é tratada como indicação de que a compilação passou.

A medição usa o tokenizer e chat template do modelo sobre as mensagens reais
salvas na tentativa seguinte. Substitui somente o bloco de informação SMT
por uma consulta completa e soma a mesma reserva de saída (4096 tokens).
Inclui original, candidato, diagnósticos, instruções e delimitadores.
Não estima tokens por caracteres e não trunca a consulta.

São avaliados contextos de 32768, 49152, 65536, 98304 e 131072 tokens.
São tamanhos hipotéticos para medir cobertura, não garantias de suporte do
modelo ou de viabilidade na GPU. A cobertura considera apenas feedbacks
de reparo salvos, incluindo os sem consulta (que continuam sem cobertura
em qualquer tamanho). O crescimento de contexto não altera as gerações
anteriores nesta análise; uma execução nova pode produzir outros candidatos.

Se uma requisição de reparo estiver ausente ou não reconhecer o bloco salvo,
o caso será registrado em `errors`, sem reconstrução aproximada.

Para executar apenas a classificação com Python 3 padrão, sem transformers:

```bash
python3 -m diagnostics.b_audit --skip-tokenization --output analysis/b-audit-classification
```

Testes locais com dados simulados: `python3 -m unittest discover -s tests -p test_b_audit.py -v`.
