# Auditoria detalhada do experimento C — 21/10/2026

Fonte: download_2026-10-21_22-25-20.zip. Análise somente de arquivos salvos;
nenhuma execução de conteúdo do ZIP, solver ou LLM. O experimento não foi alterado.

## Achados confirmados

- 262/262 payloads JSON foram encontrados literalmente nos requests da tentativa seguinte.
- 149 feedbacks continham internals disponíveis. Os demais 113 tinham motivo
  no_captured_sat_or_unknown_query, não divergência de resultado registrada.
- Depois dos 149 feedbacks disponíveis, 130 candidatos foram repetidos byte a byte
  (87,2%). Nos 262 reparos totais, foram 201 repetições (76,7%). No ZIP v4 anterior,
  foram 196/261 (75,1%): o comportamento já existia sem internals.
- Dos 149 reparos com internals disponíveis: 138 continuaram classificados como
  verificação, 10 passaram a compilação e 1 a sintaxe. Desses 138, 130 repetiram
  exatamente o candidato; 8 mudaram o código e continuaram falhando na verificação.
- Foram enviados 1429 grupos de quantificadores: 566 com qids do prelude,
  839 de biblioteca/codificação e somente 24 grupos com qid contendo candidate.
  A classificação usa os nomes dos qids, não demonstra relevância lógica.
- Só 12/149 payloads disponíveis continham algum grupo com qid contendo candidate.
  Só 6/149 continham grupo com qid user_candidate; estes 6 cobrem 3 tarefas.
- Os arquivos brutos continham eventos user_candidate em 36 feedbacks, mas a
  seleção excluiu todos eles em 30 desses casos. É uma perda de seleção observável,
  não apenas falta de capacidade do modelo.
- O quantificador prelude_u_inv apareceu em 137 payloads; axiomas de box/unbox
  de raw_ptr.Metadata em 134 e 133, respectivamente. São grupos por payload.
- Motivos dos replays disponíveis: 140 incomplete quantifiers e 9 incomplete
  (theory arithmetic). Tempos reportados: mínimo 0,017 s, mediana 0,121 s,
  máximo 0,304 s. Estes replays não falharam pelo timeout de 5 s.

## Exemplos

cloverbench_array_append_strong: o candidato tem n <= len, mas não mantém
explicitamente a relação len == v.len() no invariante. O erro reportado é a
precondição de v[n]. Os dez quantificadores enviados têm qids de biblioteca,
codificação e prelude. O evento user_candidate__append_29 já aparece no registro
bruto 51, mas não entrou no payload. O reparo devolveu exatamente o mesmo código.
Acrescentar a relação de comprimento é uma hipótese concreta a validar no Verus,
não um resultado provado por esta auditoria.

mbpp_task_id_3: o erro é a pós-condição existencial no retorno true. O candidato
já tem um invariante que exclui divisores anteriores. O passo a investigar é a
justificação do índice corrente como testemunha e a relação entre módulo em
inteiro de máquina e na especificação. O payload tem cinco grupos do prelude,
sem grupo source-candidate. O modelo repete exatamente o arquivo.

## Próximas mudanças sugeridas, ainda não implementadas

1. Priorizar qids do candidato e operações/termos associados ao erro antes de
   aplicar os tetos de quantidade e tokens. Reservar somente uma pequena cota
   para axiomas de representação e prelude. Não excluir toda a biblioteca:
   axiomas de Seq/Vec podem ser relevantes.
2. Mostrar a obrigação-fonte que falhou, contexto do loop/retorno e vínculos
   comprovados entre nomes SMT e fonte. Não inferir localização só do número
   no qid. Manter origem e fórmulas brutas para auditoria.
3. Pedir uma alteração localizada e verificável nas anotações, tratando saída
   idêntica como ausência de progresso. Não fazer gerações extras escondidas.
4. Resumir estatísticas; priorizar instâncias relevantes, em vez de expandir
   instruções genéricas sobre conflitos, tempo e recursos. Os contadores não
   identificam automaticamente a causa da falha.
5. Pilotar reparos pareados dos mesmos candidatos, com as mesmas instruções,
   diagnóstico e orçamento, variando somente a exposição dos internals filtrados.
   Registrar mudança efetiva, compilação, integridade e aprovação final.

As hipóteses de reparo e de seleção não foram testadas neste relatório. A evidência
não permite concluir que o feedback filtrado terá ganho ou que o modelo em geral
não consegue usar internals. A seleção usada nesta execução tem uma limitação
concreta que deve ser corrigida antes de aumentar volume ou considerar finetuning.
