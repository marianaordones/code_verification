# LLM-Guided Program Verification — baseline

Pipeline simples para gerar e reparar provas Rust/Verus com Qwen3-8B local,
uma GPU e feedback convencional do Verus. Sem fine-tuning, busca de candidatos,
contraexemplos adicionais ou acesso interno ao solver.

O código foi preparado localmente para você transferir e executar no cluster
Linux/SLURM. **Nenhum resultado real do piloto foi produzido neste ambiente.**
O baseline completo só é habilitado após a escolha humana baseada no piloto.

Comece pela [análise das referências e arquitetura](docs/architecture.md) e pelo
[guia de instalação e execução no SLURM](docs/cluster.md).

```text
baseline/        carregamento → prompts → vLLM → Verus → integridade → logs/métricas
configs/         thinking e non-thinking, com os parâmetros solicitados
prompts/         prompts zero-shot e de reparo versionados
data/            150 entradas oficiais, hashes e seleção fixa de 15 tarefas
tools/lynette/   parser/comparador de integridade reutilizado (MIT)
scripts/         preparo e jobs SLURM
tests/           protocolo, retomada, métricas e testes reais opcionais
docs/            análise e instruções para o cluster
```

Python 3.11+, vLLM 0.8.5, Transformers 4.51.3 e BF16. Verus, Z3 e o modelo têm
revisões/identidades registradas; veja o guia para preparar o ambiente.
O pipeline fora da inferência usa somente a biblioteca padrão de Python.

Testes locais (sem baixar o modelo):

```bash
python -m unittest discover -s tests -v
```

Testes de Verus/Lynette são pulados quando `VERUS_BIN` e `LYNETTE_BIN` não estão
definidos. Os testes com simulação não medem sucesso científico.

No cluster, depois de extrair o ZIP em armazenamento compartilhado:

```bash
mkdir -p logs
sbatch scripts/slurm/prepare.slurm
```

O primeiro job prepara um runtime persistente sem módulos/venv, compila as
ferramentas e testa duas tarefas nos dois modos. Quando ele terminar com sucesso:

```bash
sbatch scripts/slurm/pilot.slurm
```

O job do piloto usa as mesmas 15 tarefas nos dois modos: geração inicial e até dois reparos.
Mantém respostas completas, prompts renderizados, código, saída do Verus,
integridade, tempos e tokens por tentativa. Salva `results/seed-20261018/pilot/report.md` e
`report.json`, com resultados globais e por categoria, custo por resolvida e
projeção de tempo. Arquivos salvos permitem retomar o job.

Seleção prévia: seed `20261018`, estratos CloverBench 2, Diffy 4, MBPP 7, Misc 2;
IDs em [data/pilot.json](data/pilot.json). Só `unverified/` é distribuído ao pipeline.
O modo não é escolhido automaticamente e o job para após o relatório do piloto.

Piloto atual: **Qwen3-14B, prompt v2, 50 IDs sorteados com semente fixa,
thinking e non-thinking**. Consulte [as instruções e arquivos a transferir](docs/pilot14b-v2-50.md).
Depois de atualizar esses arquivos no cluster:

```bash
mkdir -p logs
sbatch scripts/slurm/pilot14b_v2_50.slurm
```

Resultados em `results/qwen14b-v2-50/seed-20261018/pilot/`, separados do 8B
e do piloto anterior de dez tarefas. Nenhuma seleção por dificuldade foi aplicada.

Referências: [AutoVerus / VeruSAGE e Verus-Bench](https://github.com/microsoft/verus-proof-synthesis),
[artigo AutoVerus](https://arxiv.org/abs/2409.13082),
[ExVerus](https://github.com/claudeyj/exverus),
[Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B).
# Atualização: Coder v4 e revalidação

A próxima execução completa usa `scripts/slurm/qwen25coder14b_v4_150.slurm`.
O filtro permite triggers de prova e mantém as verificações estrutural e Verus.
Para reavaliar candidatos antigos sem inferência, use `scripts/slurm/revalidate.slurm`.
Instruções e comandos: [Coder v4 e revalidação](docs/qwen25coder14b-v4-150.md).

