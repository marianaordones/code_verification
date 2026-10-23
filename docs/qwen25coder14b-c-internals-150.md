# Experimento C: estatísticas e instanciações, sem consulta SMT no prompt

## Configuração

Qwen2.5-Coder-14B-Instruct na mesma revisão fixada; 150 problemas oficiais,
ordem por ID, BF16, contexto de 32768, saída máxima 4096, seed 20261018,
temperature 0.7, top_p 0.8, top_k 20, geração inicial e até dois reparos.
Sem YaRN e sem offload de pesos. Mesmos Verus, Z3 original e integridade.
Não altera implementação/contratos nem amplia as ações permitidas ao modelo.

O prompt `v4-internals` contém cópias exatas do system/initial/repair v4,
com o acréscimo `prompts/v4-internals/solver-info.txt` ao system. Essa instrução
também aparece na geração inicial. Portanto o resultado inicial pode diferir
do v4, e comparar com v4 não isola somente o efeito dos eventos de busca.

## Extração

1. O candidato passa por Verus e integridade normalmente. O proxy existente
   salva os protocolos originais sem inserir comandos ou alterar parâmetros.
2. Só se a tentativa falhar e ainda houver reparo, seleciona a primeira consulta
   capturada com resultado `sat` ou `unknown`, na ordem dos arquivos/consultas
   usada pelo capturador. Não se infere qual linha-fonte ela representa.
3. Reexecuta somente essa consulta em processo Python separado, com pacote
   `z3-solver==4.12.5.0` isolado. Preserva o prefixo SMT capturado e aplica
   timeout de 5000 ms. Não força rlimit=1, candidate_models, sat.euf, prova
   ou qi.profile. Não reproduz o histórico de busca da chamada original.
4. A implementação aceita somente um `check-sat` simples; consultas com
   assumptions ou tactics são marcadas como indisponíveis, sem aproximação.
5. Registra `OnClause`, filtra a regra `inst` e conta todos os eventos observados.
   Salva até 200 eventos, omitindo inteiros aqueles com mais de 64000 caracteres.
   Não corta expressões. Não solicita modelo, prova, core ou fluxo geral de cláusulas.
6. Após `check`, obtém resultado, `reason_unknown()` e `statistics()`. O processo
   inteiro tem limite externo de 20 s (5 s de solver + 15 s para import/parse/log).
7. Só fornece estatísticas e eventos quando o replay completar com o MESMO
   resultado original. Divergências/indisponibilidade ficam explícitas.
8. Sem consultas, envia um bloco de indisponibilidade junto aos diagnósticos
   convencionais. Não inventa uma consulta ou troca por uma consulta UNSAT.

Não existe tradução de SMT para Verus, identificação semântica do quantificador
do usuário, reconstrução de dependências ou modelo auxiliar. Eventos podem ser
de axiomas de fundo. Os termos `bind` são preservados na ordem bruta do callback,
sem inventar correspondência com nomes de variáveis do código-fonte.

## Formato exato entregue ao modelo

O user prompt de reparo mantém o original, candidato e diagnósticos do v4.
Depois dos diagnósticos de integridade, seu feedback recebe:

```text
<solver_internals>
{ ... JSON ... }
</solver_internals>
```

O exemplo completo de todos os campos está em
`docs/solver-internals-payload-example.json`. É ILUSTRATIVO, não é um novo
resultado de medição. A estrutura é produzida por `baseline/internals.py`.

| Campo JSON | Significado |
|---|---|
| schema | Versão do formato, z3-internals-v1 |
| scope | diagnostic_api_replay_not_original_search: origem dos dados |
| availability | available somente quando replay completou e resultado coincide |
| original_query_counts | Contagens originais de todas as consultas capturadas nessa tentativa |
| capture_errors | Número de problemas de captura registrados |
| query_id | Identificador local da consulta selecionada, não localização fonte |
| original_result | Resultado da consulta na execução original |
| replay_result | Resultado da reexecução, ou null se indisponível |
| reason_unknown | Motivo de UNKNOWN do replay, não da execução original |
| replay_timeout_ms | Timeout configurado para a reexecução |
| unavailability_reason | Código de ausência/divergência, ou null |
| statistics | Sete métricas selecionadas; null quando não disponíveis |
| sampling | Quantidade de eventos observados/salvos, erros e amostra enviada |
| quantifiers | Grupos de quantificadores e suas instâncias selecionadas |

As sete métricas são `quant instantiations`, `conflicts`, `decisions`,
`propagations`, `arith conflicts`, `rlimit count`, `time`. São respectivamente
contagens de instanciações, conflitos, decisões, propagações, conflitos
aritméticos, recursos internos e tempo reportado pelo solver em segundos.
Não medem correção ou distância até uma prova. Campos ausentes são null, não 0.

O acréscimo ao prompt agora detalha cada contador e separa sua definição de
hipóteses de reparo: instanciação de um caso relevante com prova dos limites,
assertions intermediárias, divisões de casos somente em blocos de prova,
condições laterais aritméticas e lemas auxiliares. Os valores não identificam
automaticamente a causa da falha. Não há limiares numéricos arbitrários,
inferência de timeout só pelo tempo, diagnóstico de trigger só pela contagem
ou comparação inventada com tentativas anteriores. Essas estratégias são
heurísticas do experimento, não prescrições ou garantias da documentação Z3.
As instruções adicionais também consomem o contexto total de 32768 tokens;
o orçamento do pacote continua sendo um teto de 12288, não uma reserva fixa.

Cada grupo contém `id` (Q1, Q2...), `quantifier_smt` (fórmula completa) e
`instances`. Cada instância contém `binding_terms_callback_order` (termos
brutos de bind) e `clause_literals_smt` (lista de literais disjuntos). Os
literais NÃO são fatos simultaneamente verdadeiros: guardar guardas e polaridade
é essencial. As fórmulas são fragmentos diagnósticos, não a consulta completa.

## Seleção e orçamento

Até 12288 tokens adicionais (12k), INCLUINDO metadados JSON e delimitadores, contados
com o tokenizer do modelo. O prompt inteiro com chat template deve ainda caber
em 32768 tokens, reservando 4096 para saída. Não aumenta silenciosamente o contexto.

Percorre eventos salvos na ordem observada, agrupa pela fórmula exata, remove
instâncias idênticas e aceita a primeira que caiba, até 10 quantificadores e
3 instâncias por quantificador. Se um evento não couber, é omitido inteiro e
o próximo é considerado. Não há ranking por suposta relevância. Metadados de
amostragem informam observados/salvos/incluídos e erros de callback. A ausência
na amostra não significa ausência na busca. Zero é diferente de indisponível.

Um motivo textual excepcionalmente grande pode ser omitido inteiro para
preservar o orçamento; o relatório bruto continua salvo. Se nem o pacote
mínimo com o programa couber, registra erro de infraestrutura em vez de cortar
o código ou as mensagens. Estatísticas e eventos nunca decidem aceitação:
somente Verus e integridade do novo candidato.

## Execução no cluster

IMPORTANTE: não substitua arquivos usados pelo job B/96k ainda em execução.
Transfira após ele terminar ou use uma cópia separada do projeto.

Envie `baseline/`, `diagnostics/`, `prompts/`, `configs/`, `scripts/` e `tests/`
atualizados. Mantenha dados, ferramentas e modelo já preparados. O job instala
somente a API Z3 4.12.5.0 em scratch nativo, sem alterar o ambiente do vLLM.
O acesso pip/cache é necessário para esse pacote. Falha na instalação ou no
autoteste impede carregar o modelo e iniciar o benchmark.

Se ocorrer `ZMQError: Input/output error` em `ipc:///home/.../pylibs/.tmp/...`,
atualize `scripts/cluster/setup_runtime.sh` e `scripts/cluster/prepare_ipc.py`.
O runtime agora define `VLLM_RPC_BASE_PATH` em um diretório curto validado
por um teste real ZMQ de bind/envio/recepção em `/tmp` ou `/var/tmp`, antes
de carregar o modelo. O fallback HOME para temporários grandes de instalação
não será usado para esses sockets. O log deve mostrar
`vllm_rpc_base_path=... (ZMQ IPC probe passed)`.
Se os diretórios padrão não suportarem IPC, configure em `cluster.env`:
`export CLUSTER_IPC_TMP=/caminho/curto/no/scratch/local`.
O ajuste não muda modelo, prompt, sampling, candidatos ou fingerprint do
experimento; reenvie o mesmo job sem apagar resultados anteriores.

```bash
cd /mnt/users/mariana.soares/code_verification
mkdir -p logs
sbatch scripts/slurm/qwen25coder14b_c_internals_150.slurm
```

Uma GPU, 8 CPUs, 64 GB e 24 h, na mesma partição/qos. Não foi submetido
automaticamente. O job faz um autoteste SAT quantificado da API isolada, testes
reais de ferramentas/captura e os testes do pacote de feedback antes da inferência.
O autoteste não representa uma execução do VerusBench nem chama o LLM.

Resultados: `results/qwen25coder14b-c-internals-150/seed-20261018/full/instruct/`.
Para retomar, reenvie sem alterar arquivos/configuração. Não reutiliza candidatos
anteriores como gerações desta execução.

## Auditoria, custo e limitações

Cada tentativa mantém `solver/capture/`, consultas e resultados originais.
Nas tentativas com reparo, `internals/replay/` contém eventos, relatório API
e stdout/stderr do processo; `internals/payload.json` é o objeto enviado;
`internals/feedback.txt` é o feedback completo; `internals/exposure.json`
registra tokens/cobertura/tempo. O request e prompt da tentativa seguinte
confirmam a entrega efetiva. Não confundir feedback preparado com entregue
se houver interrupção.

`summary.json` acrescenta `solver_internals` com cobertura de estatísticas e
instâncias, disponibilidade, tokens e tempo de replay/empacotamento. Esse
tempo também entra no custo da tentativa, sem duplicação ao retomar. O binário
Z3 original e a biblioteca API têm hashes separados na proveniência; a biblioteca
API participa do fingerprint. O replay pode divergir mesmo na mesma versão.

Um teste futuro com controle deve manter as mesmas instruções, replays e
metadados nas duas condições, variando somente os dados internos entregues.
Este código implementa a condição com dados internos, não uma ablação pareada.
Não garante aumento da taxa de prova e não resolve falhas anteriores à geração SMT.

## Fontes oficiais usadas no acréscimo ao prompt

- Quantificadores/padrões/incompletude: https://microsoft.github.io/z3guide/docs/logic/Quantifiers/
- Callback e hints de instanciação: https://microsoft.github.io/z3guide/programming/Proof%20Logs/
- Resultado, motivo e estatísticas: https://z3prover.github.io/api/html/classz3py_1_1_solver.html
- Chaves de estatísticas: https://z3prover.github.io/api/html/classz3py_1_1_statistics.html

As instruções sobre limites, amostragem, proveniência e ações permitidas são
decisões deste experimento, não recomendações de eficácia feitas pelo Z3.
