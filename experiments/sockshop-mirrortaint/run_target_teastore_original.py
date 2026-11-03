"""Original-only fixed TeaStore fixtures and sealed requests, not TF truth."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def run(home):
    env=home/'teastore-original-02';out=env/'sealed-original-requests';out.mkdir(exist_ok=False)
    base=['docker','compose','-p','tf2-closure-teastore-original','-f',str(env/'compose.yml')]
    sql="""INSERT INTO PERSISTENCECATEGORY(ID,NAME,DESCRIPTION) VALUES(1,'tf_category','fixture') ON DUPLICATE KEY UPDATE NAME=VALUES(NAME);
INSERT INTO PERSISTENCEUSER(ID,USERNAME,REALNAME,EMAIL,PASSWORD) VALUES
(1,'tf_user_1','tf_repeat','one@example.invalid','fixture-no-auth'),
(2,'tf_user_2','tf_repeat','two@example.invalid','fixture-no-auth'),
(3,'tf_user_3','tf_third','three@example.invalid','fixture-no-auth');
INSERT INTO PERSISTENCEPRODUCT(ID,CATEGORY_ID,NAME,DESCRIPTION,LISTPRICEINCENTS) VALUES
(1,1,'tf_repeat','fixture',1200),(2,1,'tf_repeat','fixture',1200),(3,2,'tf_third','fixture',1200);
INSERT INTO PERSISTENCEORDER(ID,USER_ID,ORDERTIME,TOTALPRICEINCENTS,ADDRESSNAME,ADDRESS1,ADDRESS2,CREDITCARDCOMPANY,CREDITCARDNUMBER,CREDITCARDEXPIRYLOCALDATE) VALUES
(1,1,'2020-01-01 12:00:00',1200,'Fixture','Test Road','1','Fixture','not-a-card','2027-01-01'),
(2,2,'2020-01-01 12:00:00',1200,'Fixture','Test Road','2','Fixture','not-a-card','2027-01-01'),
(3,3,'2020-01-01 12:00:00',1200,'Fixture','Test Road','3','Fixture','not-a-card','2027-01-01');
INSERT INTO PERSISTENCEORDERITEM(ID,ORDER_ID,PRODUCT_ID,QUANTITY,UNITPRICEINCENTS) VALUES
(1,1,1,1,1200),(2,2,2,1,1200),(3,3,3,1,1200);
"""
    (out/'fixture-before-original.sql').write_text(sql)
    protocol={'source_and_queries':'external-query-seal-v3-before-tools.json',
       'fixture_sql_sha256':hashlib.sha256(sql.encode()).hexdigest(),
       'original_war_changed':False,
       'preparation':'SQL only in new disposable DB. Fixed source values/IDs for already sealed inputs; legitimate order totals equal their line items. Clear original repository cache before each request, using its own maintenance API, for repeatable declared JPA reads.',
       'scope':'Original business/content validation only; physical source calls and target coordinates still required separately before tool scoring.'}
    (out/'protocol-before-original.json').write_text(json.dumps(protocol,indent=2)+'\n')
    result=subprocess.run([*base,'exec','-T','db','mysql','-uroot','-prootpassword','teadb'],input=sql,text=True,capture_output=True)
    (out/'fixture-import.log').write_text(result.stdout+result.stderr);result.check_returncode()
    tasks=json.loads((home/'external-query-seal-v3-before-tools.json').read_text())['tasks']['teastore']
    records=[];prefix='http://persistence:8080/tools.descartes.teastore.persistence'
    for task in tasks:
        for index,body in enumerate(task['inputs']):
            method,path=task['http'].split(' ',1)
            if method=='GET':
                if isinstance(body,dict):
                    for key,value in body.items():path=path.replace('{'+key+'}',str(value))
                else:path=path.replace('{name}',str(body))
            cleared=subprocess.run([*base,'exec','-T','client','curl','-sS','--max-time','15','-X','DELETE',prefix+'/rest/cache/cache'],text=True,capture_output=True)
            (out/(task['id']+'-'+str(index)+'-cache-reset.txt')).write_text(cleared.stdout+cleared.stderr)
            args=[*base,'exec','-T','client','curl','-sS','--max-time','25','-w','\n%{http_code}']
            if method!='GET':args+=['-X',method,'-H','Content-Type: application/json','--data-binary',json.dumps(body)]
            response=subprocess.run([*args,prefix+path],text=True,capture_output=True)
            raw,status=response.stdout.rsplit('\n',1)if'\n'in response.stdout else(response.stdout,'0')
            try:value=json.loads(raw)
            except ValueError:value=raw
            row={'query':task['id'],'case':index,'input':body,'method':method,'path':path,
                 'http_status':int(status or 0),'response':value,'curl_returncode':response.returncode,'stderr':response.stderr}
            records.append(row);(out/(task['id']+'-'+str(index)+'.json')).write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n')
    (out/'results.json').write_text(json.dumps({'Agent':False,'cases':records,'protocol':protocol},ensure_ascii=False,indent=2)+'\n')
    print({t['id']:[r['http_status']for r in records if r['query']==t['id']]for t in tasks})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);run(p.parse_args().home.resolve())
