"""Independent literal business review. NEVER imports TF inference or MT tag code.

Rules describe ORIGINAL source/DB facts, not a propagation implementation used
inside the tool. Evaluators bind the specified source occurrences to raw facts.
Retrospective rules: first captures predate this review, explicitly disclosed.
"""
from decimal import Decimal
from datetime import datetime
from pathlib import Path
import json

def flatten(value,path=''):
    if isinstance(value,dict):return[(p,v)for k,x in value.items()for p,v in flatten(x,path+'/'+str(k).replace('~','~0').replace('/','~1'))]
    if isinstance(value,list):return[(p,v)for k,x in enumerate(value)for p,v in flatten(x,path+'/'+str(k))]
    return[(path or'/',value)]

def return_rule(api,path):
    if api=='piggymetrics-2':
        if path=='/name':return{'source':{'kind':'argument','argument':0,'path':'/username'},'basis':'AccountServiceImpl.create: account.setName(user.getUsername())'}
        if path in('/lastSeen','/incomes','/expenses','/note','/saving/amount','/saving/currency','/saving/interest','/saving/deposit','/saving/capitalization'):
            return{'source':None,'basis':'Fresh Account/Saving; fixed initialized/default fields and fresh Date producer. Clock generation is recorded separately, outside the declared input/DB/RPC-read boundary; not an input dependency.'}
    if api=='piggymetrics-5':
        if path=='/accountName':return{'source':{'kind':'argument','argument':0,'path':'<Principal.getName actual backing field>'},'requires':'Principal runtime physical-field projection','basis':'RecipientController passes principal.getName; RecipientService.save overwrites accountName'}
        if path=='/email' or path.endswith(('/active','/frequency')):return{'source':{'kind':'argument','argument':1,'path':path},'basis':'RecipientService.save preserves email and active/frequency of the same supplied Recipient; only lastNotified null values are replaced'}
        if path.endswith('/lastNotified'):return{'source':None,'basis':'All frozen input settings lastNotified are null; original method assigns new Date when null','requires':'Actual setting key/member and executed null branch facts'}
    if api=='piggymetrics-4':return{'source':{'kind':'argument','argument':0,'path':path},'requires':'Actual OAuth2Authentication class, physical-field and computed-getter projection; no matching by equal wire names','basis':'UserController.getUser literally returns its Principal parameter'}
    return{'source':'unresolved','requires':'Review outside the five original methods frozen in this protocol'}

def database(path):
    result={}
    for line in path.read_text().splitlines():
        if line.startswith('{'):
            row=json.loads(line);result[(row['database'],row['collection'])]=row['documents']
    return result

def account_return_checks(case,home):
    """Check original semantics against this JVM's request, response AND raw DB."""
    if case['http_status']!=200:return[]
    response=case['response'];assert set(response)=={'name','lastSeen','incomes','expenses','saving','note'}
    assert response['name']==case['body']['username']
    assert response['note']is None and response['incomes']is None and response['expenses']is None
    assert response['saving']=={'amount':0,'currency':'USD','interest':0,'deposit':False,'capitalization':False}
    docs=database(home/(case['api']+'-'+case['case']+'-database-after.jsonl'))[('piggy-account','accounts')]
    actual=[d for d in docs if d['_id']==case['body']['username']];assert len(actual)==1;doc=actual[0]
    assert all(Decimal(str(doc['saving'][k]))==Decimal(str(response['saving'][k]))for k in('amount','interest'))
    assert all(doc['saving'][k]==response['saving'][k]for k in('currency','deposit','capitalization'))
    left=datetime.fromisoformat(doc['lastSeen'].replace('Z','+00:00'));right=datetime.strptime(response['lastSeen'],'%Y-%m-%dT%H:%M:%S.%f%z');assert left==right
    assert all(doc.get(k)is None for k in('incomes','expenses','note'))
    return['Root username equals this request name; original code selects it, equality is ONLY a check','Fixed/default fields agree with original source AND actual saved DB document','Clock response agrees with DB timestamp; no boundary input dependency is invented']

def inventory_entries():
    return [
      {'api':'piggymetrics-1','method_return':'void','sinks':[{'id':'account-save','kind':'persistence','method':'com/piggymetrics/account/service/AccountServiceImpl.saveChanges(Ljava/lang/String;Lcom/piggymetrics/account/domain/Account;)V','site':39,'callee':'com/piggymetrics/account/repository/AccountRepository.save(Ljava/lang/Object;)Ljava/lang/Object;','argument':0,'targets':'All Account scalar/null leaves; empty incomes/expenses are structural checkpoints','rules':{'/name':'Actual findByName return.name (NOT input Account.name)','/note':'Root argument1.note','/saving/*':'Corresponding root argument1.saving field','/lastSeen':'Fresh Date producer, no declared boundary input','/incomes/*':'Corresponding input member; empty inputs have no member target','/expenses/*':'Corresponding input member; empty inputs have no member target'}}, {'id':'statistics-outbound','kind':'supplementary-RPC-attempt','method':'com/piggymetrics/account/service/AccountServiceImpl.saveChanges(Ljava/lang/String;Lcom/piggymetrics/account/domain/Account;)V','site':50,'callee':'com/piggymetrics/account/client/StatisticsServiceClient.updateStatistics(Ljava/lang/String;Lcom/piggymetrics/account/domain/Account;)V','targets':'Actual outgoing account argument if request serialized; fallback invocation is not actual remote execution','rule':'Name comes from Principal.getName; account content as saved','scope':'Supplementary communication audit, do not merge with persistence counts'}]},
      {'api':'piggymetrics-2','method_return':'Account scalar/null response fields; include null incomes/expenses, not only element paths','sinks':[{'id':'account-create-save','kind':'persistence','method':'com/piggymetrics/account/service/AccountServiceImpl.create(Lcom/piggymetrics/account/domain/User;)Lcom/piggymetrics/account/domain/Account;','site':67,'callee':'com/piggymetrics/account/repository/AccountRepository.save(Ljava/lang/Object;)Ljava/lang/Object;','targets':'All saved Account fields','rules':'Same original Account construction rule as method return; target occurrence remains save argument, NOT response occurrence'}, {'id':'auth-create-outbound','kind':'supplementary-RPC-and-remote-persistence','method':'com/piggymetrics/account/service/AccountServiceImpl.create(Lcom/piggymetrics/account/domain/User;)Lcom/piggymetrics/account/domain/Account;','site':20,'callee':'com/piggymetrics/account/client/AuthServiceClient.createUser(Lcom/piggymetrics/account/domain/User;)V','targets':'Actual User request and remote UserRepository.save fields','rules':'username copies root argument0.username; remote password is BCrypt of root argument0.password plus generated salt; requires actual cross-service message and remote object/write coordinates'}]},
      {'api':'piggymetrics-3','method_return':'void; native collector null sentinel is NOT a source answer','sinks':[{'id':'user-save','kind':'persistence','method':'com/piggymetrics/auth/service/UserServiceImpl.create(Lcom/piggymetrics/auth/domain/User;)V','site':20,'callee':'com/piggymetrics/auth/repository/UserRepository.save(Ljava/lang/Object;)Ljava/lang/Object;','argument':0,'targets':'username and encoded password','rules':{'/username':'Root argument0.username','/password':'Root argument0.password through BCrypt plus generated salt; not a known empty source'}}]},
      {'api':'piggymetrics-4','method_return':'All actual Principal/OAuth2Authentication serialized scalar/null leaves; empty sets/maps separate structural checkpoints','sinks':[], 'rules':'Identity return of root argument0, physical projection required; cannot equate every computed JSON path to same-name physical field'},
      {'api':'piggymetrics-5','method_return':'Actual Recipient scalar/null leaves including both BACKUP/REMIND settings','sinks':[{'id':'recipient-save','kind':'persistence','method':'com/piggymetrics/notification/service/RecipientServiceImpl.save(Ljava/lang/String;Lcom/piggymetrics/notification/domain/Recipient;)Lcom/piggymetrics/notification/domain/Recipient;','site':11,'callee':'com/piggymetrics/notification/repository/RecipientRepository.save(Ljava/lang/Object;)Ljava/lang/Object;','argument':0,'targets':'All Recipient scalar/null leaves; Map keys are enum NotificationType, not String in memory','rules':'accountName from Principal.getName; email/active/frequency from actual root argument1; null lastNotified replaced by fresh Date; return is same mutated Recipient'}]}
    ]
