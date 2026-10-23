# Rodada curta: quais informações fornecer ao LLM?

O experimento não chama o LLM, não modifica candidatos e não executa os 150
problemas. Reúne controles com solução conhecida e cinco candidatos reais para
inspecionar conteúdo, disponibilidade, tamanho e estabilidade dos dados do Z3.

## Executar no cluster

Envie a pasta `diagnostics/` atualizada e o arquivo
`scripts/slurm/z3_exposure.slurm`. O restante do projeto e as ferramentas já
preparadas são reutilizados; não precisa reenviar baseline/configs/prompts.

```bash
cd /mnt/users/mariana.soares/code_verification
mkdir -p logs
sbatch scripts/slurm/z3_exposure.slurm
```

O caminho padrão para os candidatos é
`results/qwen25coder14b-v3-150/seed-20261018/full/instruct`.
Para outro caminho, passe-o como primeiro argumento do sbatch.
O segundo argumento opcional escolhe uma pasta nova de saída.

## Casos incluídos

1. **SMT aritmético SAT**: hipóteses `x >= 0` e objetivo `x > 0`.
   Consulta `x >= 0 AND NOT(x > 0)`: o único valor inteiro é x=0.
   Grava modelo e get-value de x e das duas expressões. O relatório exige SAT
   com modelo nesse controle; se não acontecer, o job retorna erro.
2. **SMT quantificado SAT**: `forall j, f(j) >= 0` e `f(0)=0`.
   A interpretação f constante zero satisfaz a fórmula. Não impõe os axiomas
   de biblioteca nem as opções do Verus. O resultado é observado, não forçado.
3. **Controle Verus aritmético**: uma pós-condição propositalmente falsa, com
   as mesmas condições x>=0 / x>0. Inclui a codificação real do Verus, que pode
   retornar UNKNOWN por seus axiomas/opções apesar de o controle SMT ser SAT.
4. **Cinco candidatos iniciais reais salvos do v3**:
   - cloverbench_array_copy_strong: pré-condição;
   - diffy_condn: invariante;
   - mbpp_task_id_3: pós-condição;
   - mbpp_task_id_170: invariante/aritmética;
   - misc_arg_free: aritmética/assertion.

Os cinco arquivos foram identificados nos resultados v3 enviados pelo usuário.
Não são soluções de referência. Se um arquivo não existir no caminho indicado,
o caso é marcado como ausente e não é inventado nem gerado novamente.

O SAT do controle não pode ser apresentado como SAT em uma obrigação real do
VerusBench. O relatório separa explicitamente essas origens. A confirmação do
controle básico não garante que todos os outros casos tenham dados disponíveis.

## Coleta e comparação

Para cada prova Verus, captura os retornos originais e examina no máximo uma
consulta SAT/UNKNOWN. Cada consulta selecionada recebe:

- replay CLI no mesmo binário, para razão, modelo e estatísticas;
- replay API para instâncias, bindings, cláusulas e hints;
- controle API com rlimit=1, claramente identificado, nos casos Verus;
- três replays CLI adicionais para comparar resultados observados;
- tamanhos em bytes/caracteres e, se o tokenizer Coder já estiver no cache
  local, tokens exatos de cada bloco de texto e da prévia. Não baixa tokenizer
  nem modelo; contagens não disponíveis ficam nulas.

Amostras agora são separadas: até 20 assumptions, 100 instâncias, 100 eventos
de outras inferências e 100 deleções. Os contadores incluem todos os eventos
observados, não apenas os salvos. `search-inferences.jsonl` contém outros hints,
sem afirmar automaticamente que todos são lemas de teoria ou provas reutilizáveis.
`rules_observed` mostra quais regras realmente apareceram. Dependências vazias
continuam vazias; não é reconstruído um grafo artificial.

Três resultados iguais sugerem estabilidade observada, mas não provam identidade
dos modelos, das trajetórias de busca ou das cláusulas. API e CLI são separados,
pois usam builds diferentes da mesma versão do Z3. Modelos de UNKNOWN permanecem
não validados; modelos vazios são identificados como tal.

## Onde olhar

Pasta principal: `results/z3-exposure/job-ID/`.

- `report.md`: tabela geral para começar a leitura;
- `report.json`: resultados por caso, disponibilidade, eventos e estabilidade;
- `progress.json`: progresso enquanto os casos reais são executados;
- `controls/sat_arithmetic/cli.values.txt`: x=0, hipótese verdadeira e objetivo
  falso, se o solver completar como esperado;
- `controls/`: dados completos dos dois controles SMT;
- `verus-cases/`: captura original e diagnósticos para cada prova.

Em cada pasta de consulta/control:

- `api/report.json`: resultado, motivo, modelo e contagens por regra;
- `api/instantiations.jsonl`: quantificadores e bindings;
- `api/search-inferences.jsonl`: amostra que não é ocupada por assumptions;
- `api/clauses.jsonl`: amostras de todas as categorias;
- `stability.json` e `repeat-cli/`: três replays da mesma consulta;
- `payload-sizes.json`: custo de cada bloco;
- `package-preview.txt`: prévia de um pacote possível, sem envio ao LLM.

A prévia apenas concatena trechos com limite fixo, mantendo início e fim quando
necessário. Pode conter SMT/JSON incompleto e é identificada como prévia; os dados
completos ficam preservados. Não há JE, LLM auxiliar ou tradução semântica.

## Limites operacionais

Usa a inicialização Slurm já testada e reserva uma GPU para compatibilidade com
o preflight existente, mas não faz inferência nem carrega pesos. Limite do job:
uma hora. Z3 Python 4.12.5.0 é instalado somente em scratch isolado, como no teste
anterior. Falhas de instalação são registradas; a captura CLI pode continuar.
Use nova pasta para repetir o estudo. Nenhum resultado anterior é sobrescrito.

Validação local focada verifica a separação das amostras, a leitura de SAT e dos
valores e a preparação dos controles. Os resultados reais precisam ser medidos
no cluster; não há alegação de SAT observado localmente sem o Z3 instalado.
