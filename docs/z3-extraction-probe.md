# Diagnóstico curto de extração do Z3

Este é um experimento separado. Não chama o LLM, não executa o benchmark inteiro
e não envia informação a reparos. A execução normal e os resultados antigos não
são alterados. O objetivo é descobrir quais dados estão disponíveis na prática.

## Executar

Envie a pasta `diagnostics/` e `scripts/slurm/z3_probe.slurm` ao cluster.
Os arquivos de baseline e a preparação existente continuam necessários,
mas não precisam ser substituídos para executar este diagnóstico.

```bash
cd /mnt/users/mariana.soares/code_verification
mkdir -p logs
sbatch scripts/slurm/z3_probe.slurm
```

Por padrão, verifica um único arquivo pequeno, com uma obrigação deliberadamente
falsa, criado apenas para este diagnóstico. Isso não é resultado do VerusBench.
A presença de um quantificador permite observar instanciações, mas o solver pode
simplificar a fórmula; nenhum evento específico é garantido.

Também é possível usar um único candidato real salvo. Este exemplo teve
integridade válida e falha de verificação no v3 enviado:

```bash
sbatch scripts/slurm/z3_probe.slurm \
  results/qwen25coder14b-v3-150/seed-20261018/full/instruct/diffy_condn/attempt_00/candidate.rs
```

O script usa o runtime e os binários já preparados. A reserva de GPU mantém a
inicialização padrão já testada no cluster; não carrega modelo nem usa a GPU
para inferência. O limite do job é de 30 minutos.

## O que acontece

1. Um proxy transparente copia stdin/stdout/stderr do Z3 e encaminha o protocolo
   sem inserir consultas ou mudar opções. Verus também grava SMT e triggers.
2. Os retornos `sat`, `unsat` e `unknown` são associados aos checks de cada
   processo. Se o número não coincide, o programa registra o erro e não adivinha.
3. No máximo duas consultas SAT/UNKNOWN são selecionadas para replays.
4. O replay CLI usa o mesmo executável Z3, solicita modelo, motivo e estatísticas,
   com timeout diagnóstico de cinco segundos.
5. Dois replays na API Python tentam registrar callbacks de cláusulas e instâncias.
   O segundo aplica `rlimit=1` e ativa candidate_models, para investigar UNKNOWN
   induzido por limite. Pode terminar de outra forma; o resultado é registrado.

O wrapper executa em scratch nativo, evitando o problema de executáveis em
filesystem compartilhado. A API exige uma biblioteca: o job tenta instalar
`z3-solver==4.12.5.0` numa pasta isolada em scratch. Isso não modifica os pacotes
de inferência nem substitui o Z3 do Verus. Se a instalação falhar, a captura e o
replay CLI continuam e o worker registra a indisponibilidade da API. O log da
instalação fica em `logs/z3-probe-install-ID.log`.

Para tentar apenas o ambiente já disponível, sem instalar o pacote:

```bash
Z3_PROBE_INSTALL_PYTHON=0 sbatch scripts/slurm/z3_probe.slurm
```

## Arquivos produzidos

Em `results/z3-probe/job-ID/`:

- `report.md` e `report.json`: resultados originais e resultados de cada replay;
- `verus.json`, `verus.stdout.txt`, `verus.stderr.txt`: execução do arquivo;
- `candidate.rs`: cópia da entrada, sem reparos;
- `capture/`: protocolo bruto e argumentos de cada processo Z3;
- `verus-logs/`: SMT e informações de triggers emitidas pelo Verus;
- `query-00/`, `query-01/`: consultas selecionadas e dados abaixo.

Em cada consulta:

| Informação | Arquivos |
|---|---|
| Resultado, limites e identificação | `query.json`, `cli-report.json`, `api/report.json` |
| SMT-LIB e opções originais | `query.smt2`, `prefix.smt2`, `query.json` |
| Modelo | `cli.model.txt`, `api/model.smt2`, se disponível |
| Estatísticas | `cli.statistics.txt`, campo statistics no relatório API |
| Instâncias, quantificador e bindings | `api/instantiations.jsonl` |
| Cláusulas, proof hints e dependências | `api/clauses.jsonl` |
| Perfil simples de quantificadores / erros API | `api-process.json`, stderr |
| Experimento com recurso mínimo | os mesmos arquivos em `api-low-resource/` |

Callbacks agora separam as amostras: até 20 assumptions e até 200 eventos por
categoria restante (instâncias, outras inferências e deleções). As instâncias
também ficam no arquivo específico, e outras inferências em search-inferences.jsonl.
Expressões acima de 8000 caracteres são marcadas como truncadas. Contadores de
eventos observados e omitidos ficam no relatório. Um arquivo vazio significa
ausência de eventos gravados; não demonstra que a interface é inexistente.
Os lemas de teoria aparecem nas cláusulas com seus hints, quando emitidos.
Não há conversão automática deles para lemas Verus.

## Interpretação

- Só os retornos no capture são da chamada original. Os demais são replays.
- O prefixo preserva o contexto lógico incremental, mas não o histórico interno
  de busca entre checks. Não se deve exigir resultado idêntico num replay.
- A biblioteca Python tem a mesma versão 4.12.5, mas é outro build; o caminho e a
  versão são registrados. A API usa um Solver padrão. Se o check original usava
  uma tática explícita, o relatório marca que ela não foi reproduzida pela API.
- O replay de rlimit mínimo é um controle deliberado, não evidência de timeout
  natural do candidato. Candidate model após UNKNOWN não é contraexemplo validado.
- Não são extraídos cores ou provas completas de uma consulta SAT/UNKNOWN.
- Símbolos SMT são preservados; não há mapeamento inferido para variáveis fonte,
  JE, LLM auxiliar ou processamento semântico.
- Se nenhuma consulta SAT/UNKNOWN for capturada, o relatório ainda é escrito e o
  job retorna erro para evitar aparentar sucesso. Verifique os diagnósticos.

Foram validados localmente somente três testes focados do parser/proxy e da
marcação de dados indisponíveis, mais a sintaxe Bash. A extração real precisa
ser executada no cluster. Nenhum resultado de capacidade foi fabricado.

Referências usadas para compatibilidade:
- Verus: revisão `33269ac6a0ea33a08109eefe5016c1fdd0ce9fbd`, config.rs e smt_process.rs.
- Z3 Python: versão `z3-4.12.5`, classe OnClause.
- https://microsoft.github.io/z3guide/programming/Proof%20Logs/
