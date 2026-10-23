# Análise e arquitetura — 18/10/2026

## Referências examinadas antes da implementação

- AutoVerus, commit `cbf9c0c6337b224fd8e5b7cb4e01ae65c0f98bc1`: `autoverus/veval.py` executa Verus e separa diagnósticos de compilação/verificação; `infer.py` encapsula clientes e amostragem; `verify.py` organiza experimentos por arquivo; `utils.py::code_change_is_safe` usa o parser Lynette. Artigo: https://arxiv.org/abs/2409.13082 . O sistema combina inferência, refinamento e reparo; não transplantamos essas estratégias nem os exemplos few-shot.
- ExVerus, commit `4e513a1c49e8ba0731a4e23b3b9fe4e20662cd8c`: `vinv/pipeline/main.py::attempt_naive_repair`, ramo `ablation`, separa geração inicial de reparos e salva status/custos. `iterative.py::compile_naive_repair_prompt` também inclui original/diff; nosso protocolo deliberadamente usa só código atual e último diagnóstico, como solicitado. Não usamos contraexemplos, instrumentação ou o benchmark modificado do ExVerus.
- VeruSAGE: `verusage/run_batch.py`, no mesmo commit Microsoft, oferece configuração, logs, continuação e agregação por arquivo. Reaproveitamos a organização conceitual, sem agentes ou estratégias especializadas.

Fontes: https://github.com/microsoft/verus-proof-synthesis ; https://github.com/claudeyj/exverus . Código Python próprio; somente o parser/comparador Lynette é uma dependência externa, compilada a partir do commit fixado.

## Proposta simples

Pacote Python sem dependências para seleção, execução do Verus, logs e relatório. Apenas a inferência importa vLLM/Transformers. Um processo, uma GPU, um candidato e nenhuma busca. JSON é o equivalente a YAML escolhido para evitar outra dependência.

`baseline/`: benchmark, prompts, inference, verifier, integrity, feedback, storage, runner, evaluation e CLI. `configs/`: dois modos do piloto. `prompts/`: instruções versionadas. `data/`: somente entradas oficiais e manifests com hashes. `scripts/`: preparo e SLURM. `tests/`: testes de protocolo e integração com doubles explícitos. `docs/`: ambiente e protocolo. `results/`: uma pasta por execução/modo/tarefa/tentativa.

Reuso: benchmark oficial (apenas `unverified/`) e Lynette `additions`, que preserva assinaturas e implementação e permite lemas novos. Complementamos o comparador com restrições conservadoras a mecanismos confiados, atributos, imports e macros e verificamos separadamente o programa completo. Falha do comparador nunca equivale a sucesso. Não usar somente regex para comparar programas.

## Ambiente e dependências

Linux, Python 3.11, vLLM 0.8.5, Transformers 4.51.3, modelo Qwen/Qwen3-8B revisão `b968826d9c46dd6066d109eabc6255188de91218`, BF16, tensor parallel 1. Sampling e `enable_thinking` são passados explicitamente ao template/tokenizador e ao motor local. Contexto de 32768 tokens; excesso é erro registrado, sem cortar o código. Documentação consultada: https://huggingface.co/Qwen/Qwen3-8B e https://docs.vllm.ai/en/v0.8.5/ . Instalação GPU e compatibilidade efetiva ainda precisam de smoke test no cluster.

Verus recomendado pelo benchmark: commit `33269ac6a0ea33a08109eefe5016c1fdd0ce9fbd`. Usar o Z3 obtido pelo script desse commit. Registrar versões, hashes dos executáveis, `pip freeze`, hardware, configuração, hashes dos prompts e do código do pipeline em cada execução. Não instalar outro z3 via pip. Cargo.lock fixa o parser Lynette.

## Avaliação

Seleção anterior a qualquer resultado, seed 20261018, entradas ordenadas por ID e sorteio estratificado: CloverBench 2, Diffy 4, MBPP 7, Misc 2. Mesmo manifest nos dois modos. Essa alocação aproxima as proporções oficiais e garante cobertura; não será ajustada com base nos resultados. Piloto: geração inicial + 2 reparos. Baseline posterior: geração inicial + 5 reparos, somente após escolha humana.

Success@k é acumulado por tarefa. No piloto reportar @0, @1 e @2; @3/@5 ficam indisponíveis. Separar falhas de infraestrutura de falhas de prova, reportar cobertura e categorias. Guardar tempos, tokens, truncamento, erro e integridade por tentativa. Custo por resolvida = tempo computacional total de todas as tarefas / número resolvido; não excluir gastos com fracassos. Estimativa para 150 tarefas com seis tentativas é extrapolação de planejamento, não medida nem previsão de sucesso.

## Riscos e prevenção

- Sem acesso ao cluster não há piloto real nem conclusão científica; testes simulados ficam separados dos resultados.
- Verus antigo versus parser recente: testar em 1–2 tarefas, inclusive mutações negativas, antes do piloto. Nenhuma troca silenciosa de versões.
- Lynette é uma checagem estrutural, não prova matemática de equivalência. Restrições extras conservadoras podem rejeitar soluções legítimas; registrar esse fato e manter a política constante.
- Respostas thinking podem terminar sem resposta final; registrar truncamento, não tratar raciocínio como programa.
- SLURM pode interromper entre fases. Persistir resposta antes de verificar e resultados atomicamente; retomar sem regenerar respostas salvas. Um único escritor por pasta de execução.
- Não ler `verified/` ou `tasks.jsonl` durante experimentos (este último também contém soluções).
- Fixar seeds e versões melhora rastreabilidade, sem prometer determinismo bit a bit de kernels GPU.

## Estado inicial

Workspace vazio em Windows; sem Verus, Cargo, nvidia-smi ou sbatch no PATH. Cluster ainda não informado. A implementação e testes locais avançam; etapas de inferência real, smoke test real e piloto dependem dessa infraestrutura. Não há autorização para iniciar automaticamente o baseline de 150 tarefas.

## Adaptação ao guia do cluster — 18/10/2026

O guia posterior definiu `high_performance`, QOS `high`, runtime persistente com
pip target e isolamento por `CUDA_VISIBLE_DEVICES`. Os jobs agora separam preparação
e piloto, repetem inicialização/preflight em cada alocação e usam caminhos por seed.
O Python pode ser 3.11 ou 3.12; a pilha CUDA usa torch 2.6.0 exigido pelo vLLM,
preservando o modelo e os parâmetros científicos. A classe da GPU é registrada;
mudanças entre sessões são sinalizadas no relatório de custo, sem fixar nós.
Instruções atuais: `docs/cluster.md`.
