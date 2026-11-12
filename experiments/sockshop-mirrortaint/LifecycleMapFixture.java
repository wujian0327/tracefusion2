import java.lang.ref.*;
import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Adversarial identity semantics and the bounded live-state guard. */
public class LifecycleMapFixture {
    static class Hostile {public int hashCode(){throw new AssertionError("Business hashCode called");}public boolean equals(Object other){throw new AssertionError("Business equals called");}}
    static void check(boolean b,String reason){if(!b)throw new AssertionError(reason);}
    static PhantomReference<Object> dead(WeakIdentityMap<Object,String> map,Object live,ReferenceQueue<Object> q){Object dead=new Hostile();map.put(dead,"dead");check(map.get(live).equals("live")&&map.get(dead).equals("dead"),"identity lookup");boolean bound=false;try{map.put(new Hostile(),"third");}catch(IllegalStateException expected){bound=expected.getMessage().contains("state bound");}check(bound,"live-state bound ignored");int entries=0;for(Map.Entry<Object,String> entry:map.entrySet()){check(entry.getKey()==live||entry.getKey()==dead,"entry identity");entries++;}check(entries==2,"identity iterator");return new PhantomReference<>(dead,q);}
    static PhantomReference<Object> versions(ReferenceQueue<Object> q){Object owner=new Hostile();String id=PlannedServiceAgent.Recorder.id(owner);Map<String,Integer> fields=new LinkedHashMap<>();fields.put(id+":first",1);fields.put(id+":second",2);PlannedServiceAgent.Recorder.VERSIONS.putAll(fields);check(PlannedServiceAgent.Recorder.VERSIONS.get(id+":second")==2,"putAll bypassed index");return new PhantomReference<>(owner,q);}
    static PhantomReference<Object> date(ReferenceQueue<Object> q){Object value=new java.util.Date(123);TemporalDateHooks.WIRE.put(value,new Object[]{123L,"wire"});return new PhantomReference<>(value,q);}
    public static void main(String[] args)throws Exception{
        WeakIdentityMap<Object,String> map=new WeakIdentityMap<>("identity-unit",2,v->{},v->true);Object live=new Hostile();map.put(live,"live");String id=PlannedServiceAgent.Recorder.id(live);ReferenceQueue<Object> q=new ReferenceQueue<>();PhantomReference<Object> proof=dead(map,live,q),versionProof=versions(q),dateProof=date(q);int count=0;
        for(int n=0;n<80&&count<3;n++){System.gc();System.runFinalization();map.drain(64);PlannedServiceAgent.Recorder.drainRetired(128);Reference<?> ref;while((ref=q.poll())!=null){ref.clear();count++;}Thread.sleep(25);}
        for(int n=0;n<32;n++){map.drain(128);PlannedServiceAgent.Recorder.drainRetired(128);}
        check(count==3,"bounded terminal queue proof missing");check(map.size()==1&&map.get(live).equals("live"),"retirement removed live entry");check(TemporalDateHooks.WIRE.size()==0,"date wire state retained");check(PlannedServiceAgent.Recorder.VERSIONS.size()==0,"putAll versions not retired");check(id.equals(PlannedServiceAgent.Recorder.id(live)),"live ID changed");Object third=new Hostile();map.put(third,"third");check(map.size()==2,"capacity not restored");boolean protectedState=false;try{PlannedServiceAgent.Recorder.VERSIONS.clear();}catch(UnsupportedOperationException expected){protectedState=true;}check(protectedState,"global version clear permitted");Map r=new LinkedHashMap();r.put("gate",true);r.put("terminal_proofs",count);r.put("live_state_bound",2);r.put("current_entries",map.size());r.put("hostile_equals_hash_not_called",true);r.put("state",PlannedServiceAgent.Recorder.lifecycle());System.out.println(new ObjectMapper().writeValueAsString(r));check(proof.get()==null&&versionProof.get()==null&&dateProof.get()==null,"phantom referent exposed");
    }
}
