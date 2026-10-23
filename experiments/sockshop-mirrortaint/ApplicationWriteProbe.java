import java.util.*;
import java.io.*;

/** Scope, exact receiver and version maintenance of application value omission. */
public final class ApplicationWriteProbe {
    static class Item { String other; }
    static class Child extends Item {}
    static int checks;
    static Map map(Object... pairs){Map m=new LinkedHashMap();for(int i=0;i<pairs.length;i+=2)m.put(pairs[i],pairs[i+1]);return m;}
    static void check(boolean pass){checks++;if(!pass)throw new AssertionError("application write guard "+checks);}
    public static void main(String[] args)throws Exception{
        String method="Fixture.helper()V",root="Fixture.root()V",field="ApplicationWriteProbe$Item.other",site=method+"@3";
        Map proof=map("field",field,"field_owner","ApplicationWriteProbe$Item","method",method,"kind","frame");
        Map policy=map("version",1,"enabled",true,"required_value_fields",new ArrayList(),"sites",map(site,proof));
        Map closure=map("version",1,"enabled",true,"application_write_values",policy);
        PlannedServiceAgent.plan=map("profile","execution-dependency","entry",root,"execution_observation_closure",closure);
        PlannedServiceAgent.full=false;Item item=new Item();
        check(!ExecutionKernelHooks.versionOnly(item,site,field));
        PlannedServiceAgent.Recorder.Frame f=new PlannedServiceAgent.Recorder.Frame();f.id="root";f.method=root;PlannedServiceAgent.Recorder.STACK.get().push(f);
        check(!ExecutionKernelHooks.versionOnly(item,site,field));
        PlannedServiceAgent.Recorder.Frame child=new PlannedServiceAgent.Recorder.Frame();child.id="child";child.method=method;PlannedServiceAgent.Recorder.STACK.get().push(child);
        check(ExecutionKernelHooks.versionOnly(item,site,field));
        check(!ExecutionKernelHooks.versionOnly(new Child(),site,field));
        check(!ExecutionKernelHooks.versionOnly(null,site,field));
        check(!ExecutionKernelHooks.versionOnly(item,"unknown",field));
        PlannedServiceAgent.full=true;check(!ExecutionKernelHooks.versionOnly(item,site,field));PlannedServiceAgent.full=false;
        closure.put("enabled",false);check(!ExecutionKernelHooks.versionOnly(item,site,field));closure.put("enabled",true);
        policy.put("enabled",false);check(!ExecutionKernelHooks.versionOnly(item,site,field));policy.put("enabled",true);
        ((List)policy.get("required_value_fields")).add(field);
        try{ExecutionKernelHooks.versionOnly(item,site,field);throw new AssertionError("required value omitted");}catch(IllegalStateException expected){checks++;}
        ((List)policy.get("required_value_fields")).clear();
        proof.put("kind","setter");check(!ExecutionKernelHooks.versionOnly(item,site,field));
        CollectionServiceHooks.CALLS.get().push(map("callee",method));check(ExecutionKernelHooks.versionOnly(item,site,field));
        CollectionServiceHooks.CALLS.get().push(map("callee","Unknown.call()V"));check(!ExecutionKernelHooks.versionOnly(item,site,field));CollectionServiceHooks.CALLS.get().pop();CollectionServiceHooks.CALLS.get().pop();proof.put("kind","frame");
        StringWriter sink=new StringWriter();PlannedServiceAgent.Recorder.output=new BufferedWriter(sink);
        PlannedServiceAgent.Recorder.fieldVersionRecord(item,field,site);PlannedServiceAgent.Recorder.fieldVersionRecord(item,field,site);
        String key=PlannedServiceAgent.Recorder.id(item)+":"+field;check(PlannedServiceAgent.Recorder.VERSIONS.get(key)==2);
        PlannedServiceAgent.Recorder.output.flush();check(sink.toString().contains("write-version")&&!sink.toString().contains("observed"));
        PlannedServiceAgent.Recorder.ACTIVE.put(PlannedServiceAgent.Recorder.id(item),new HashSet(Arrays.asList("read-only-root")));
        try{PlannedServiceAgent.Recorder.fieldVersionRecord(item,field,site);throw new AssertionError("read-only source modified");}catch(IllegalStateException expected){checks++;}
        PlannedServiceAgent.Recorder.ACTIVE.clear();PlannedServiceAgent.Recorder.STACK.get().clear();check(!ExecutionKernelHooks.versionOnly(item,site,field));
        System.out.println("APPLICATION_WRITE_GUARDS_PASSED="+checks);
    }
}
