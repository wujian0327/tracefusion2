"""Run sealed requests on an original-only RuoYi stack; no predictions/truth tags."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import quote


def run(home,attempt):
    env=home/attempt;out=env/'sealed-original-requests';out.mkdir(exist_ok=False)
    seal=home/'external-query-seal-v2-before-core.json';protocol=json.loads(seal.read_text())
    login=json.loads((env/'normal-login-response.json').read_text());assert login['code']==200
    token=login['data']['access_token']
    base=['docker','compose','-p','tf2-closure-ruoyi-original','-f',str(env/'compose.yml')]
    receipt={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
       'seal_sha256':hashlib.sha256(seal.read_bytes()).hexdigest(),'Agent':False,
       'original_authentication':'Original normal /login token; no invented identity or signing material.',
       'cases':[]}
    for task in protocol['tasks']['ruoyi']:
        for index,request in enumerate(task['inputs']):
            method,route=task['http'].split(' ',1)
            if method=='GET'and '{'in route:
                begin=route.index('{');end=route.index('}',begin)
                route=route[:begin]+quote(str(request),safe='')+route[end+1:]
            message=hashlib.sha256((task['id']+'|'+str(index)).encode()).hexdigest()
            args=[*base,'exec','-T','client','curl','-sS','--max-time','25','-w','\n%{http_code}',
                  '-H','Authorization: Bearer '+token,'-H','traceparent: 00-'+message[:32]+'-'+message[32:48]+'-01']
            if method!='GET':args+=['-X',method,'-H','Content-Type: application/json','--data-binary',json.dumps(request)]
            args+=['http://system:9201'+route]
            result=subprocess.run(args,text=True,capture_output=True)
            raw,status=result.stdout.rsplit('\n',1)if'\n'in result.stdout else(result.stdout,'0')
            try:body=json.loads(raw)
            except ValueError:body=raw
            record={'query':task['id'],'case':index,'input':request,'method':method,'route':route,
                    'http_status':int(status or 0),'response':body,'curl_returncode':result.returncode,
                    'stderr':result.stderr,'message':message[:32]+'/'+message[32:48]}
            receipt['cases'].append(record)
            (out/(task['id']+'-'+str(index)+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
            (out/'progress.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    sql='SELECT dept_id,parent_id,dept_name,status,del_flag FROM sys_dept ORDER BY dept_id; SELECT post_id,post_name,status FROM sys_post ORDER BY post_id; SELECT config_id,config_key,config_value FROM sys_config ORDER BY config_id; SELECT dict_code,dict_type,dict_label,dict_value FROM sys_dict_data ORDER BY dict_code;'
    result=subprocess.run([*base,'exec','-T','mysql','mysql','-uroot','-ptf2-disposable-fixture','--batch','--default-character-set=utf8mb4','ry-cloud','-e',sql],text=True,capture_output=True,check=True)
    (out/'independent-database-content.tsv').write_text(result.stdout)
    receipt['database_content_only']='Independent content validation, not a replacement for each JVM mapper call/field/version coordinates.'
    (out/'results.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print({task['id']:[(c['http_status'],c['response'].get('code')if isinstance(c['response'],dict)else None) for c in receipt['cases']if c['query']==task['id']] for task in protocol['tasks']['ruoyi']})


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--home',type=Path,required=True);parser.add_argument('--attempt',required=True)
    a=parser.parse_args();run(a.home.resolve(),a.attempt)
