# Falha Rust `build-script-build (never executed)`, os error 22

O compilador gerou programas auxiliares, mas o sistema recusou iniciá-los. Vários
pacotes independentes falham da mesma forma. Como o caminho está em `/mnt/users`,
e o guia relata problemas CIFS/QNAP, a hipótese principal é uma incompatibilidade
de execução/mapeamento de executáveis no filesystem compartilhado. O erro isolado
não confirma o tipo de montagem; `findmnt -T CAMINHO` permite conferir no cluster.

Cargo compila e executa `build.rs` antes de construir cada pacote:
https://doc.rust-lang.org/cargo/reference/build-scripts.html .

Correção implementada:

- A cópia compartilhada `.cluster/verus` guarda somente a revisão de referência.
  Seus `target/` antigos não são usados pelo build novo.
- O job clona essa revisão para scratch local e compila todo o fluxo ali,
  incluindo o próprio vargo, o Verus e o Lynette.
- As ferramentas completas, com bibliotecas e vstd, são guardadas em um arquivo
  `tools-native.tar.gz` com manifesto e SHA256 no filesystem compartilhado.
- Cada job extrai o pacote em scratch local, confere as ferramentas e executa
  dali. Não grava caminhos temporários como identificadores estáveis de retomada.
- Requisitos: 25 GiB livres para build e 2 GiB para extrair ferramentas prontas.
  O diretório precisa aceitar execução; há uma sonda ELF antes do uso.

Para atualizar uma instalação existente, coloque `verus-baseline-fix-build.zip`
na raiz do projeto e execute no login node:

```bash
cd /mnt/users/mariana.soares/code_verification
unzip -o verus-baseline-fix-build.zip
mkdir -p logs
sbatch scripts/slurm/prepare.slurm
```

Faça isso após o job antigo ter terminado. Os caches Python/modelo são reutilizados;
não apague `.cluster`, `results`, `$HOME/pylibs` ou os pesos. Um build interrompido
em scratch pode precisar recomeçar, mas a instalação Python não é refeita se o
cache completo já existir.

Se faltar scratch, o novo erro será explícito. Peça ao administrador um diretório
local executável e configure `CLUSTER_BUILD_TMP` em `cluster.env`. Não aponte essa
variável de volta para `/mnt/users`/HOME compartilhado.

Validação local cobre sintaxe Bash, testes Python e estabilidade das identidades
das ferramentas entre caminhos temporários. O build Rust real e o comportamento
do filesystem precisam ser confirmados no job do cluster.
