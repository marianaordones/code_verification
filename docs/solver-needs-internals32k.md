# Solver Needs: 32k de internals, três propostas e eventos iniciais reutilizados

Esta variante usa os mesmos 100 IDs de `configs/solver-needs-tasks100.json`.
O modelo continua sendo Qwen2.5-Coder-14B-Instruct, com as mesmas configurações
de geração e sementes por proposta. São **três propostas totais** em cada braço.

| Parâmetro | Valor |
|---|---:|
| Contexto total | 49.152 tokens |
| Bloco de internals | Até 32.768 tokens |
| Grupos de quantificadores | Até 50 |
| Instanciações por grupo | Até 3 |
| Reserva de saída | 4.096 tokens |

O teto de grupos não aumenta em relação à execução de 24k. O tamanho efetivo do
bloco também respeita o espaço restante no contexto. Não há truncamento silencioso
do programa, dos diagnósticos ou de fórmulas selecionadas.

## Reutilização da primeira proposta

A preparação exige a execução concluída de 24k como fonte. Ela:

- confere os hashes das entradas congeladas e as identidades do Verus/Z3;
- exige os mesmos 100 IDs, na mesma ordem, e os mesmos parâmetros de geração;
- copia o candidato inicial, sua região editável e o diagnóstico original;
- copia consultas, relatórios e eventos de replay salvos para formar um snapshot;
- reconstrói o pacote de internals com 32k a partir desses eventos, sem executar
  novamente o candidato inicial nem seus replays;
- confere que as mensagens comuns da primeira proposta e sua semente coincidem
  com as da execução de origem.

Os registros antigos permanecem intactos. Arquivos ausentes ou incompatíveis
causam erro explícito; não há fallback para uma nova busca do solver.

O system prompt é preservado literalmente a partir do pedido inicial salvo,
inclusive a referência histórica a um teto de quatro propostas. O controlador
encerra esta execução em **três**, independentemente desse teto textual. Essa
escolha mantém a primeira mensagem igual à referência de 24k, sem mudar a redação
do prompt ao mesmo tempo que o orçamento do feedback. As ações, catálogo e
interpretação dos internals permanecem iguais. O prompt congelado também é usado
nas propostas seguintes.

Após reparos diferentes, as buscas precisam ser novas. Portanto, a igualdade
de eventos é garantida para a primeira proposta, não para trajetórias divergentes.
O protocolo mantém os limites anteriores de captura/replay e seleção por relevância.

O reservatório salvo limita a informação recuperável: ampliar o orçamento não
recupera eventos que não foram guardados na execução de origem.

## Executar no cluster

Após encerrar os jobs ativos e seus relatórios, atualize `solver_needs_study/`,
`configs/`, `scripts/` e `tests/`. Não altere uma execução ativa, pois os hashes
de implementação são conferidos. Preserve a versão de código dos estudos antigos
se precisar retomá-los. Não é necessário alterar o conteúdo de `prompts/`.

Na pasta nova do projeto, que contém os resultados de 24k:

```bash
cd /home/mariana.soares/code_verification_git
mkdir -p logs
bash scripts/submit_solver_needs_internals32k.sh
```

Se a execução de origem estiver em outra pasta, forneça destino e origem:

```bash
bash scripts/submit_solver_needs_internals32k.sh \
  results/solver-needs-qwen14b-100-internals32k/seed-20261018 \
  /caminho/para/solver-needs-qwen14b-100-internals24k/seed-20261018
```

O script agenda preparação CPU, os dois braços numa sessão GPU e o relatório,
com QoS `high`. A preparação usa tokenizer e ferramentas de identidade da
infraestrutura existente; seus autotestes são independentes dos eventos reutilizados.

Resultados separados:

```text
results/solver-needs-qwen14b-100-internals32k/seed-20261018/
```

Em cada `inputs/ID/reuse.json` ficam os hashes dos artefatos de origem, a semente,
o hash do prompt comum e os hashes dos pacotes anterior e reconstruído. O
`manifest.json` congela as cópias e a configuração nova. Os arquivos
`source-feedback.json` preservam os pacotes anteriores para auditoria.

Para retomar somente a etapa GPU:

```bash
sbatch scripts/slurm/solver_needs_run.slurm results/solver-needs-qwen14b-100-internals32k/seed-20261018
```

Para atualizar o relatório:

```bash
python3 -m solver_needs_study compare --study results/solver-needs-qwen14b-100-internals32k/seed-20261018
```

O controlador lê o manifesto: não volta ao limite de quatro propostas numa retomada.
Para comparar com 24k, utilize somente as primeiras três propostas da referência.
O controle sem internals é executado novamente; não são copiadas respostas ou
resultados do modelo. Mesmas sementes não garantem resultados idênticos em
ambientes de inferência diferentes.
