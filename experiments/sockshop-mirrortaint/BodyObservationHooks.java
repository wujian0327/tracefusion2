import java.util.*;

/** Passive prefix guard. Never calls an application method to inspect aliases. */
public final class BodyObservationHooks {
 static final ThreadLocal<Map<String,Root>> ROOTS=ThreadLocal.withInitial(HashMap::new);
 static final ThreadLocal<Map<String,Mode>> MODES=ThreadLocal.withInitial(HashMap::new);
 static class Root {Map certificate;Object sourceCall;String body,revoked;final Set<String> owners=new TreeSet<>();final Map<String,Map> objects=new HashMap<>();final Map<Object,Map> calls=new HashMap<>(),decisions=new HashMap<>();}
 static class Mode {Object call;long reads,branches;Mode(Object id){call=id;}}
 static Map config(){return ExecutionKernelHooks.enabled()?(Map)((Map)PlannedServiceAgent.plan.get("execution_kernel")).get("body_observation"):null;}
 static String root(){if(PlannedServiceAgent.Recorder.STACK.get().isEmpty())return null;PlannedServiceAgent.Recorder.Frame bottom=PlannedServiceAgent.Recorder.STACK.get().peekLast();return bottom.method.equals(PlannedServiceAgent.plan.get("entry"))?bottom.id:null;}
 static Root current(){return ROOTS.get().get(root());}
 static boolean hit(Object raw,Root state){return raw instanceof Map&&!((Map)raw).containsKey("value")&&state.owners.contains(((Map)raw).get("object"));}
 static boolean references(Object raw,Root state){if(raw instanceof Map){if(hit(raw,state))return true;for(Object v:((Map)raw).values())if(v instanceof Map||v instanceof List)if(references(v,state))return true;}else if(raw instanceof List){for(Object v:(List)raw)if(references(v,state))return true;}return false;}
 static boolean safeGetter(Map row){Map getters=(Map)PlannedServiceAgent.plan.get("collection_getters"),proof=(Map)getters.get(row.get("callee"));return proof!=null&&Objects.equals(proof.get("implementation"),row.get("accessor_implementation"))&&row.get("getter")!=null;}
 static boolean safeMapGet(Map row,Root state){String key=(String)row.get("callee");if(!Arrays.asList("java/util/Map.get(Ljava/lang/Object;)Ljava/lang/Object;","java/util/HashMap.get(Ljava/lang/Object;)Ljava/lang/Object;").contains(key))return false;Map receiver=(Map)row.get("receiver"),node=receiver==null?null:state.objects.get(receiver.get("object"));if(node==null||!Arrays.asList("java/util/HashMap","java/util/LinkedHashMap").contains(node.get("type")))return false;List args=(List)row.get("args"),types=(List)row.get("argument_types");return args!=null&&args.size()==1&&types!=null&&types.equals(Collections.singletonList("java.lang.String"))&&((Map)args.get(0)).get("value")instanceof String;}
 static void revoke(Root state,String reason){if(state.revoked==null)state.revoked=reason;}
 static void observe(String kind,Map row){Map cfg=config();if(cfg==null)return;String root=root();if(root==null)return;Root state=ROOTS.get().computeIfAbsent(root,k->new Root());
  if(kind.equals("collection-call-enter")){
   String site=row.get("method")+"@"+row.get("pc");Map source=(Map)cfg.get("source"),candidate=(Map)((Map)cfg.get("candidates")).get(site);
   if(Objects.equals(row.get("callee"),source.get("callee"))||candidate!=null)state.calls.put(row.get("call_id"),new LinkedHashMap(row));
   if(state.certificate!=null){boolean touches=hit(row.get("receiver"),state)||references(row.get("args"),state);if(touches&&!safeGetter(row)&&!safeMapGet(row,state)){
     if(MODES.get().containsKey(row.get("frame")))throw new IllegalStateException("Effect-only body reached private source graph");
     revoke(state,"private-graph-passed-to-call");
   }}
   if(candidate!=null){boolean eligible=state.certificate!=null&&state.revoked==null&&!PlannedServiceAgent.Recorder.captureInvalid&&!hit(row.get("receiver"),state)&&!references(row.get("args"),state);
    Map decision=new LinkedHashMap();decision.put("version",1);decision.put("root_frame",root);decision.put("callee",candidate.get("callee"));decision.put("guard_eligible",eligible);decision.put("selected",eligible&&"selective".equals(PlannedServiceAgent.mode)&&Boolean.TRUE.equals(cfg.get("enabled"))&&!System.getProperty("service.body.observation","true").equals("false"));decision.put("reason",state.certificate==null?"no-closed-source-island":state.revoked);decision.put("source_call_id",state.sourceCall);decision.put("ownership_id",state.certificate==null?null:state.certificate.get("ownership_id"));decision.put("source_seq",state.certificate==null?null:state.certificate.get("seq"));decision.put("body",state.body);decision.put("private_owners",new ArrayList(state.owners));row.put("body_observation",decision);state.decisions.put(row.get("call_id"),decision);
   }
  }else if(kind.equals("locality-end")&&Boolean.TRUE.equals(row.get("valid"))){
   Map call=state.calls.get(row.get("call_id")),source=(Map)cfg.get("source");
   if(call!=null&&Objects.equals(call.get("method"),source.get("caller"))&&Objects.equals(call.get("pc"),source.get("pc"))&&Objects.equals(call.get("callee"),source.get("callee"))){
    if(state.certificate!=null){revoke(state,"source-occurrence-repeated");return;}
    state.certificate=row;state.sourceCall=row.get("call_id");state.body=(String)row.get("body");for(Object node:(List)row.get("objects")){state.owners.add((String)((Map)node).get("owner"));state.objects.put((String)((Map)node).get("owner"),(Map)node);}
   }
  }else if(kind.equals("enter")){
   Mode parent=MODES.get().get(row.get("parent"));Mode mode=null;
   if(parent!=null)mode=new Mode(parent.call);
   else if(!CollectionServiceHooks.CALLS.get().isEmpty()){
    Map actual=CollectionServiceHooks.CALLS.get().peek(),decision=state.decisions.get(actual.get("call_id"));
    if(decision!=null&&Boolean.TRUE.equals(decision.get("selected"))&&Objects.equals(row.get("method"),decision.get("callee")))mode=new Mode(actual.get("call_id"));
   }
   if(mode!=null){MODES.get().put((String)row.get("frame"),mode);row.put("body_observation_call",mode.call);}
  }else if(kind.equals("exit")||kind.equals("abort")){
   Mode mode=MODES.get().get(row.get("frame"));if(mode!=null){row.put("body_observation_call",mode.call);Map counts=new LinkedHashMap();counts.put("field_reads",mode.reads);counts.put("branches",mode.branches);row.put("body_observation_omissions",counts);}
  }else if(state.certificate!=null){
   boolean mutation=(kind.equals("write")||kind.equals("write-version"))&&(state.owners.contains(row.get("owner"))||hit(row.get("observed"),state));
   boolean capture=kind.equals("execution-lambda")&&references(row.get("captures"),state);
   boolean array=kind.equals("execution-array")&&"store".equals(row.get("operation"))&&references(row.get("value"),state);
   if(mutation||capture||array){if(MODES.get().containsKey(row.get("frame")))throw new IllegalStateException("Effect-only body touched/published private graph");revoke(state,mutation?"private-graph-write-or-store":capture?"private-graph-capture":"private-graph-array-store");}
   if(kind.equals("binding-return")&&state.decisions.values().stream().anyMatch(d->Boolean.TRUE.equals(d.get("selected")))&&!Objects.equals(((Map)row.get("result")).get("object"),state.body))throw new IllegalStateException("Effect-only return forward proof violated");
  }
 }
 public static boolean omitRead(Object receiver,String field,String site){synchronized(PlannedServiceAgent.Recorder.class){if(config()==null||PlannedServiceAgent.Recorder.STACK.get().isEmpty())return false;Mode mode=MODES.get().get(PlannedServiceAgent.Recorder.STACK.get().peek().id);if(mode==null)return false;Root state=current();if(state.owners.contains(PlannedServiceAgent.Recorder.id(receiver)))throw new IllegalStateException("Omitted read reaches private graph");mode.reads++;return true;}}
 static boolean omitBranch(){if(config()==null||PlannedServiceAgent.Recorder.STACK.get().isEmpty())return false;Mode mode=MODES.get().get(PlannedServiceAgent.Recorder.STACK.get().peek().id);if(mode==null)return false;mode.branches++;return true;}
}
