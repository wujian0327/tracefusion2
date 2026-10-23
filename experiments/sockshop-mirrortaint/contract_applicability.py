"""Select reviewed library models from actual input JAR class bytes."""
import io,json,hashlib
from pathlib import Path
from zipfile import ZipFile

HERE=Path(__file__).parent

def library_inventory(jar):
    names=set()
    for name in ('save-effect-contracts-20261021.json','save-provided-id-contracts-20261023.json','async-task-contracts-20261021.json','request-entity-contracts-20261021.json','framework-wrapper-contracts-20261020.json'):
        names.update(json.loads((HERE/name).read_text()).get('class_sha256',{}))
    found={};providers={}
    def scan(z,label):
        entries=set(z.namelist())
        for own in names:
            path=own+'.class'
            if path not in entries:continue
            digest=hashlib.sha256(z.read(path)).hexdigest()
            if own in found:raise ValueError('Ambiguous library class on input classpath: '+own)
            found[own]=digest;providers[own]=label
    with ZipFile(jar)as source:
        scan(source,'root')
        for name in source.namelist():
            if name.startswith('BOOT-INF/lib/')and name.endswith('.jar'):
                with ZipFile(io.BytesIO(source.read(name)))as dependency:scan(dependency,name)
    return {'version':1,'classes':found,'providers':providers,'source_jar_sha256':hashlib.sha256(Path(jar).read_bytes()).hexdigest()}

def matches(contract,inventory):
    expected=contract['class_sha256'];actual=inventory.get('classes',{})
    return bool(expected)and all(actual.get(k)==v for k,v in expected.items())

def select(contract,inventory):
    if inventory is None:return None
    for profile in [contract,*contract.get('additional_profiles',[])]:
        if matches(profile,inventory):return {**profile,'observation_only':contract.get('observation_only',False)}
    return None
