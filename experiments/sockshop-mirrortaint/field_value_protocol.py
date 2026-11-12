"""Descriptor-aware field observations. Legacy artificial box IDs stay readable."""
import math,struct
from query_observation_planner import require

PRIMITIVES=set('ZBCSIJFD')


def validate(plan,rows):
    headers=[r for r in rows if r.get('kind')=='start']
    version=headers[0].get('field_value_version',0)if len(headers)==1 else 0
    require(type(version)is int and version in (0,1),'Unsupported field value protocol')
    descriptors={}
    def specifications(item):
        if isinstance(item,dict):
            if 'field'in item and isinstance(item.get('descriptor'),str):
                old=descriptors.setdefault(item['field'],item['descriptor']);require(old==item['descriptor'],'Conflicting declared field descriptors')
            if item.get('op')in (178,179,180,181):descriptors[item['owner']+'.'+item['name']]=item['desc']
            for value in item.values():specifications(value)
        elif isinstance(item,list):
            for value in item:specifications(value)
    specifications(plan)
    def primitive(observed,desc):
        require(observed.get('primitive')==desc and observed.get('object')is None and 'value'in observed,'Primitive type/value/identity differs')
        value=observed['value']
        if desc=='Z':require(type(value)is bool,'Primitive boolean differs')
        elif desc in 'BCSIJ':
            bounds={'B':(-128,127),'C':(0,65535),'S':(-32768,32767),'I':(-2**31,2**31-1),'J':(-2**63,2**63-1)}
            lo,hi=bounds[desc];require(type(value)is int and lo<=value<=hi,'Primitive integer range/type differs')
        else:
            bits=observed.get('bits');require(isinstance(bits,str) and 1<=len(bits)<= (8 if desc=='F'else 16) and all(c in '0123456789abcdef'for c in bits),'Primitive floating bits absent/invalid')
            number=struct.unpack('>f'if desc=='F'else'>d',int(bits,16).to_bytes(4 if desc=='F'else 8,'big'))[0]
            if not math.isfinite(number):require(value==('NaN'if math.isnan(number)else'Infinity'if number>0 else'-Infinity'),'Primitive nonfinite value/bits differ')
            else:
                require(type(value)in (int,float) and math.isfinite(value),'Primitive floating value differs')
                try:projected=struct.unpack('>f',struct.pack('>f',value))[0]if desc=='F'else float(value)
                except (OverflowError,struct.error):raise ValueError('Primitive floating value outside range')
                require(projected==number and (number!=0 or math.copysign(1,projected)==math.copysign(1,number)),'Primitive floating value/bits differ')
    def visit(item):
        if isinstance(item,dict):
            if isinstance(item.get('primitive'),str):
                require(version==1 and item['primitive']in PRIMITIVES,'Primitive observation without supported header/type');primitive(item,item['primitive'])
            if isinstance(item.get('observed'),dict)and ('field'in item or item.get('kind')=='execution-static-read'):
                observed=item['observed'];desc=item.get('descriptor',descriptors.get(item.get('field')))
                if version:
                    if item.get('kind')in ('read','write'):require(isinstance(item.get('descriptor'),str),'Field descriptor absent')
                    if desc in PRIMITIVES:primitive(observed,desc)
                    else:
                        require('primitive'not in observed,'Reference field encoded as primitive')
                        require('object'in observed and (observed.get('value')is None or observed['object']is not None),'Reference field identity absent')
                    if 'field'in item and item.get('kind')!='execution-static-read':
                        require(item.get('owner')is not None and type(item.get('version'))is int and item['version']>=0,'Field physical coordinate absent')
                    expected=descriptors.get(item.get('field'))
                    if expected:require(desc==expected,'Observed field descriptor differs from original declaration')
            for value in item.values():visit(value)
        elif isinstance(item,list):
            for value in item:visit(value)
    visit(rows)
    return version
