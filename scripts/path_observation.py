"""Query-relative branch deletion shared by bounded instruction analyses."""
from hybrid_model import require


def select_branches(paths, branches, outcome, observe_return=False):
    def separates(selected):
        groups = {}
        for path in paths:
            signature = tuple((e['address'], e['taken']) for e in path['branches'] if e['address'] in selected)
            if observe_return:
                signature = (path['return_address'], signature)
            groups.setdefault(signature, set()).add(outcome(path))
        return all(len(values) == 1 for values in groups.values())
    selected = set(branches)
    require(separates(selected), 'Control observations cannot distinguish output dependencies')
    for branch in sorted(branches, reverse=True):
        if separates(selected - {branch}):
            selected.remove(branch)
    return sorted(selected)
