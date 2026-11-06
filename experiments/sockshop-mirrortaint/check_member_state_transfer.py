"""Independent dependency expectations, including the prior scalar/null failure."""
from collections import defaultdict
from execution_dependency_state import Value,State,Frame
from member_state_transfer import read_members,copy_member,install_members,register_references

def run():
 seen=[]
 def source(field,before):
  seen.append((field['owner'],field['field'],field['version'],before))
  return Value(field['observed'],frozenset({('field',41,0)}))
 null={'object':None,'value':None};owned=read_members('array-A',7,[null],99,source)[0]
 assert owned.origins==frozenset({('field',41,0)})and not owned.unknown
 constant=copy_member(Value(null));assert not constant.origins and not constant.unknown
 assert seen==[('array-A','@list:0',7,99)]
 for reason in('missing','ambiguous'):
  value=read_members(reason,0,[null],9,lambda f,b:Value(f['observed'],unknown=True))[0];assert value.unknown and not value.origins
 a=Value({'value':'SAME'},frozenset({('field',10,0)}));b=Value({'value':'SAME'},frozenset({('field',20,0)}))
 assert copy_member(a).origins!=copy_member(b).origins
 overwrite=copy_member(Value({'value':'SAME'}));assert not overwrite.origins and a.origins==frozenset({('field',10,0)})
 old=Value({'object':'member'},a.origins,frozenset({('choice',3)}),True,12);new=copy_member(old,selectors=frozenset({('choice',4)}))
 assert new.origins==a.origins and new.selectors==frozenset({('choice',3),('choice',4)})and new.unknown and new.allocation==12
 state=State(Frame('f'));container=install_members(state,'copy',[new],3);assert container.epoch==3 and not container.local and container.elements[0]==new
 refs=defaultdict(set);register_references(refs,'copy',[new],lambda v:v.observed);assert refs['copy']=={'member'}
 print('Member state: source/constant null, absent/ambiguous facts, occurrences, overwrite, choice/unknown, phase and references passed')
if __name__=='__main__':run()
