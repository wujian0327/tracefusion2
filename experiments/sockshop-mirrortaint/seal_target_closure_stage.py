"""Seal external tasks without importing a TF planner or a label decoder.

Selection uses original source/API structure. This file is experiment wiring,
not a propagation summary. Existing seals are never overwritten.
"""
import argparse
import datetime
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(home):
    destination = home / 'external-query-seal-before-core.json'
    if destination.exists():
        raise FileExistsError(destination)
    applications = home / 'external-candidates'
    ruoyi = applications / 'ruoyi-cloud'
    tea = applications / 'teastore'
    for path, expected in [(ruoyi, '86527f4da8448a11630ea8dcd03a585cdd6565c6'),
                           (tea, '34b37f7e7be433ce72d5f9455e66922a13116749')]:
        assert subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip() == expected
    pool = []
    files = sorted((ruoyi / 'ruoyi-modules/ruoyi-system/src/main/java/com/ruoyi/system/controller').glob('*.java'))
    files += sorted((tea / 'services/tools.descartes.teastore.persistence/src/main/java/tools/descartes/teastore/persistence/rest').glob('*.java'))
    for path in files:
        # Inventory all public endpoint-source methods; annotations and source
        # remain available for inherited/generic route resolution before tools.
        text = path.read_text()
        pool.append({'file': str(path.relative_to(home)), 'sha256': sha(path),
                     'public_methods': re.findall(r'public\s+(?:<[^>]+>\s+)?[\w<>, ?\[\]]+\s+(\w+)\s*\(', text)})
    def task(identifier, entry, route, target, sources, inputs, rule, structure):
        return dict(id=identifier, entry=entry, http=route, target=target,
                    source_calls=sources, inputs=inputs, independent_rule=rule,
                    structure=structure, initial_status='sealed_not_trial_planned')
    rm = 'com/ruoyi/system/mapper/'
    rd = 'com/ruoyi/system/api/domain/'
    rc = 'com/ruoyi/system/controller/'
    ruoyi_tasks = [
        task('ruoyi-1', rc+'SysDeptController.getInfo(Ljava/lang/Long;)Lcom/ruoyi/common/core/web/domain/AjaxResult;',
             'GET /dept/{deptId}', rd+'SysDept.deptName@/data/deptName',
             [rm+'SysDeptMapper.selectDeptById(Ljava/lang/Long;)L'+rd+'SysDept;'],
             [100,101,102,103,100,999999],
             'Normal data.deptName copies the concrete selectDeptById return field. Data-scope reads select control only. Null data is a separate null-field target, not an element.', 'forwarding + data-scope check'),
        task('ruoyi-2', rc+'SysDeptController.excludeChild(Ljava/lang/Long;)Lcom/ruoyi/common/core/web/domain/AjaxResult;',
             'GET /dept/list/exclude/{deptId}', rd+'SysDept.deptName@/data/*/deptName',
             [rm+'SysDeptMapper.selectDeptList(L'+rd+'SysDept;)Ljava/util/List;'],
             [101,102,103,104,999999,101],
             'Each surviving element name copies its own mapper row field; removeIf changes membership, not the name source. Repeated names must keep different row coordinates.', 'collection selection + lambda'),
        task('ruoyi-3', rc+'SysDictDataController.dictType(Ljava/lang/String;)Lcom/ruoyi/common/core/web/domain/AjaxResult;',
             'GET /dict/data/type/{dictType}', rd+'SysDictData.dictLabel@/data/*/dictLabel',
             [rm+'SysDictDataMapper.selectDictDataByType(Ljava/lang/String;)Ljava/util/List;',
              'org/springframework/data/redis/core/ValueOperations.get(Ljava/lang/Object;)Ljava/lang/Object;'],
             ['sys_user_sex','sys_normal_disable','sys_user_sex','sys_job_status','tf_missing','sys_normal_disable'],
             'Actual mapper or Redis read occurrence supplies each label. A cache hit is not attributed to an earlier absent mapper occurrence. Empty list has no member targets.', 'collection + cache hit/miss'),
        task('ruoyi-4', rc+'SysConfigController.getInfo(Ljava/lang/Long;)Lcom/ruoyi/common/core/web/domain/AjaxResult;',
             'GET /config/{configId}', rd+'SysConfig.configValue@/data/configValue',
             [rm+'SysConfigMapper.selectConfigById(Ljava/lang/Long;)L'+rd+'SysConfig;'],
             [1,2,3,4,1,999999],
             'Value copies the concrete mapper return field. Missing record leaves null data; no value-based matching.', 'simple forwarding'),
        task('ruoyi-5', rc+'SysPostController.optionselect()Lcom/ruoyi/common/core/web/domain/AjaxResult;',
             'GET /post/optionselect', 'com/ruoyi/system/domain/SysPost.postName@/data/*/postName',
             [rm+'SysPostMapper.selectPostAll()Ljava/util/List;'],
             [{}, {}, {}, {}, {}, {}],
             'Each postName is its actual selectPostAll row field; deliberately equal names on distinct rows cannot merge. Six requests have fresh method/source occurrences.', 'nonempty collection'),
        task('ruoyi-6', rc+'SysDeptController.add(L'+rd+'SysDept;)Lcom/ruoyi/common/core/web/domain/AjaxResult;',
             'POST /dept', 'com/ruoyi/common/core/web/domain/AjaxResult.code@/code',
             [rm+'SysDeptMapper.selectDeptById(Ljava/lang/Long;)L'+rd+'SysDept;',
              rm+'SysDeptMapper.checkDeptNameUnique(Ljava/lang/String;Ljava/lang/Long;)L'+rd+'SysDept;'],
             [dict(parentId=100,deptName='tf_dept_'+str(i),orderNum=i,status='0') for i in range(6)],
             'On successful insert toAjax returns constant success code with empty data origins; row count and uniqueness affect selection. Save/logging effects remain obligations, not read-only summaries.', 'writes + multiple reads + logging')]
    prefix = 'tools/descartes/teastore/'
    rest = prefix+'persistence/rest/'
    entity = prefix+'entities/'
    query = 'jakarta/persistence/TypedQuery.getResultList()Ljava/util/List;'
    find = 'jakarta/persistence/EntityManager.find(Ljava/lang/Class;Ljava/lang/Object;)Ljava/lang/Object;'
    ranges = [dict(category=1,start=0,max=2),dict(category=1,start=1,max=2),dict(category=2,start=0,max=2),dict(category=1,start=0,max=4),dict(category=999999,start=0,max=2),dict(category=1,start=0,max=2)]
    tea_tasks = [
        task('tea-1',rest+'ProductEndpoint.listAllForCategory(Ljava/lang/Long;Ljava/lang/Integer;Ljava/lang/Integer;)Ljava/util/List;',
             'GET /rest/products/category/{category}?start={start}&max={max}',entity+'Product.name@/*/name',[find,query],ranges,
             'The copy constructor preserves each selected PersistenceProduct.name field from the concrete TypedQuery row. Category find supplies selection, not product name.', 'copy + collection + multiple reads'),
        task('tea-2',rest+'ProductEndpoint.listAllForCategory(Ljava/lang/Long;Ljava/lang/Integer;Ljava/lang/Integer;)Ljava/util/List;',
             'GET /rest/products/category/{category}?start={start}&max={max}',entity+'Product.listPriceInCents@/*/listPriceInCents',[find,query],ranges,
             'Price copies its own concrete selected row. Equal prices remain separate sources.', 'collection different target field'),
        task('tea-3',rest+'UserEndpoint.findById(Ljava/lang/String;)Ljakarta/ws/rs/core/Response;',
             'GET /rest/users/name/{name}',entity+'User.firstName@/firstName',[query],
             ['tf_user_1','tf_user_2','tf_user_3','tf_user_1','tf_missing','tf_user_2'],
             'Repository maps its concrete matching PersistenceUser row into User; final copy preserves that firstName. Missing user 404 is not a successful field.', 'single-row forwarding + copies'),
        task('tea-4',rest+'OrderEndpoint.listAllForUser(Ljava/lang/Long;Ljava/lang/Integer;Ljava/lang/Integer;)Ljava/util/List;',
             'GET /rest/orders/user/{user}?start={start}&max={max}',entity+'Order.totalPriceInCents@/*/totalPriceInCents',[find,query],
             [dict(user=u,start=0,max=2) for u in (1,2,3,1,999999,2)],
             'Each totalPriceInCents copies the selected PersistenceOrder field, not a newly recomputed product sum; user find determines selection.', 'multi-read collection'),
        task('tea-5',prefix+'registryclient/util/AbstractCRUDEndpoint.listAll(Ljava/lang/Integer;Ljava/lang/Integer;)Ljava/util/List;',
             'GET /rest/categories?start={start}&max={max}',entity+'Category.name@/*/name',[query],
             [dict(start=s,max=m) for s,m in [(0,2),(1,2),(0,4),(2,2),(999999,2),(0,2)]],
             'Inherited route dispatches to CategoryEndpoint; each copied category name uses its concrete query row. Runtime generic dispatch must be bound, not guessed.', 'inheritance + collection'),
        task('tea-6',prefix+'registryclient/util/AbstractCRUDEndpoint.create(Ljava/lang/Object;)Ljakarta/ws/rs/core/Response;',
             'POST /rest/products', 'generated product ID response scalar', [find],
             [dict(categoryId=1,name='tf_product_'+str(i),description='repeat',listPriceInCents=1200) for i in range(6)],
             'Generated identifier has no declared root/read data source; generation requires actual generated-ID write fact. Preserve oracle-unavailable if not observed; persisted input fields are separate sink obligations.', 'write + generated result')]
    extra = [p for base in (ruoyi, tea) for p in base.rglob('*')
             if p.is_file() and (p.suffix in ('.java','.xml','.sql') or p.name=='Dockerfile') and '.git' not in p.parts]
    result = dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  reference='7e4ad0b900a64871259a5fac008968128cc5ec28',
                  selection='Fixed official revisions, six families/app in order below. Inventory all endpoint-source files; select read forwarding, collection/selection and effects across >=3 endpoint classes. Other inventory methods not selected because this batch is bounded; never replace failures by successful methods.',
                  disclosure='Source/dependency/environment review permitted and performed; no third-party blind claim. No TF plan or run on these tasks before new algorithm freeze.',
                  pool=pool, tasks={'ruoyi':ruoyi_tasks,'teastore':tea_tasks},
                  fixture='Isolated original SQL/schema + six input cases. Seed nonempty rows, at least two distinct rows with equal selected values. Save every fixture diff and hash before original runs. Public application authentication only; no signing-material reads or invented admin JWT.',
                  oracle='Logical copy/constant/selection rules above fixed before tools. Each JVM needs actual source-call start/completion and field/owner/version/target projection. DB values verify content but cannot supply missing physical coordinates. Labels/TF inference never generate truth.',
                  compatibility='RuoYi host OpenJDK8u504; TeaStore JDK11/Tomcat10.0.27 official Dockerfile. Independent control probes allowed; no query compatibility trial planning. Missing model/runtime/transport => report unsupported, no registration or framework adaptation.',
                  first_execution='After algorithm freeze only. Original, TF full/selective, applicable fixed MT. Keep complete pool statuses and unchanged logical source boundaries. Handler leaves and save/message sinks separately inventoried, not automatically counted as field success.',
                  archive_source_hashes={str(p.relative_to(home)):sha(p) for p in sorted(extra)})
    destination.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    summary={k:result[k] for k in ('created_utc','reference','selection','disclosure','tasks','fixture','oracle','compatibility','first_execution')}
    summary['full_seal_sha256']=sha(destination)
    summary['pool_source_files']=len(pool)
    small=ROOT/'experiments/sockshop-mirrortaint/target-closure-external-seal-20261103.json'
    assert not small.exists()
    small.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'seal':str(destination),'sha256':sha(destination),'queries':{k:len(v) for k,v in result['tasks'].items()},'pool_files':len(pool)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--home',type=Path,required=True)
    main(parser.parse_args().home.resolve())
