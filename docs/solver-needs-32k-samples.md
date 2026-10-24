# Dois formatos de internals: 80 x 3 e 50 x 5

Os dois experimentos usam os mesmos 100 IDs de `solver-needs-tasks100.json`,
Qwen2.5-Coder-14B-Instruct, contexto total de 49.152 tokens, até 32.768 tokens
de internals, 4.096 tokens reservados para saída e três propostas totais.

| Experimento | Grupos de quantificadores | Instanciações por grupo |
|---|---:|---:|
| Maior diversidade | Até 80 | Até 3 |
| Maior profundidade | Até 50 | Até 5 |

O limite de grupos é global ao pacote, somando as consultas selecionadas. Os
valores são tetos: os eventos observados, a seleção por relevância, as cotas de
axiomas genéricos e os limites de tokens podem reduzir a amostra enviada.

## Fonte e coleta compartilhada

Os candidatos, regiões editáveis, diagnósticos, contexto da falha, prompts e
sementes iniciais vêm da execução concluída de 24k. A implementação e os contratos
não são alterados. A igualdade das mensagens comuns e das sementes é verificada.

O coletor antigo guardava até quatro eventos distintos por grupo. Portanto, não
seria possível testar cinco instanciações apenas reempacotando esses registros.
Esta preparação executa **novos replays das mesmas consultas iniciais capturadas**,
salvando até cinco eventos por grupo. Essa nova coleta acontece uma vez por
candidato e é reutilizada pelos dois formatos. Não há uma nova execução inicial
do Verus para obter outras consultas.

Assim, as duas variantes compartilham o mesmo conjunto inicial de eventos e
estatísticas, mas esse conjunto pode diferir dos replays antigos da execução de
24k. Não se deve atribuir toda diferença em relação a 24k apenas ao formato ou
ao orçamento, pois a coleta diagnóstica inicial também foi renovada.

O reservatório continua com até 128 grupos por consulta, até três consultas e
cinco segundos de replay por consulta. A seleção e as cotas de representação e
outros axiomas genéricos permanecem. Nas propostas posteriores, ambos os formatos
também coletam até cinco eventos por grupo; as buscas podem divergir após reparos
diferentes. A variante 80x3 envia no máximo três desses eventos e a 50x5 até cinco.

O prompt é preservado literalmente da execução de origem. O controlador impõe
três propostas, embora o texto histórico mencione um teto de quatro. Isso mantém
a redação comum e evita alterar a orientação ao comparar formatos.

## Executar

Não é necessário executar a variante anterior de 32k/50x3. Após concluir jobs
ativos e seus relatórios, atualize estas pastas no cluster:

- `solver_needs_study/`
- **`repair_study/`**, que contém o coletor com limite configurável;
- `configs/`
- `scripts/`
- `tests/`

Na pasta nova do projeto:

```bash
cd /home/mariana.soares/code_verification_git
mkdir -p logs
bash scripts/submit_solver_needs_32k_samples.sh
```

A origem padrão é `results/solver-needs-qwen14b-100-internals24k/seed-20261018`.
Para outro destino e origem:

```bash
bash scripts/submit_solver_needs_32k_samples.sh \
  results/solver-needs-qwen14b-100-internals32k-samples/seed-20261018 \
  /caminho/para/solver-needs-qwen14b-100-internals24k/seed-20261018
```

O script agenda uma preparação CPU compartilhada e dois jobs GPU independentes
com QoS `high`. Cada job executa os braços com e sem internals; cada um solicita
uma GPU, 64 GB de RAM e até 24 horas. Os dois jobs podem executar simultaneamente
quando houver recursos. Há um job de relatório por variante.

## Arquivos e retomada

```text
results/solver-needs-qwen14b-100-internals32k-samples/seed-20261018/
    shared-initial-events/   # coleta inicial comum, com hashes e bloqueio
    80x3/                   # comparação com/sem internals
    50x5/                   # comparação com/sem internals
```

Leia `comparison.md` e `comparison.json` em cada variante. Os arquivos
`inputs/ID/reuse.json` identificam o pool compartilhado e os hashes dos eventos
copiados. O pool é congelado por `pool.json`; alterações ou incompatibilidades
causam erro explícito. Os estudos ficam autossuficientes para a etapa GPU porque
as evidências iniciais são copiadas e incluídas nos hashes de seus manifestos.

Se a preparação for interrompida, rode novamente o script de preparação com os
mesmos quatro argumentos e a mesma versão do código. Pools completos são reutilizados;
uma coleta interrompida antes de completar seu manifesto pode precisar de replay.

Para retomar somente um job GPU:

```bash
sbatch scripts/slurm/solver_needs_run.slurm results/solver-needs-qwen14b-100-internals32k-samples/seed-20261018/80x3
sbatch scripts/slurm/solver_needs_run.slurm results/solver-needs-qwen14b-100-internals32k-samples/seed-20261018/50x5
```

Os controles sem internals são executados em ambos os estudos, com as mesmas
sementes e mensagens comuns. Respostas antigas não são copiadas. Após a primeira
proposta, a comparação continua sendo entre trajetórias de reparo, não entre buscas
idênticas garantidas. O compartilhamento de eventos não garante determinismo da
inferência nem que cada grupo disponha de cinco eventos distintos.
