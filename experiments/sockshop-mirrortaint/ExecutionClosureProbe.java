import java.util.*;

/** Scope/version guards for value elision. No provenance computation. */
public final class ExecutionClosureProbe {
    static int count;
    static Map map(Object... pairs){Map m=new LinkedHashMap();for(int i=0;i<pairs.length;i+=2)m.put(pairs[i],pairs[i+1]);return m;}
    static void check(boolean x){count++;if(!x)throw new AssertionError("closure guard "+count);}
    public static void main(String[] args){
        String site="Fixture.<init>(I)V@4",field="Fixture.other",source="Repository.read()LFixture;";
        Map needed=map("Fixture.target",Arrays.asList("query target"));
        Map c=map("version",1,"enabled",true,"source_calls",Arrays.asList(source),"needed_fields",needed,"candidate_write_sites",map(site,map("field",field)));
        PlannedServiceAgent.plan=map("profile","execution-dependency","entry","Fixture.root()LFixture;","execution_observation_closure",c);
        PlannedServiceAgent.full=false;
        check(ExecutionKernelHooks.closureCandidate(site,field));
        check(!ExecutionKernelHooks.omitWrite(site,field));
        Map call=map("callee",source);CollectionServiceHooks.CALLS.get().push(call);
        check(!ExecutionKernelHooks.omitWrite(site,field));
        PlannedServiceAgent.Recorder.Frame f=new PlannedServiceAgent.Recorder.Frame();f.id="root";f.method="Fixture.root()LFixture;";PlannedServiceAgent.Recorder.STACK.get().push(f);
        check(ExecutionKernelHooks.omitWrite(site,field));
        Object object=new Object();String key=PlannedServiceAgent.Recorder.id(object)+":"+field;
        PlannedServiceAgent.Recorder.fieldVersion(object,field,site);
        check(PlannedServiceAgent.Recorder.VERSIONS.get(key)==1);
        Map completion=map();ExecutionKernelHooks.closureCompletion(call,completion);
        check(((Map)((Map)completion.get("execution_closure")).get("elided_writes")).get(site).equals(1));
        CollectionServiceHooks.CALLS.get().push(map("callee","Unknown.effect()V"));check(!ExecutionKernelHooks.omitWrite(site,field));CollectionServiceHooks.CALLS.get().pop();
        check(!ExecutionKernelHooks.closureCandidate("other",field));
        PlannedServiceAgent.full=true;check(!ExecutionKernelHooks.omitWrite(site,field));PlannedServiceAgent.full=false;
        c.put("enabled",false);check(!ExecutionKernelHooks.omitWrite(site,field));c.put("enabled",true);
        needed.put(field,Arrays.asList("necessary effect"));
        try{ExecutionKernelHooks.omitWrite(site,field);throw new AssertionError("necessary field omitted");}catch(IllegalStateException expected){count++;}needed.remove(field);
        try{ExecutionKernelHooks.omitWrite(site,"Fixture.target");throw new AssertionError("wrong field accepted");}catch(IllegalStateException expected){count++;}
        c.put("version",2);try{ExecutionKernelHooks.omitWrite(site,field);throw new AssertionError("unknown version accepted");}catch(IllegalStateException expected){count++;}c.put("version",1);
        PlannedServiceAgent.Recorder.STACK.get().pop();check(!ExecutionKernelHooks.omitWrite(site,field));
        CollectionServiceHooks.CALLS.get().pop();Map ordinary=map();ExecutionKernelHooks.closureCompletion(map("callee","Unknown.effect()V"),ordinary);check(ordinary.isEmpty());
        System.out.println("EXECUTION_CLOSURE_GUARDS_PASSED="+count);
    }
}
