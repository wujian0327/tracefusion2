"""Boolean result is a computation over predicates, including unknown inputs."""
from types import SimpleNamespace
from execution_dependency_state import Value
from infer_remove_if import complete


def check():
    checks=[]
    for uncertain in (False,True):
        left=Value({'object':'left'});right=Value({'object':'right'})
        a=('field',10,0);b=('field',20,0);s=('field',30,0)
        before={'elements':[left.observed,right.observed],'epoch':0,'mod_count':0}
        proof={'before':before};c=SimpleNamespace(elements=[left,right],epoch=0)
        tests=[Value({'value':False},frozenset({a}),frozenset({s})),
               Value({'value':True},frozenset({b}),unknown=uncertain)]
        replay={'source':c,'proof':proof,'decisions':tests,'before':[left,right],
                'null':False,'structural':False,'error':None}
        result={'value':True}
        finish={'kind':'collection-call-exit','result':result,
                'remove_if':{**proof,'after':{'elements':[left.observed],'epoch':1,'mod_count':1},'result':result}}
        got=complete(replay,{},finish,lambda v:v.observed,lambda v:v.observed.get('object'),{})
        assert got.origins==frozenset({a,b}) and got.selectors==frozenset({s})
        assert got.unknown==uncertain and c.elements[0].unknown==uncertain
        checks.append({'unknown_predicate':uncertain,'boolean_dependencies_preserved':True})
    return checks


if __name__=='__main__': print(check())
