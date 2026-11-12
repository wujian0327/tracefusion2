"""Module-level counterexample using the real static operand analysis."""
import argparse,json
from pathlib import Path
from control_dependencies import Control,ControlFlow,field_selection
from execution_dependency_state import Frame,State,Value


def case():
    method={'owner':'Example','name':'root','access':8,'desc':'(LHolder;)V','try_catches':0,'exception_handlers':[],
            'instructions':[{'op':3},{'op':153,'target':4},{'op':25,'var':0},
                {'op':184,'owner':'Example','name':'update','desc':'(LHolder;)V'},{'op':177}]}
    update={'owner':'Example','name':'update','access':8,'desc':'(LHolder;)V','try_catches':0,'exception_handlers':[],
            'instructions':[{'op':25,'var':0},{'op':180,'owner':'Holder','name':'child','desc':'LChild;'},
                {'op':4},{'op':181,'owner':'Child','name':'value','desc':'I'},{'op':177}]}
    frame=Frame('f1');state=State(frame)
    state.field_write(('holder','Holder.child',1),Value({'object':'child'}))
    control=Control(ControlFlow(method),frame,state,lambda v:v.observed.get('object'),{'Example.update(LHolder;)V':update})
    frame.locals[0]=Value({'object':'holder'});frame.pc=1
    error=None
    try:control.branch(method['instructions'][1],[Value({'value':0},frozenset({('field',7,0)}))],{'seq':10,'taken':True})
    except ValueError as e:error={'type':type(e).__name__,'error':str(e)}
    value=field_selection(state,('child','Child.value',1),Value({'value':7},frozenset({('field',3,0)})))
    return {'selectors':[list(x)for x in sorted(value.selectors)],'unknown':value.unknown,'error':error,
            'registered_cells':[[*k]for k in state.control_fields],
            'expected_selectors':[['field',7,0]],'complete_correct':value.selectors==frozenset({('field',7,0)})and not value.unknown and error is None}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False);(a.out/'result.json').write_text(json.dumps(case(),indent=2));print(json.dumps(case()))
