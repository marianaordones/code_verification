# Auditoria de contexto: Solver Needs, primeiros 100 casos

Fonte: `results/download_2026-10-23_21-25-20.zip`.
Leitura dos artefatos salvos; sem inferência nem execução do solver.

## Contexto total

- 667 pedidos: 319 com internals e 348 sem internals.
- Contagem com o tokenizer da revisão aedcc2d42b622764e023cf882b6652e646b95671: nenhuma divergência dos tokens de entrada registrados.
- Com internals: mínimo 4.491, mediana 16.816, máximo 23.245 tokens.
- Sem internals: mínimo 4.063, mediana 6.414,5, máximo 11.283 tokens.
- Menor espaço livre após reservar 4.096 tokens de saída: 21.811 tokens.
- Nenhuma resposta truncada.

## Exposição de quantificadores

- 240/319 pedidos do braço com internals receberam o bloco; 79 não receberam.
- Blocos expostos: mediana 12.215 tokens, máximo 12.288.
- Grupos enviados por bloco: mediana 12, máximo 20.
- 35 pedidos atingiram 20 grupos; 207 tiveram algum grupo disponível omitido.
- 54 pedidos, em 19 casos distintos, omitiram grupos associados ao candidato.
- Grupos associados a anotações: 641 disponíveis, 427 enviados, 214 omitidos.
- Grupos associados a definições: 855 disponíveis, 663 enviados, 192 omitidos.

As contagens de grupos são ocorrências ao longo dos pedidos, não quantificadores
únicos em todo o dataset. Relevância é a categoria heurística do código, não
uma relação causal estabelecida. A disponibilidade considera os eventos salvos
de reexecuções concordantes e que poderiam alimentar o pedido enviado.

Os testes de acrescentar um primeiro evento omitido ao payload final excedem
o orçamento de internals nos 54 pedidos com grupos do candidato omitidos.
Esses são testes marginais sobre o pacote final, não uma reconstrução da ordem
cronológica de todas as decisões do empacotador.

## Limites anteriores ao prompt

- Nenhum pedido tinha mais de três consultas SAT/UNKNOWN capturadas; esse teto não cortou consultas nos pedidos auditados.
- Quatro replays discordantes foram excluídos.
- Onze relatórios de replay tinham 128 grupos salvos, o teto do reservatório.
- Nenhum qid observado associado ao candidato ficou totalmente ausente dos grupos salvos nas reexecuções concordantes auditadas.
- Nenhum erro de callback nos 269 relatórios concordantes examinados.

A amostra não cobre todos os eventos da busca: o worker guarda até quatro
eventos por grupo e o feedback envia até três. Não é possível inferir relevância
semântica nem ausência de eventos da busca original a partir desses arquivos.

## Conclusão

O contexto de 48k foi suficiente para todos os prompts enviados. O limite interno
de 12k deixou grupos do candidato fora apesar de haver folga no contexto total.
Ampliar o orçamento do bloco é uma intervenção mais diretamente motivada por
esta auditoria do que ampliar o contexto total. O teto de 20 grupos também foi
atingido, mas não foi o único nem o principal indício de limitação observado.
Isso demonstra espaço para expor mais material, não que ele aumentará o sucesso.

Detalhes reproduzíveis: summary.json, feedbacks.json, queries.json e prompts.json.
