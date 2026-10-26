"""Bounded clause capture without AST pretty-printing during a traced check."""
from repair_study.relevance import rank


class ClauseCapture:
    def __init__(self, z3, context, report, capacity=512):
        self.z3, self.context, self.report, self.capacity = z3, context, report, capacity
        self.items = {}
        for key in ('callback_errors', 'non_inst_clauses_observed', 'clause_sample_omissions',
                    'clause_duplicates', 'oversized_clauses_omitted', 'clause_serialization_errors'):
            report.setdefault(key, 0)
        report.setdefault('rules_observed', {})

    def __call__(self, hint, dependencies, clause):
        """Hold AST references only; sexpr()/str(AST) must never run here."""
        try:
            z3, report = self.z3, self.report
            rule = str(hint.decl().name()) if z3.is_app(hint) else 'unknown'
            report['rules_observed'][rule] = report['rules_observed'].get(rule, 0) + 1
            if rule in ('inst', 'assumption', 'del', 'deleted', 'tseitin'):
                return
            report['non_inst_clauses_observed'] += 1
            if len(clause) > 128:
                report['oversized_clauses_omitted'] += 1
                return
            literals, deps = list(clause), list(dependencies)
            key = (hint.get_id(), tuple(deps), tuple(sorted({c.get_id() for c in literals})))
            if key in self.items:
                report['clause_duplicates'] += 1
                return
            # Native symbol access does not invoke the AST pretty-printer.
            pending, seen, names = list(literals), set(), []
            while pending and len(seen) < 64:
                node = pending.pop()
                if node.get_id() in seen:
                    continue
                seen.add(node.get_id())
                if z3.is_app(node):
                    names.append(str(node.decl().name()))
                elif z3.is_quantifier(node):
                    names.append(str(node.qid()))
                pending.extend(node.children())
            score = rank(' '.join(':qid ' + name for name in names), self.context)[0]
            if len(self.items) >= self.capacity:
                worst = max(self.items, key=lambda k: self.items[k]['score'])
                report['clause_sample_omissions'] += 1
                if score >= self.items[worst]['score']:
                    return
                del self.items[worst]
            self.items[key] = {'score': score, 'rule': rule, 'hint': hint, 'deps': deps, 'literals': literals}
        except Exception:
            self.report['callback_errors'] += 1

    def serialize(self, limit=256, render_context=None):
        """Called after the search trace boundary; preserve distinct justifications."""
        output, seen, rendered = [], set(), {}
        def render(node):
            key = node.get_id()
            if key not in rendered:
                target = node.translate(render_context) if render_context is not None else node
                rendered[key] = target.sexpr()
            return rendered[key]
        for item in sorted(self.items.values(), key=lambda item: item['score']):
            try:
                pending = [item['hint'], *item['literals']]
                nodes = set()
                while pending and len(nodes) <= 4096:
                    node = pending.pop()
                    if node.get_id() not in nodes:
                        nodes.add(node.get_id())
                        pending.extend(node.children())
                if pending or len(nodes) > 4096:
                    self.report['oversized_clauses_omitted'] += 1
                    continue
                hint = render(item['hint'])
                literals = [render(c) for c in item['literals']]
                if len(hint) + sum(map(len, literals)) > 32000:
                    self.report['oversized_clauses_omitted'] += 1
                    continue
                key = (item['rule'], hint, tuple(item['deps']), tuple(sorted(set(literals))))
                if key in seen:
                    self.report['clause_duplicates'] += 1
                    continue
                seen.add(key)
                output.append({'rule': item['rule'], 'hint_smt': hint, 'dependencies': item['deps'],
                    'clause_literals_smt': literals,
                    'scope': 'replay clause; dependencies/branch validity not reconstructed'})
                if len(output) == limit:
                    break
            except Exception:
                self.report['clause_serialization_errors'] += 1
        return output
