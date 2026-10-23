# Solver Needs: Qwen Coder 14B, com e sem internals

Este experimento compara reparos localizados dos mesmos candidatos Verus, usando
Qwen2.5-Coder-14B-Instruct, com e sem estatísticas/instanciações do Z3. São **quatro
propostas no total por tarefa e braço**, incluindo JSON inválido e edições vazias.
O modelo é carregado uma vez; a ordem dos braços alterna entre tarefas.

## Dataset e seleção

Fonte: [knutsa/solver-needs](https://github.com/knutsa/solver-needs/tree/f32c274b053c372aa35c9d8a7e12c1df35bda20d),
commit `f32c274b053c372aa35c9d8a7e12c1df35bda20d`.
Usamos os **462 IDs Verus do benchmark do artigo**, não todos os 468 registros
da extração publicada. Ambos os números e os rótulos são registrados.

Por padrão, usamos **100 tarefas com IDs fixados** em
`configs/solver-needs-tasks100.json`, com semente de seleção 20261018.
São 17 tarefas de cada categoria `AX`, `INST-forall`, `INST-witness` e `NLA`,
e 16 de cada categoria `FUEL` e `Other`. A seleção prefere programas menos
repetidos, sem consultar resultados do modelo. A execução lê essa lista salva;
não sorteia novos IDs. Os IDs também são copiados para `selected_ids.json` na
pasta dos resultados, antes das verificações, e constam no manifesto final.
Alguns rótulos da extração e do benchmark diferem; as divergências ficam no relatório.
Os rótulos representam resultados de sondas, podem se sobrepor e não são respostas
obrigatórias do modelo.

Cada tarefa remove uma assertion essencial, incluindo seu bloco `by`, de um
programa previamente verificado. As outras anotações permanecem. Isso difere dos
experimentos anteriores que geravam provas sobre VerusBench: as taxas de sucesso
não devem ser comparadas diretamente.

**A preparação confia nas checagens publicadas. Não executa novamente o programa
original, o placebo ghost nem a restauração da assertion.** Executa somente o
candidato com a assertion removida, para obter os diagnósticos e capturar consultas.
Se esse candidato já verificar na infraestrutura atual, registra `initially_verified`,
não chama o modelo nesse caso e não o conta como reparo bem-sucedido. O denominador
efetivo de reparos é apresentado separadamente.

Os arquivos baixados são conferidos por SHA-256. A licença do código é MIT e a
licença dos dados gerados é CC BY 4.0; os avisos originais acompanham o download.

## O que o modelo recebe e pode fazer

O prompt completo está em `prompts/solver-needs/system.txt`. Ambos os braços recebem:

- programa atual com um único ponto de edição marcado;
- diagnósticos do Verus, contexto da falha e histórico das tentativas;
- explicação das seis famílias de falha e das intervenções possíveis;
- o mesmo catálogo completo de nove lemas de sequências, com corpos de prova.

O modelo retorna somente JSON:

```json
{"mechanism":"INST-forall","statements":"let ghost hint = TERM;","law":null,"nla":false}
```

`TERM` é apenas um marcador ilustrativo. O modelo precisa produzir uma expressão real.
A resposta substitui a região anterior e suas opções, em vez de acumular texto.
O campo `mechanism` é uma hipótese, não um critério de aceitação.

São permitidos assertions, termos ghost, chamadas de lemas existentes e
`reveal_with_fuel` na região. O aplicador preserva o prefixo e o sufixo originais,
rejeita construções proibidas e insere `proof { ... }` quando necessário.
Não usa Lynette nem afirma aplicar exatamente a política antiga de integridade:
a preservação é mecânica e a aprovação depende da verificação do arquivo inteiro.

Uma lei opcional acrescenta **um lema com prova verificada**, não uma hipótese
incondicional. `nla=true` permite exatamente `--smt-option smt.arith.nl=true`, a
intervenção NLA do artigo. Essa opção muda a configuração do solver e é registrada;
neste estudo a ação não se limita a inserir anotações.

O modelo não recebe a assertion removida, o rótulo correto, seeds das sondas nem
quais sondas tiveram sucesso. Esses metadados ficam em `private/` para auditoria.

## Internals e orçamento

O braço `with_internals` acrescenta somente o bloco `solver_internals`; o controle
omite esse bloco. Candidato inicial, sementes, orientação e catálogo são os mesmos.
O relatório confere a igualdade das entradas comuns da primeira proposta.
Depois de reparos diferentes, os candidatos e diagnósticos podem divergir.

Configuração: contexto de **49.152 tokens**, até **12.288 tokens de internals** e
**4.096 tokens reservados para saída**. A contagem usa o tokenizer e o template
reais. Não há corte silencioso do programa nem envio da consulta SMT inteira.

São examinadas até três consultas capturadas com resultado `sat` ou `unknown`.
Cada uma é reexecutada pela API do Z3 com limite diagnóstico de cinco segundos;
somente resultados concordantes com a consulta capturada são expostos. Incluímos:

- sete estatísticas: `quant instantiations`, `conflicts`, `decisions`, `propagations`,
  `arith conflicts`, `rlimit count`, `time`;
- até 20 grupos de quantificadores, até três instanciações por grupo;
- fórmulas, termos das substituições na ordem do callback e literais das cláusulas;
- identificação e resultado da consulta, motivo de `unknown` e limites do replay.

A seleção prioriza eventos associados ao candidato e operações relevantes;
limita grupos de representação e outros axiomas genéricos. Os tetos são máximos,
não promessas: eventos ausentes, fórmulas grandes e o espaço restante podem reduzir
o que é incluído. A seleção é heurística e não estabelece correspondência causal
entre uma consulta e uma linha do programa.

O prompt explica cada estatística e como formular uma hipótese de reparo sem
interpretar contadores como prova ou ausência de eventos como ausência na busca.
Os dados são de **reexecuções diagnósticas**, não da sequência original de busca.
Versões iguais do Z3 não garantem sequências idênticas.

## Executar no cluster

Atualize as pastas `solver_needs_study/`, `configs/`, `prompts/`, `scripts/`,
`tests/` e `docs/`. Mantenha as versões atuais de `baseline/`, `diagnostics/` e
`repair_study/`, usadas como dependências. Não sobrescreva seus resultados antigos.

Na raiz do projeto no cluster, execute:

```bash
cd /mnt/users/mariana.soares/code_verification
bash scripts/submit_solver_needs.sh
```

O comando agenda a preparação em CPU, a comparação dos dois braços em uma GPU
e o relatório final. Usa os parâmetros de partição/QoS já adotados no projeto;
a solicitação GPU é uma placa, 64 GB de RAM e limite de 24 horas.

A preparação baixa o dataset e reutiliza/baixa o modelo fixado. Instala uma versão
separada do **Verus 0.2026.02.22.2c9a6a0**, com **Z3 4.12.5** e Rust **1.93.0**,
para acompanhar o toolchain do dataset. Não recompila Verus nem substitui o bundle
dos experimentos anteriores. Os executáveis são extraídos em scratch local com
teste de execução ELF, evitando o armazenamento compartilhado problemático.
A primeira preparação precisa de acesso à rede para esses downloads e para Rust.
O helper desativa a instalação implícita de toolchains e usa `--no-self-update`
na instalação explícita, evitando que o rustup tente substituir seu próprio
executável entre os caminhos `/home` e `/mnt/users` do cluster.

Para um teste menor, use os seis primeiros IDs da mesma lista em outra pasta:

```bash
bash scripts/submit_solver_needs.sh results/solver-needs-qwen14b-smoke/seed-20261018 6
```

Para retomar a etapa GPU após interrupção, sem repetir inferências já salvas:

```bash
sbatch scripts/slurm/solver_needs_run.slurm results/solver-needs-qwen14b-100/seed-20261018
```

Para atualizar apenas o relatório:

```bash
python3 -m solver_needs_study compare --study results/solver-needs-qwen14b-100/seed-20261018
```

Não altere código, prompt, entradas ou classe de GPU durante uma retomada. Para
outra configuração, use outra pasta; hashes evitam misturar execuções diferentes.

## Resultados e limites

### Executar os 362 casos restantes

Após concluir a execução dos 100 casos **e seu relatório**, atualize
`solver_needs_study/`, `configs/`, `scripts/` e `tests/` no cluster. Não atualize
código enquanto uma execução estiver ativa: a verificação de hashes rejeita
mudanças durante execução/retomada. Preserve uma cópia do código anterior caso
precise retomar ou regenerar relatórios daquela execução posteriormente.

```bash
cd /mnt/users/mariana.soares/code_verification
bash scripts/submit_solver_needs_remaining.sh
```

Esse comando executa os mesmos dois braços, com o mesmo modelo, prompt, sementes,
limites de contexto e quatro propostas. Usa uma pasta separada:
`results/solver-needs-qwen14b-remaining362/seed-20261018`.

Os IDs estão fixados em `configs/solver-needs-tasks-remaining362.json`, que também
registra os 100 IDs excluídos. São o complemento exato dentro dos **462 casos
Verus/Z3 do benchmark do artigo**; não incluem os seis registros extras da
extração de 468 assertions. A lista é copiada para os resultados como
`selection.json` e `selected_ids.json`, com hashes no manifesto.

Distribuição: AX 156, INST-forall 62, INST-witness 32, NLA 90, FUEL 10, Other 12.
Não há reequilíbrio nem substituição por resultados de verificação/modelo.

O limite GPU continua em 24 horas. Se esse lote maior atingir o limite, retome
as propostas já salvas sem mudar código/configuração:

```bash
sbatch scripts/slurm/solver_needs_run.slurm results/solver-needs-qwen14b-remaining362/seed-20261018
```

Ao finalizar uma retomada, atualize o relatório com:

```bash
python3 -m solver_needs_study compare --study results/solver-needs-qwen14b-remaining362/seed-20261018
```

Leia `results/solver-needs-qwen14b-100/seed-20261018/comparison.md` e `comparison.json`.
Eles mostram resolvidas, sucessos acumulados por proposta, vitórias exclusivas,
erros de edição, repetições, exposição efetiva, tarefas pendentes e resultados por
rótulo. Há um `summary.json` por braço e pedidos/respostas/diagnósticos por tentativa.
Os custos de carregamento e da sessão compartilhada aparecem uma vez em `session-*.json`.

O subconjunto é estratificado e pequeno; sucesso de reparo não é acurácia de
classificação nem desempenho sobre todo VerusBench. A disponibilidade real de
instanciações deve ser inspecionada antes de atribuir diferenças aos internals.
Os testes locais verificam a preparação sem as quatro checagens, montagem dos
prompts, restrições, quatro propostas e retomada. A execução real do novo Verus
Linux e da inferência GPU fica para o cluster.
