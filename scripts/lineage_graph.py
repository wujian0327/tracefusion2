"""Language-independent backward dependency traversal shared by native pilots."""
def backward_nodes(edges, sinks, kinds):
    incoming = {}
    for edge in edges:
        if edge['kind'] in kinds:
            incoming.setdefault(edge['target'], set()).add(edge['source'])
    keep = set(sinks)
    pending = list(keep)
    while pending:
        for parent in incoming.get(pending.pop(), ()):
            if parent not in keep:
                keep.add(parent)
                pending.append(parent)
    return keep
