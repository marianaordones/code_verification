# Validação local — 18/10/2026

Ambiente: Windows, Python 3.12.14. O alvo de execução real continua sendo Linux
com Python 3.11 e uma GPU.

Executado: `python -m unittest discover -s tests -v`.

- 32 testes passaram, incluindo os pilotos 14B/v2 com dez e cinquenta tarefas.
- 1 teste de ferramentas reais foi pulado porque Verus/Lynette não estão instalados.
- Compilação dos módulos Python e ajuda da CLI passaram.
- Inventário: 150 entradas oficiais; a seleção fixa reproduz exatamente os 15 IDs.
- Sintaxe dos 13 scripts Bash/SLURM validada com `bash -n`.
- Diretivas verificadas: partição `high_performance`, QOS `high`, uma GPU,
  stdout/stderr separados em logs e ausência de seleção/exclusão de nós.

Os testes verificam fluxo geração/reparo, persistência de prompts/respostas/código,
retomada sem regeneração após interrupção entre geração e verificação, integridade
como condição necessária de sucesso, feedback apenas convencional, parâmetros
fixados, extração de thinking, timeouts e métricas acumuladas. Também verificam
relatórios completos/incompletos, categorias e rejeição de pares de tarefas diferentes.
Também verificam falha antecipada sem GPU alocada, GPUs visíveis em excesso e CUDA
indisponível, além da sinalização de mudanças de classe de GPU entre sessões.
Os testes de relatório também aceitam caminhos temporários distintos quando os
hashes dos executáveis são iguais. Build e execução Rust agora usam scratch local;
essa correção ainda precisa ser validada no filesystem do cluster.
O log 5921 confirma que o kernel BF16 passou na L40S e que vargo compilou em
scratch local; a falha seguinte foi ausência do comando unzip. O instalador agora
usa zipfile do Python para extrair o mesmo Z3 4.12.5, com dois testes locais de
extração. O build completo Verus/Lynette ainda depende de nova execução no cluster.

O log posterior enviado pelo usuário confirmou o teste real Verus/Lynette como
`ok`; a falha seguinte foi a criação de symlinks pelo cache Hugging Face. A inferência
agora usa uma pasta local persistente obtida com `snapshot_download(local_dir=...)`,
na mesma revisão fixada. Dois testes locais verificam o destino/revisão solicitados
e a rejeição de downloads incompletos. A carga efetiva do Qwen ainda precisa ser
confirmada no cluster.

Os doubles de inferência, Verus e integridade existem somente nos testes. Seus
resultados temporários são descartados e nunca são escritos em `results/pilot`.

Ainda não executados: build Rust do Lynette, teste com Verus e Z3 reais, carga BF16
do Qwen3-8B, smoke tests com inferência real e piloto de 15 tarefas nos dois modos.
Essas etapas estão no script SLURM e devem passar no cluster antes de interpretar
qualquer resultado como evidência experimental. Não há relatório de resultados
científicos fabricado nem escolha de modo.
