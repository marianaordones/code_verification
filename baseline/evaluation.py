from collections import Counter
from pathlib import Path
from statistics import mean, median
import re

from .storage import digest, read_json, write_json, write_text
from .provenance import tool_signature


def summarize(tasks, expected, budget):
    attempts = [a for t in tasks for a in t["attempts"]]
    solved = sum(t["success"] for t in tasks)
    initial_failures = [t for t in tasks if not t["attempts"][0]["success"]]
    total = sum(t["total_seconds"] for t in tasks)
    successes = {str(k): (sum(t["first_success"] is not None and t["first_success"] <= k
                             for t in tasks) / expected if expected else None)
                 if k <= budget else None for k in (0, 1, 2, 3, 5)}
    return {"expected_tasks": expected, "completed_tasks": len(tasks), "solved": solved,
            "success_at": successes, "complete": len(tasks) == expected,
            "repair_rate": (sum(t["success"] for t in initial_failures) / len(initial_failures)
                            if initial_failures else None),
            "attempts": len(attempts),
            "inference_mean_seconds": mean(a["inference_seconds"] for a in attempts) if attempts else None,
            "inference_median_seconds": median(a["inference_seconds"] for a in attempts) if attempts else None,
            "task_mean_seconds": mean(t["total_seconds"] for t in tasks) if tasks else None,
            "task_median_seconds": median(t["total_seconds"] for t in tasks) if tasks else None,
            "total_active_seconds": total,
            "seconds_per_solved": total / solved if solved else None,
            "tokens_per_solved": sum(a["output_tokens"] for a in attempts) / solved if solved else None,
            "verification_seconds": sum(a["verification_seconds"] for a in attempts),
            "input_tokens": sum(a["input_tokens"] for a in attempts),
            "output_tokens": sum(a["output_tokens"] for a in attempts),
            "reasoning_tokens": sum(a["reasoning_tokens"] for a in attempts),
            "final_tokens": sum(a["final_tokens"] for a in attempts),
            "output_tokens_per_attempt": mean(a["output_tokens"] for a in attempts) if attempts else None,
            "truncated": sum(a["truncated"] for a in attempts),
            "truncation_rate": mean(a["truncated"] for a in attempts) if attempts else None,
            "invalid_modifications": sum(a["invalid_modification"] for a in attempts),
            "integrity_statuses": dict(Counter(a.get("integrity_status", "legacy_unknown") for a in attempts)),
            "errors": dict(Counter(a["error_type"] for a in attempts if a["error_type"])),
            "error_rates_per_attempt": {kind: count / len(attempts) for kind, count in
                                        Counter(a["error_type"] for a in attempts if a["error_type"]).items()},
            "planning_150_tasks_6_attempts_hours": (
                150 * 6 * mean(a["total_seconds"] for a in attempts) / 3600 if attempts else None)}


def aggregate(run_dir):
    root = Path(run_dir)
    metadata = read_json(root / "run.json")
    selected = metadata["tasks"]
    tasks = [read_json(root / t["id"] / "task.json") for t in selected
             if (root / t["id"] / "task.json").exists()]
    summary = summarize(tasks, len(selected), metadata["config"]["max_repairs"])
    if metadata["config"].get("solver_feedback") == "internals":
        exposures = [read_json(path) for t in tasks
                     for path in (root / t["id"]).glob("attempt_*/internals/exposure.json")]
        summary["solver_internals"] = {
            "repair_feedbacks": len(exposures),
            "feedbacks_with_instances": sum(e["has_instances"] for e in exposures),
            "feedbacks_with_statistics": sum(e["statistics_available"] for e in exposures),
            "availability": dict(Counter(e["availability"] for e in exposures)),
            "replay_and_packaging_seconds": sum(e["seconds"] for e in exposures),
            "extra_tokens": sum(e["extra_tokens"] for e in exposures)}
    if metadata["config"].get("solver_feedback") == "obligation":
        exposures = [(t["id"], read_json(path)) for t in tasks
                     for path in (root / t["id"]).glob("attempt_*/solver/exposure.json")]
        summary["solver_exposure"] = {
            "repair_feedbacks": len(exposures),
            "feedbacks_with_complete_query": sum(e["complete_query_exposed"] for _, e in exposures),
            "feedbacks_without_complete_query": sum(not e["complete_query_exposed"] for _, e in exposures),
            "omission_reasons": dict(Counter(e["omission_reason"] for _, e in exposures if not e["complete_query_exposed"])),
            "problem_ids_with_complete_query": sorted({tid for tid, e in exposures if e["complete_query_exposed"]}),
            "scope": "feedbacks prepared for repair; inspect saved requests for the actual prompts"}
    syntax_ids, type_ids = set(), set()
    syntax_attempts = type_attempts = audited = 0
    for task in tasks:
        for attempt in task["attempts"]:
            path = root / task["id"] / f"attempt_{attempt['attempt']:02}" / "verification.json"
            if not path.exists():
                continue
            verification = read_json(path)
            headers = "\n".join(line for line in
                                (verification["stdout"] + "\n" + verification["stderr"]).splitlines()
                                if re.match(r"^error(?:\[|:)", line))
            syntax = any(token in headers for token in ("expected one of", "unexpected token",
                         "unclosed delimiter", "expected `", "expected curly braces"))
            typed = "error[E0308]" in headers
            audited += 1
            syntax_attempts += syntax
            type_attempts += typed
            if syntax:
                syntax_ids.add(task["id"])
            if typed:
                type_ids.add(task["id"])
    summary["diagnostics"] = {"audited_attempts": audited, "syntax_attempts": syntax_attempts,
                              "type_mismatch_attempts": type_attempts,
                              "problems_with_syntax_errors": len(syntax_ids),
                              "problems_with_type_mismatches": len(type_ids),
                              "syntax_problem_ids": sorted(syntax_ids),
                              "type_mismatch_problem_ids": sorted(type_ids)}
    summary["stage"] = metadata["stage"]
    summary["mode"] = metadata["config"]["mode"]
    summary["run_fingerprint"] = metadata["fingerprint"]
    sessions = [read_json(path) for path in root.glob("session_*.json")]
    summary["model_load_seconds"] = sum(s["model_load_seconds"] for s in sessions)
    summary["seconds_per_solved_including_model_load"] = (
        (summary["total_active_seconds"] + summary["model_load_seconds"]) / summary["solved"]
        if summary["solved"] else None)
    summary["completed_session_wall_seconds"] = sum(s.get("wall_seconds_including_model_load", 0) for s in sessions)
    summary["interrupted_sessions"] = sum("wall_seconds_including_model_load" not in s for s in sessions)
    summary["session_gpus"] = [s["provenance"]["gpu"] for s in sessions]
    summary["categories"] = {
        c: summarize([t for t in tasks if t["category"] == c],
                     sum(t["category"] == c for t in selected), metadata["config"]["max_repairs"])
        for c in sorted({t["category"] for t in selected})}
    summary["missing_tasks"] = [t["id"] for t in selected if not (root / t["id"] / "task.json").exists()]
    summary["infrastructure_failures"] = {
        t["id"]: read_json(root / t["id"] / "task_error.json") for t in selected
        if (root / t["id"] / "task_error.json").exists() and t["id"] in summary["missing_tasks"]}
    write_json(root / "summary.json", summary)
    return summary


def pilot_report(thinking_dir, nonthinking_dir, output):
    dirs = [Path(thinking_dir), Path(nonthinking_dir)]
    metadata = [read_json(d / "run.json") for d in dirs]
    if [m["config"]["mode"] for m in metadata] != ["thinking", "nonthinking"]:
        raise ValueError("Expected thinking and nonthinking runs, in that order")
    if any(m["stage"] != "pilot" or m["config"]["max_repairs"] != 2 for m in metadata):
        raise ValueError("Report requires pilot runs with two repairs")
    count = metadata[0]["config"].get("pilot_size", 15)
    if (metadata[0]["tasks"] != metadata[1]["tasks"] or len(metadata[0]["tasks"]) != count
            or count != metadata[1]["config"].get("pilot_size", 15)):
        raise ValueError("Pilot runs must contain the same frozen task selection")
    for key in ("experiment", "model", "model_revision", "prompt_version", "task_selection", "seed", "max_num_seqs"):
        if metadata[0]["config"].get(key) != metadata[1]["config"].get(key):
            raise ValueError(f"Pilot configuration differs: {key}")
    # These fields must stay constant in this paired comparison.
    for key in ("sources", "prompts", "verus", "z3", "lynette", "model_revision", "versions"):
        if tool_signature(metadata[0]["provenance"][key]) != tool_signature(metadata[1]["provenance"][key]):
            raise ValueError(f"Pilot environment differs: {key}")
    if metadata[0]["provenance"].get("dependency_lock_sha256") != metadata[1]["provenance"].get("dependency_lock_sha256"):
        raise ValueError("Pilot dependency locks differ")
    summaries = [aggregate(d) for d in dirs]
    initial_gpu = metadata[0]["provenance"]["gpu"]
    homogeneous_gpu = (metadata[1]["provenance"]["gpu"] == initial_gpu
                       and all(gpu == initial_gpu for s in summaries for gpu in s["session_gpus"]))
    complete = all(s["complete"] for s in summaries)
    paired = Counter()
    if complete:
        for task in metadata[0]["tasks"]:
            outcomes = [read_json(d / task["id"] / "task.json")["success"] for d in dirs]
            paired[str(tuple(outcomes))] += 1
    recommendation = (
        f"Recomenda-se um piloto maior antes de fixar o modo: {count} tarefas e uma seed "
        "não isolam o efeito de thinking nem estabelecem uma vantagem estável. "
        "Compare o custo por resolvida, truncamento e sucessos pareados antes da decisão humana."
        if complete else "Execução incompleta: não há base para escolher um modo. Complete as tarefas ausentes e gere novamente o relatório.")
    if complete:
        # Only call a configuration operationally dominant when it wins both
        # success and cost, without increasing truncation. Still no auto-selection.
        for index, name in enumerate(("thinking", "non-thinking")):
            best, other = summaries[index], summaries[1 - index]
            if (best["solved"] > other["solved"] and best["seconds_per_solved"] is not None
                    and other["seconds_per_solved"] is not None
                    and best["seconds_per_solved"] <= other["seconds_per_solved"]
                    and best["truncation_rate"] <= other["truncation_rate"]):
                recommendation = (
                    f"{name} apresentou mais sucessos, menor ou igual custo por resolvida e "
                    "não aumentou o truncamento neste piloto. É um candidato operacional para o baseline; "
                    f"a amostra de {count} tarefas e uma seed limita a generalização. "
                    "Confirme a escolha humana ou amplie o piloto antes de fixar o modo.")
    if not homogeneous_gpu:
        recommendation = (
            "As sessões usaram GPUs de classes ou builds CUDA diferentes. Os sucessos estão registrados, "
            "mas a comparação de custo/tempo está confundida por hardware. Recomenda-se repetir o piloto "
            "em alocações da mesma classe antes de escolher a configuração; não fixar nós no sbatch.")
    report = {"complete": complete, "hardware_comparable": homogeneous_gpu,
              "summaries": summaries, "paired_outcomes": dict(paired),
              "recommendation": recommendation,
              "run_directories": [str(d.resolve()) for d in dirs],
              "run_metadata_hashes": [digest((d / "run.json").read_bytes()) for d in dirs]}
    output = Path(output)
    write_json(output.with_suffix(".json"), report)
    model = metadata[0]["config"].get("model", "Qwen/Qwen3-8B")
    version = metadata[0]["config"].get("prompt_version", "v1")
    lines = [f"# Piloto {model} — prompt {version} — {count} tarefas", "", "Estado: " + ("completo" if complete else "incompleto"), "",
             "Hardware comparável entre sessões: " + str(homogeneous_gpu), "",
             "Configurações operacionais completas: thinking 8192 tokens, T=0.6, p=0.95; "
             "non-thinking 4096 tokens, T=0.7, p=0.8. Ambos k=20, uma geração + dois reparos.", "",
             "| Medida | Thinking | Non-thinking |", "|---|---:|---:|"]
    rows = [("Tarefas completas", "completed_tasks"), ("Resolvidas", "solved"),
            ("Inferência média (s/tentativa)", "inference_mean_seconds"),
            ("Inferência mediana (s/tentativa)", "inference_median_seconds"),
            ("Tempo médio por tarefa (s)", "task_mean_seconds"),
            ("Tempo mediano por tarefa (s)", "task_median_seconds"),
            ("Tokens gerados/tentativa", "output_tokens_per_attempt"),
            ("Tokens de raciocínio", "reasoning_tokens"), ("Tokens finais", "final_tokens"),
            ("Respostas truncadas", "truncated"), ("Modificações inválidas", "invalid_modifications"),
            ("Segundos por tarefa resolvida (inclui carga do modelo)", "seconds_per_solved_including_model_load"),
            ("Estimativa 150 × 6 tentativas (h)", "planning_150_tasks_6_attempts_hours")]
    for title, key in rows:
        lines.append(f"| {title} | {summaries[0][key]} | {summaries[1][key]} |")
    for k in (0, 1, 2):
        lines.append(f"| Success@{k} | {summaries[0]['success_at'][str(k)]} | {summaries[1]['success_at'][str(k)]} |")
    lines.extend(["", "## Categorias e erros", ""])
    for summary in summaries:
        lines.append(f"- {summary['mode']}: erros {summary['errors']}; frequências por tentativa "
                     f"{summary['error_rates_per_attempt']}; taxa de truncamento {summary['truncation_rate']}.")
        lines.append(f"- {summary['mode']}: integridade {summary['integrity_statuses']}. Falha de parsing/checker não é alteração inválida confirmada.")
        for category, values in summary["categories"].items():
            lines.append(f"- {summary['mode']}/{category}: {values['solved']}/{values['expected_tasks']} resolvidas; "
                         f"Success@0={values['success_at']['0']}, Success@2={values['success_at']['2']}.")
    lines.extend(["", "Sucessos pareados (thinking, non-thinking): " + str(dict(paired)), "",
                  "Success@3 e @5 não foram medidos neste piloto. Success@k é sucesso acumulado, não pass@k.", "",
                  "A extrapolação supõe seis tentativas com duração igual à média observada e inclui fracassos. "
                  "Não prevê sucesso, crescimento dos prompts, filas ou carregamento do modelo. "
                  "Tempos de tentativas interrompidas antes de persistir resultados não entram nessa estimativa. "
                  "GPU: amostras de uso/memória ficam em gpu.csv do job quando nvidia-smi está disponível.", "",
                  "## Recomendação", "", recommendation,
                  "", "O baseline completo depende de uma escolha explícita registrada em decision.json."])
    write_text(output.with_suffix(".md"), "\n".join(lines) + "\n")
    return report


def single_report(run_dir):
    """Report one operational configuration, without a paired comparison."""
    root = Path(run_dir)
    metadata = read_json(root / "run.json")
    summary = aggregate(root)
    config = metadata["config"]
    lines = [f"# {config.get('model')} — {summary['expected_tasks']} tarefas", "",
             f"Prompt: {config.get('prompt_version', 'v1')}; modo: {config['mode']}.", "",
             f"Concluídas: {summary['completed_tasks']}/{summary['expected_tasks']}.",
             f"Resolvidas: {summary['solved']}; tentativas: {summary['attempts']}.",
             f"Relatório completo: {summary['complete']}.", "",
             "| Orçamento de reparos | Taxa de sucesso |", "|---|---:|"]
    for budget in (0, 1, 2):
        value = summary["success_at"][str(budget)]
        lines.append(f"| {budget} | {value:.2%} |")
    lines += ["", f"Saídas truncadas: {summary['truncated']}.",
              f"Tokens de saída: {summary['output_tokens']}.",
              "", "Métricas por categoria, erros e tarefas pendentes: summary.json.",
              "Taxas usam todas as tarefas selecionadas como denominador; pendentes não são sucessos."]
    audit = summary["diagnostics"]
    lines += ["", f"Diagnósticos auditados: {audit['audited_attempts']} tentativas.",
              f"Problemas com erro de sintaxe: {audit['problems_with_syntax_errors']}.",
              f"Problemas com incompatibilidade de tipos E0308: {audit['problems_with_type_mismatches']}.",
              "Contagens consideram qualquer tentativa e podem se sobrepor."]
    if metadata["stage"] == "revalidation":
        lines += ["", "REVALIDAÇÃO DE CANDIDATOS SALVOS: nenhuma inferência nova.",
                  "Tokens e tempos de inferência são históricos da execução original.",
                  "Todas as tentativas salvas são auditadas, inclusive após um sucesso reclassificado;",
                  "este resultado não simula uma nova execução com parada antecipada.",
                  "A revalidação não mede o efeito de novos prompts ou de um novo feedback de reparo."]
    write_text(root / "report.md", "\n".join(lines) + "\n")
    return summary
