# Experimento B: obrigação SMT exposta

Mantém o Qwen2.5-Coder-14B-Instruct e a revisão da v4, BF16, os mesmos 150
problemas em ordem de ID, seed, sampling, prompt v4, 4096 tokens de saída,
uma geração inicial e até dois reparos. Verus e integridade continuam sendo
obrigatórios. O modelo continua produzindo apenas código Verus com as mesmas
anotações de prova permitidas; não ganha ferramentas nem pode editar SMT,
opções do solver, implementação ou contratos.

A geração inicial recebe exatamente os mesmos textos de prompt da v4.
Nos reparos, além dos diagnósticos convencionais e de integridade, recebe
os resultados das consultas e uma consulta completa que caiba no contexto.
Ela inclui declarações, hipóteses e a codificação da obrigação com o objetivo
negado, conforme enviada pelo Verus. Não há reconstrução manual do objetivo.

A captura usa um proxy transparente na chamada original ao mesmo binário Z3.
Não muda parâmetros, não repete a verificação e não solicita modelos,
estatísticas, reason-unknown, provas ou instanciações. Opções já presentes
no próprio protocolo permanecem na consulta. Não se trata de um novo modo
de interação direta do modelo com o solver.

## Política de contexto

O contexto permanece em 32768 tokens. O código conta os tokens com o tokenizer
do modelo e o chat template real, reservando os mesmos 4096 tokens de saída.
Escolhe a primeira consulta completa com resultado sat/unknown/timeout que
caiba, na ordem dos arquivos capturados e das consultas em cada arquivo.
Se todas as consultas forem unsat, considera a primeira que caiba.
Não há seleção semântica nem associação inferida a uma linha do código.

Se nenhuma couber, expõe apenas a contagem dos resultados e informa a omissão.
Não corta fórmulas. Isso importa: consultas reais anteriores ultrapassaram
32 mil tokens. Portanto nem todo reparo receberá uma consulta completa.
Erros de sintaxe/tipos podem ocorrer antes de qualquer consulta SMT.
Não confundir essa ausência com unknown. Capturas desalinhadas são registradas
como erro, sem inventar resultados. Timeout significa uma consulta sem resposta
interrompida pelo limite externo; unknown continua sendo unknown, sem inferir
que sua causa foi timeout.

unsat comprova somente aquela consulta; sat indica satisfatibilidade da
consulta; unknown é inconclusivo. Nenhum desses rótulos isoladamente significa
aceitação do programa completo pelo Verus e pelo filtro de integridade.

## Enviar e executar

Envie as pastas atualizadas `baseline/`, `diagnostics/`, `configs/`, `scripts/`
e `tests/`. Os prompts v4 em `prompts/v4/` também precisam estar presentes.
Reutilize `data/`, `.cluster/`, o modelo e os binários já preparados.
Não precisa recompilar ferramentas nem instalar o pacote Python z3-solver.

Na raiz do projeto no cluster:

```bash
cd /mnt/users/mariana.soares/code_verification
mkdir -p logs
sbatch scripts/slurm/qwen25coder14b_b_150.slurm
```

O job testa Verus/integridade e a captura real de uma obrigação falha antes de
carregar o modelo. Tem os mesmos recursos e limite de 24 horas da v4. Se for
interrompido, reenvie o mesmo comando com os mesmos arquivos para retomar.
É uma execução nova: não reutiliza candidatos da v4.

## Resultados e auditoria

Diretório: `results/qwen25coder14b-b-150/seed-20261018/full/instruct/`.

- `report.md` e `summary.json`: resultados usuais; `summary.json` também inclui
  `solver_exposure` com a cobertura de consultas completas no feedback de reparo.
- Em cada tentativa, `solver/capture/`: protocolo original; `solver/query-*.smt2`:
  consultas completas com o contexto incremental; `solver/report.json`: resultados
  e erros de captura.
- Nas tentativas que levam a reparo, `solver/exposure.json` registra a consulta
  selecionada ou a omissão; `solver/feedback.txt` guarda o feedback preparado.
- `request.json` e `rendered_prompt.txt` na tentativa seguinte mostram o que
  foi efetivamente fornecido ao modelo.

Compare a taxa de sucesso final e após cada reparo com a v4, mas também informe
a cobertura de consultas completas. Os resultados iniciais são uma checagem de
consistência, pois os novos dados aparecem somente nos reparos. A captura pode
adicionar custo de I/O e afetar tempos próximos do limite, embora preserve o
protocolo e os parâmetros. Não atribua automaticamente variações ao conteúdo
do feedback sem considerar isso.

Os testes locais usam consultas e inferência simuladas para verificar alinhamento,
limite de contexto, preservação da configuração e retomada. A integração real
com Verus/Z3 é testada no início do job no Linux; não foi executada localmente.
