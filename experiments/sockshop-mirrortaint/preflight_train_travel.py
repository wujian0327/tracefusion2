#!/usr/bin/env python3
"""Check actual original travel-price bytecode against current generic planner."""
import argparse
from pathlib import Path
from run_planned_service import load,save,sha
from plan_service_observations import plan_service,decode
from plan_distributed_fields import copy_plan


def run(build,out):
    out.mkdir(parents=True,exist_ok=False)
    model=load(build/'basic/model.json')
    entry='fdse/microservice/service/BasicServiceImpl.queryForTravel(Lfdse/microservice/entity/Travel;Lorg/springframework/http/HttpHeaders;)Ledu/fudan/common/util/Response;'
    target='fdse.microservice.entity.TravelResult.prices'
    method=model['methods'][entry];attempts={}
    for name,fn in [('scalar_planner',plan_service),('copy_planner',copy_plan)]:
        try:fn(model,entry,target)
        except ValueError as e:attempts[name]={'supported':False,'reason':str(e)}
        else:attempts[name]={'supported':True}
    calls=sorted({v['owner']+'.'+v['name']+v['desc'] for v in method['instructions'] if v['op'] in (182,183,184,185)})
    details={'original_jar_sha256':sha(build/'basic/original.jar'),'model_sha256':sha(build/'basic/model.json'),
       'entry':entry,'target':target,'planner_attempts':attempts,'instructions':len(method['instructions']),
       'actual_calls':calls,'multi_source_formula':'(Route.distances[indexEnd] - Route.distances[indexStart]) * PriceConfig rate, followed by StringBuilder conversion and HashMap target membership; exception path yields fixed strings.',
       'required_additional_services':['ts-train-service','ts-route-service','ts-price-service'],
       'missing_generic_capabilities':['List indexOf/get with membership/element identity','unboxing and integer subtraction feeding double arithmetic','StringBuilder double-to-string summary','Map entry identity and JSON key provenance','exception-path source/constant distinction'],
       'new_business_special_inference_added':False,'current_shared_core_full_query_supported':False,
       'next_gate':'Generic rules plus independent branch/exception and map-element controls, then pin extra services and freeze new inputs. No stubs or canned expected dependencies used.'}
    save(out/'preflight.json',details)
    (out/'results.md').write_text('# Train Ticket多来源候选路径预检\n\n原版Basic.queryForTravel确有多来源数值组合与异常回退，已保存真实调用和计划生成错误。当前通用标量/字段复制规划器不能生成完整prices查询计划，保持N/A，未加入业务专用推断。\n\n缺口：List索引/元素身份、拆箱和数值组合、字符串转换、Map条目及JSON键身份、异常分支；还需补齐Train/Route/Price三个固定服务。\n\n本轮另用现有Station.id真实路径运行新输入full/selective验证；不能将其宣称为本多来源路径已完成。详见preflight.json。\n')
    print(attempts)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('build','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();run(a.build.resolve(),a.out.resolve())
