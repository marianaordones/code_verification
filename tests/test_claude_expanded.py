from collections import Counter
import unittest

from baseline.storage import read_json
from solver_needs_study.__main__ import ROOT, configuration
from solver_needs_study.data import LABELS, SELECTION, cases
from solver_needs_study.select_claude_pilot import select


class ExpandedPilotTests(unittest.TestCase):
    def test_only_effort_and_experiment_change(self):
        old = configuration(ROOT / 'configs/solver-needs-claude-local.json')
        new = configuration(ROOT / 'configs/solver-needs-claude-low.json')
        self.assertEqual({k for k in old if old[k] != new[k]}, {'effort', 'experiment'})
        self.assertEqual(new['effort'], 'low')

    def test_selection_is_fixed_stratified_and_excludes_development(self):
        fixed = read_json(ROOT / 'configs/solver-needs-claude-expanded60.json')
        self.assertEqual(len(fixed['ids']), 60)
        self.assertEqual(len(set(fixed['ids'])), 60)
        self.assertFalse(set(fixed['ids']) & set(read_json(SELECTION)['ids'][:6]))
        self.assertEqual(Counter(r['paper_label'] for r in fixed['cases']), {label: 10 for label in LABELS})
        self.assertEqual(fixed['unique_source_programs'], len({r['source_path'] for r in fixed['cases']}))

    def test_selector_is_deterministic_without_outcomes(self):
        rows = [{'id': f'{label}-{i}', 'paper_label': label, 'source_path': f'p-{i}'}
                for label in LABELS for i in range(12)]
        excluded = [f'{label}-0' for label in LABELS]
        first = select(rows, excluded)
        self.assertEqual(first, select(list(reversed(rows)), excluded))
        self.assertEqual(len(first['ids']), 60)
        self.assertFalse(set(first['ids']) & set(excluded))


if __name__ == '__main__':
    unittest.main()
