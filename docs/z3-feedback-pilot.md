# Piloto de disponibilidade de novos blocos de feedback do Z3

O piloto verifica o conteúdo real de três blocos antes de expô-los ao LLM:

1. cláusulas de teoria e outras inferências que não são instanciações;
2. padrões explícitos acompanhados de exemplos de termos da consulta;
3. inventário/perfil de quantificadores, incluindo fórmulas sem eventos observados.

Não chama o modelo, não executa Verus, não repara programas e não altera resultados
anteriores. Usa consultas SMT já capturadas e processos isolados com a API do
Z3 4.12.5. Não ativa explicitamente `sat.euf`, outro engine ou proof mode para tentar forçar
hints detalhados: sua ausência deve aparecer como resultado do teste.

## Casos e modos

Por padrão, seleciona uma consulta SAT/UNKNOWN salva de cada categoria do estudo
original de 24k: AX, INST-forall, INST-witness, NLA, FUEL e Other. A seleção segue
a ordem do manifesto e exige um único `check-sat` simples. Categorias sem consulta
elegível são registradas, sem inventar dados nem trocar por consultas UNSAT.

Acrescenta quatro controles SMT pequenos: SAT sem quantificadores, UNSAT aritmético,
UNSAT quantificado e quantificador sem um termo de trigger na entrada. O último
não tem resultado pré-fixado nem pressupõe ausência de instanciações.

Cada consulta recebe três repetições em quatro modos:

| Modo | Callback de inferências | `qi.profile` |
|---|---|---|
| baseline | Não | Não |
| callback | Sim | Não |
| profile | Não | Sim |
| combined | Sim | Sim |

Todos usam a mesma biblioteca, consulta e timeout de cinco segundos. Cada replay
tem processo novo; a ordem dos modos é rotacionada entre repetições. O inventário
da entrada é calculado em todos os modos, antes do relógio de `check()`.
Assim, diferenças no tempo de `check()` incluem o custo do callback, serialização
e profiling; tempos de processo são registrados separadamente.

Os resultados da instrumentação são comparados com o baseline do mesmo índice de
repetição. Médias não são usadas para esconder mudanças de resultado: o relatório
mostra todas as categorias retornadas, suas contagens e divergências pareadas.
Mesmo resultado não garante mesma busca. Razões de tempo sobre controles muito
rápidos ou replays interrompidos por limites não são medidas robustas de overhead.

## Executar no cluster

Atualize `diagnostics/`, `scripts/`, `tests/` e, opcionalmente, `docs/`.
Não atualize fontes de código enquanto estudos que validam seus hashes estiverem
ativos. O piloto deve ser lançado da raiz do clone novo:

```bash
cd /home/mariana.soares/code_verification_git
mkdir -p logs
sbatch scripts/slurm/z3_feedback_pilot.slurm
```

É um job CPU, QoS `high`, dois CPUs, 8 GB de RAM e limite de duas horas. Reutiliza
o runtime existente e instala a API Z3 em scratch executável isolado. Não baixa
pesos de modelo nem tokenizer. O tokenizer do Qwen é procurado no cache local
do clone e da pasta antiga; se indisponível, tokens ficam nulos e bytes/caracteres
continuam disponíveis.

Origem padrão:

```text
results/solver-needs-qwen14b-100-internals24k/seed-20261018/
```

Destino padrão:

```text
results/z3-feedback-pilot/job-ID_DO_JOB/
```

Para escolher origem e destino:

```bash
sbatch scripts/slurm/z3_feedback_pilot.slurm \
  results/solver-needs-qwen14b-100-internals24k/seed-20261018 \
  results/z3-feedback-pilot/pilot-01
```

Para retomar com os mesmos parâmetros, repita o comando com o mesmo destino
explícito e a mesma versão do código. Consultas são copiadas com hashes; resultados
de processos já registrados são reutilizados. Falhas registradas permanecem
visíveis. Use outro destino para um novo teste independente.

## Onde estão as respostas

Comece por `report.md` e `report.json` na pasta do piloto. Cada caso também contém:

```text
query.smt2
summary.json
rep-01/baseline/report.json
rep-01/callback/report.json
rep-01/profile/stderr.txt
rep-01/combined/
    input-quantifiers.json
    quantifier-profile.json
    matching.json
    clauses.json
    report.json
    process.json
    stderr.txt
payloads/
    theory_inferences.json
    triggers_and_input_terms.json
    quantifier_profile.json
    other_search_inferences.json
```

As repetições 02 e 03 seguem a mesma estrutura. Os blocos `payloads` são exemplos
montados a partir do primeiro replay combinado concluído; todos os replays continuam
disponíveis. Os custos em tokens referem-se a esses blocos em JSON, não a uma
conversa completa ou a todo o fluxo do solver.

### 1. Campos obtidos, vazios e sem correspondência

O relatório mostra eventos observados por regra, campos obtidos, padrões explícitos
ausentes, linhas sem exemplos de termos da entrada, identificadores de eventos que
não correspondem ao inventário e identificadores ambíguos. Dependências não vazias
são contadas, sem reconstruir um grafo que o callback não forneceu.

### 2. Fórmulas sem eventos observados

O inventário é extraído das assertions carregadas antes da busca. Fórmulas são
associadas a eventos por hash exato ou, separadamente, por qid único. Qids duplicados
são ambíguos; fórmulas transformadas ou geradas internamente podem não corresponder.
`no_event_observed` não significa que o solver descartou a fórmula nem que o
trigger esteja errado. Os contadores de eventos são mantidos após atingir o teto
de gravação dos exemplos; erros de callback e limites do inventário são explícitos.

### 3. Inferências além de hints genéricos

Eventos `smt` são separados de hints específicos documentados como `euf`, `farkas`,
`bound` e `implied-eq`. As regras efetivamente observadas são registradas sem
rotular automaticamente qualquer outra regra como lema de teoria. `tseitin`,
assumptions e deleções não são tratados como justificativas aritméticas detalhadas.

### 4. Custo de cada bloco

Bytes e caracteres são sempre medidos. Tokens usam o tokenizer offline da revisão
`aedcc2d42b622764e023cf882b6652e646b95671` do Qwen Coder. Exemplos são limitados:
até 512 quantificadores salvos, 100 mil nós de AST visitados, seis termos por
símbolo de trigger, 20 eventos por regra e 400 eventos por replay. Fórmulas/eventos
grandes são omitidos inteiros, nunca cortados para parecer completos. Os limites
e omissões impedem interpretar as contagens como cobertura de toda a busca.

### 5. Efeito da instrumentação

As tabelas comparam resultados, motivos de `unknown` e medianas de duração dos quatro modos. O baseline
é outra reexecução API da mesma consulta, não a chamada original do Verus.
Timeout e profiling são overrides explícitos. O perfil nativo é guardado com seus
campos brutos; colunas cuja semântica não foi validada não recebem interpretações
inventadas.

## O que este piloto não promete

- Não extrai a base ativa de termos do E-matching, padrões inferidos pelo solver
  ou a razão causal pela qual um quantificador não foi instanciado.
- Termos com o mesmo símbolo-raiz de um padrão são candidatos sintáticos, não
  provas de matching. Não há correspondência automática entre variáveis da fonte
  e a ordem dos bindings do callback.
- O profiling/callback pode mudar a busca; a comparação mede justamente esse risco.
- Disponibilidade de um campo não demonstra que ele será útil para o LLM.

Referências: [Z3 inference logs](https://microsoft.github.io/z3guide/programming/Proof%20Logs/),
[API de quantificadores](https://z3prover.github.io/api/html/classz3py_1_1_quantifier_ref.html),
[quantificadores e E-matching](https://microsoft.github.io/z3guide/docs/logic/Quantifiers/).
