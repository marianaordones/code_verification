# Executar neste cluster SLURM

Integração adaptada ao guia fornecido em 18/10/2026. Não foi testada em um nó real;
os jobs fazem os testes de ambiente antes de qualquer experimento. O protocolo
científico, as 15 tarefas, os parâmetros dos dois modos e o limite de reparos
permanecem iguais.

## O que executar agora

Transfira o ZIP atualizado para uma pasta **no filesystem compartilhado** do cluster.
Não precisa transferir `references/` nem criar `.venv`. Se você já tinha enviado a
versão anterior, extraia esta versão em uma pasta nova para evitar misturar arquivos.

No terminal do cluster, na pasta onde colocou o ZIP:

```bash
unzip verus-baseline.zip -d code_verification
cd code_verification
mkdir -p logs
sbatch scripts/slurm/prepare.slurm
```

Esse é o primeiro job. Não submeta o piloto junto. Nenhum caminho pessoal precisa
ser editado para o modo padrão. `SLURM_SUBMIT_DIR` define a raiz. Não coloque o
projeto em `/tmp` ou em armazenamento local de um nó.

O job `verus-prepare` solicita `high_performance`, QOS `high`, uma GPU, 8 CPUs,
64 GB e 24 horas. Não escolhe nem exclui nós. Ele:

1. Encontra Python 3.12/3.11, cria/reutiliza dependências persistentes com pip target.
2. Confere imports, CUDA, uma única GPU lógica, memória e uma operação BF16 real.
3. Compila Verus no commit fixado e Lynette em scratch local com execução validada,
   obtém seu Z3 e guarda um pacote completo das ferramentas no armazenamento compartilhado.
   Se necessário instala rustup no HOME, sem sudo.
4. Executa os testes, incluindo a checagem real de alterações inválidas de programas.
5. Baixa a revisão fixada do Qwen3-8B para uma pasta compartilhada com arquivos
   comuns, sem os symlinks do cache padrão do Hugging Face.
6. Executa as mesmas duas tarefas de integração em non-thinking e thinking.

Essa primeira preparação exige acesso HTTPS a PyPI, GitHub, servidores Rust e
Hugging Face, além de `git`, `cc`, `make` e `flock`. `curl` é necessário se rustup
ainda não existir. Reserve espaço compartilhado para bibliotecas, wheels, pesos
BF16 e builds Rust (dezenas de GB). Não é preciso token para o modelo público
Qwen/Qwen3-8B. Se a infraestrutura bloquear downloads ou builds, o job falha com
o motivo nos logs; envie esses logs para ajustarmos a preparação.

A extração do Z3 usa `zipfile` do Python, sem depender do comando `unzip` no nó.
O pacote é o Z3 4.12.5 x64/glibc 2.31 selecionado pelo checkout fixado do Verus.

O build usa `CARGO_NET_GIT_FETCH_WITH_CLI=true` e um `CARGO_HOME` novo em scratch
local. Isso evita a falha de busca de commits do backend libgit2 do Cargo antigo
e o reuso de caches Git incompletos no armazenamento compartilhado. As revisões do
Cargo.lock são preservadas. As dependências Rust são baixadas novamente quando
um build precisa recomeçar; os caches Python e do modelo permanecem persistentes.

Quando stdout terminar com **`PREPARATION AND REAL SMOKE TESTS COMPLETE`**, e o job
aparecer como `COMPLETED`, submeta o piloto da mesma raiz:

```bash
sbatch scripts/slurm/pilot.slurm
```

Esse job reutiliza o ambiente, repete o preflight e os testes reais das ferramentas,
executa thinking e non-thinking nas mesmas 15 tarefas e gera o relatório. Ele
**não inicia o baseline de 150 tarefas**. Não se exige que as duas provas de smoke
tenham sucesso; exige-se que inferência, Verus, integridade e persistência funcionem.

## Acompanhar os jobs

```bash
squeue -u "$USER"
```

Substitua `12345` pelo ID devolvido pelo `sbatch`:

```bash
tail -f logs/verus-prepare-12345.out
tail -f logs/verus-prepare-12345.err
sacct -j 12345 --format=JobID,State,ExitCode,NodeList,Elapsed
```

Para o segundo job, os arquivos são `logs/verus-pilot-ID.out` e `.err`.
`Loading checkpoint shards` em stderr é normal. Se não houver logs, confira se
`logs/` já existia **antes** do sbatch e consulte `sacct`/`scontrol show job ID`.

## Arquivos esperados

| Local | Conteúdo |
|---|---|
| `logs/verus-prepare-ID.out` e `.err` | Instalação, build e testes de integração |
| `logs/preflight-ID.json` | Nó, Python, versões, GPU lógica, CUDA e estado complete |
| `logs/requirements-ID.txt` | Dependências transitivas efetivamente instaladas |
| `$HOME/pylibs/verus-.../` | Cache persistente: Python + arquitetura + libc + hash dos requirements |
| `.cluster/models/Qwen3-8B/b968826d9c46dd6066d109eabc6255188de91218/` | Arquivos persistentes do modelo/tokenizador, sem symlinks |
| `.cluster/tools.json`, `tools-native.tar.gz` e `tools-native.json` | Hashes e pacote completo de ferramentas; extraído para scratch local em cada job |
| `results/seed-20261018/smoke/{modo}/` | As duas tarefas reais de integração |
| `results/seed-20261018/pilot/{modo}/` | As 15 tarefas, tentativas, prompts, respostas, códigos e métricas |
| `results/seed-20261018/pilot/report.md` e `.json` | Comparação e recomendação para sua decisão |
| `results/seed-20261018/gpu-ID.csv` | Amostras da GPU atribuída, quando identificável por UUID |

## Como o runtime funciona

Todo `.slurm` carrega `scripts/cluster/job_init.sh`, que carrega
`scripts/cluster/setup_runtime.sh`. Não depende de Lmod, módulos ou venv. Ignora
`PYTHONPATH`, `PYTHONHOME`, venv e configurações pip herdadas. Usa o código da raiz
e as bibliotecas em `$HOME/pylibs` via `PYTHONPATH`, com `PYTHONNOUSERSITE=1`.
Um wrapper normal `python` substitui a necessidade de symlinks do ambiente Python.

Uma instalação só é publicada após sucesso de pip e imports, escrita do manifesto
`.complete` com hash dos requirements e rename da pasta staging. Um lock impede
instalações concorrentes no mesmo cache. Instalações parciais não são reutilizadas.
Cada job usa temporários exclusivos em `/tmp` **somente se houver 25 GB livres**;
caso contrário, usa `$HOME/pylibs/.tmp`. Não usa `/dev/shm` para arquivos do projeto.
O cleanup só remove o diretório temporário exclusivo que o próprio job criou.

`requirements-cluster.txt` fixa vLLM 0.8.5, torch 2.6.0, Transformers 4.51.3,
NumPy 1.26.4 e dependências diretas de compatibilidade. O torch 2.5.1 do exemplo
LoRA do guia não serve para esse vLLM. Referência de compatibilidade:
https://github.com/vllm-project/vllm/blob/v0.8.5/requirements/cuda.txt .
Os wheels oficiais dessa geração usam bibliotecas CUDA próprias; não substituímos
o torch pelo módulo do cluster. Preflight confere o driver executando um kernel.

O arquivo `logs/requirements-ID.txt` registra o ambiente resolvido, que pode ser
usado em repetições. Como dependências transitivas nem todas estão fixadas no
arquivo inicial, preserve esse lock. Para usar um lock futuro, defina `CLUSTER_REQS`
em `cluster.env`; a mudança de hash cria outro cache automaticamente.

## Se precisar personalizar

No modo padrão não crie `cluster.env`. Para reutilizar ferramentas já instaladas
ou um Python standalone específico:

```bash
cp cluster.env.example cluster.env
nano cluster.env
```

Use caminhos absolutos. Para ferramentas existentes, defina **os três** valores
`VERUS_BIN`, `Z3_BIN` e `LYNETTE_BIN`. O Verus precisa identificar o commit
`33269ac6a0ea33a08109eefe5016c1fdd0ce9fbd`; o parser é o incluído no ZIP,
com a correção documentada em `tools/lynette/README.md`. O job fixa
`VERUS_Z3_PATH` no executável cujo hash foi registrado.

Python mínimo: 3.11; preferimos 3.12/3.11 do nó. Não usamos o módulo Python 3.10
do exemplo porque o projeto requer 3.11+. Se nenhum interpretador compatível
estiver disponível, a preparação para antes do download de pacotes e informa o erro.
Rust e o build do Verus têm requisitos próprios; se o HOME/CIFS bloquear as operações
do rustup, use ferramentas previamente compiladas em um local compartilhado
compatível e informe seus caminhos. O runtime Python não exige symlinks; o
instalador/build Rust ainda precisa ser validado nesse filesystem.

## Retomar após interrupção

Submeta novamente o job da etapa interrompida:

```bash
sbatch scripts/slurm/prepare.slurm
# OU, se a preparação já terminou:
sbatch scripts/slurm/pilot.slurm
```

Não modifique o código, prompts, entradas, parâmetros ou executáveis entre a
interrupção e a retomada na mesma pasta. O pipeline confere seus fingerprints.
Respostas já persistidas e tentativas completas são reutilizadas; uma interrupção
durante geração antes de salvar a resposta exige repetir essa geração. Locks de
execução são liberados pelo kernel. Uma pasta staging incompleta é ignorada,
e a próxima tentativa cria outra; não apague caches amplos para resolver uma falha.

O build Rust precisa de 25 GiB livres em scratch com suporte a execução. A execução
das ferramentas já compiladas precisa de 2 GiB livres. O script testa `/bin/true`
copiado para o diretório temporário antes de usá-lo. Ele tenta `CLUSTER_BUILD_TMP`,
`SLURM_TMPDIR`, `/tmp` e `/var/tmp`; não faz fallback do build para HOME/CIFS.
Se nenhum local servir, solicite um caminho de scratch local ao administrador e
defina `CLUSTER_BUILD_TMP` em `cluster.env`. Não use `/dev/shm`.

O scheduler pode escolher outra A100/L40S; não fixe nós. O relatório permite
retomada e compara a classe da GPU/memória/build CUDA, não o UUID físico. Quando
as classes mudam, os sucessos continuam registrados e o relatório marca o custo
como não comparável, recomendando repetir a comparação em hardware homogêneo.

## Baseline somente depois da sua escolha

Leia `results/seed-20261018/pilot/report.md`. Se decidir continuar, crie `decision.json`:

```json
{
  "mode": "nonthinking",
  "rationale": "Sua justificativa após comparar sucesso, custo e truncamento.",
  "pilot_report": "results/seed-20261018/pilot/report.json",
  "pilot_report_sha256": "HASH_REAL_DO_RELATORIO"
}
```

Use `sha256sum results/seed-20261018/pilot/report.json` para obter o hash. Depois:

```bash
sbatch scripts/slurm/baseline.slurm configs/nonthinking.json decision.json
```

Esse comando explícito usa as 150 tarefas e até cinco reparos. Se sua escolha for
thinking, altere o modo e o caminho da configuração. `scripts/pilot.slurm` e
`scripts/baseline.slurm` continuam como entradas equivalentes por compatibilidade.

## Limites e protocolo preservado

Ainda precisam ser validados no cluster: resolução/instalação dos wheels, driver
CUDA, espaço, downloads, toolchains Rust, build Verus/Lynette e carga BF16. Validação
local de sintaxe não demonstra que esses componentes funcionam no compute node.

O piloto compara configurações operacionais completas: thinking 8192 tokens,
T=0.6/p=0.95; non-thinking 4096 tokens, T=0.7/p=0.8; ambos k=20 e seed 20261018.
Success@k é acumulado por tarefa, não pass@k; @3/@5 não são medidos no piloto.
O custo por resolvida inclui gastos nas tarefas sem sucesso. A projeção 150 × 6
tentativas é uma estimativa de planejamento; não prevê sucesso nem tempo de fila.
Carga do modelo e sessões interrompidas são registradas separadamente. Custos de
tentativas interrompidas antes de salvar resultados podem ficar desconhecidos.

A integridade é conservadora e pode rejeitar soluções legítimas; a política fica
constante entre modos. `Misc/havoc_inline_post.rs` já tem `assume` na entrada oficial:
mantemos a tarefa, mas qualquer candidato que contenha `assume` é inválido.
Se o thinking terminar sem código final, o candidato vazio e o erro são registrados
e o reparo mantém o programa corrente anterior. O feedback do reparo contém só a
última saída convencional do Verus, sem dados internos de solver ou integridade.
