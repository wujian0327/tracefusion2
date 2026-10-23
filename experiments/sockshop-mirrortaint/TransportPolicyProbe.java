import java.util.*;

/** Context guards and exact field paths; no business/taint dependencies. */
public final class TransportPolicyProbe {
    static int count;
    static void check(boolean condition){count++;if(!condition)throw new AssertionError("policy guard "+count);}
    static Map map(Object... pairs){Map r=new LinkedHashMap();for(int i=0;i<pairs.length;i+=2)r.put(pairs[i],pairs[i+1]);return r;}
    public static void main(String[] args)throws Exception{
        PlannedServiceAgent.mode="selective";
        Map policy=map("version",1,"response_path","/data/*/text","request_proofs_outbound_only",true,"project_bound_response_fields",true);
        PlannedServiceAgent.plan=map("response_binding",map("path","/data/*/text"),"transport_evidence_policy",policy);
        ResponseBindingHooks.RETURN_MESSAGES.add("root");
        check(SpringTransportAgent.Transport.queryTransportPolicy(map("message","root","direction","response"))==policy);
        check(SpringTransportAgent.Transport.queryTransportPolicy(map("message","root","direction","request"))==null);
        check(SpringTransportAgent.Transport.queryTransportPolicy(map("message","other","direction","response"))==null);
        check(SpringTransportAgent.Transport.queryTransportPolicy(map("message","root"))==null);
        PlannedServiceAgent.mode="full";check(SpringTransportAgent.Transport.queryTransportPolicy(map("message","root","direction","response"))==null);
        PlannedServiceAgent.mode="selective";PlannedServiceAgent.plan.remove("transport_evidence_policy");check(SpringTransportAgent.Transport.queryTransportPolicy(map("message","root","direction","response"))==null);
        PlannedServiceAgent.plan.put("transport_evidence_policy",policy);policy.put("version",2);
        try{SpringTransportAgent.Transport.queryTransportPolicy(map("message","root","direction","response"));throw new AssertionError("unknown policy accepted");}catch(IllegalStateException expected){count++;}
        policy.put("version",1);policy.put("response_path","/other");
        try{SpringTransportAgent.Transport.queryTransportPolicy(map("message","root","direction","response"));throw new AssertionError("different target accepted");}catch(IllegalStateException expected){count++;}
        List<Object> fields=Arrays.asList(map("path","/data/0/text"),map("path","/data/1/text"),map("path","/data/0/other"),map("path","/data/k/text"));
        check(SpringTransportAgent.Transport.queryResponseFields(fields,"/data/*/text").size()==2);
        check(SpringTransportAgent.Transport.queryResponseFields(fields,"/data/1/text").equals(Arrays.asList(fields.get(1))));
        check(SpringTransportAgent.Transport.queryResponseFields(fields,"/missing").isEmpty());
        check(SpringTransportAgent.Transport.queryResponseFields(Arrays.asList(map("path","/a~1b/k~0v")),"/a~1b/k~0v").size()==1);
        check(SpringTransportAgent.Transport.queryResponseFields(Arrays.asList(map("path","/data/0/text/child")),"/data/*/text").isEmpty());
        System.out.println("POLICY_GUARDS_PASSED="+count);
    }
}
