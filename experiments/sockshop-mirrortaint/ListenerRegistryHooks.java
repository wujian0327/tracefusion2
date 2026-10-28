import java.util.*;
import java.lang.reflect.*;
/** Metadata-filter closure before Mongo mapping events, not callback purity. */
public final class ListenerRegistryHooks {
 static Object field(Object o,String n)throws Exception{return ResponseBindingHooks.member(o,n);}
 static boolean instance(Object o,String name)throws Exception{return Class.forName(name,false,o.getClass().getClassLoader()).isInstance(o);}
 static boolean listener(Object o,List details,Set<Object> seen)throws Exception{
  if(o==null)return false;if(!seen.add(o))return true;if(seen.size()>1000)return false;String cls=o.getClass().getName(),owner=cls.replace('.','/');Map row=new LinkedHashMap();row.put("class",cls);row.put("object",PlannedServiceAgent.Recorder.value(o));try{row.put("class_sha256",ExecutionKernelHooks.classHash(o.getClass()));}catch(Exception unavailable){row.put("class_sha256",null);row.put("generated_class_bytes_unavailable",true);}boolean smart=instance(o,"org.springframework.context.event.SmartApplicationListener"),generic=instance(o,"org.springframework.context.event.GenericApplicationListener"),ordered=instance(o,"org.springframework.core.Ordered");row.put("smart",smart);row.put("generic",generic);row.put("ordered",ordered);details.add(row);
  boolean identity=o.getClass().getMethod("equals",Object.class).getDeclaringClass()==Object.class&&o.getClass().getMethod("hashCode").getDeclaringClass()==Object.class;row.put("identity_defaults",identity);Map pins=(Map)SaveEffectHooks.config().getOrDefault("listener_filter_class_sha256",Collections.emptyMap());boolean known=pins.containsKey(owner)&&Objects.equals(pins.get(owner),row.get("class_sha256"));row.put("filter_approved",known||identity&&!smart&&!generic);
  if(!(known||identity&&!smart&&!generic))return false;
  if(cls.equals("org.springframework.boot.builder.ParentContextCloserApplicationListener$ContextCloserListener")){Object ref=field(o,"childContext");if(ref==null||ref.getClass()!=java.lang.ref.WeakReference.class)return false;Object child=((java.lang.ref.WeakReference)ref).get();if(child!=null&&(child.getClass().getMethod("equals",Object.class).getDeclaringClass()!=Object.class||child.getClass().getMethod("hashCode").getDeclaringClass()!=Object.class))return false;}
  if(cls.equals("org.springframework.context.event.GenericApplicationListenerAdapter")||cls.equals("org.springframework.context.event.SourceFilteringListener")){Object delegate=field(o,"delegate");row.put("delegate",PlannedServiceAgent.Recorder.value(delegate));return listener(delegate,details,seen);}
  if(cls.equals("org.springframework.boot.context.config.DelegatingApplicationListener")){Object nested=field(o,"multicaster");if(nested!=null)return registry(nested,details,seen);}
  return true;
 }
 static boolean registry(Object multicast,List details,Set<Object> seen)throws Exception{
  if(!SaveEffectHooks.exact(multicast,"org.springframework.context.event.SimpleApplicationEventMulticaster"))return false;if(!seen.add(multicast))return true;Object retriever=field(multicast,"defaultRetriever");Collection instances=(Collection)field(retriever,"applicationListeners"),names=(Collection)field(retriever,"applicationListenerBeans");Map registration=new LinkedHashMap();registration.put("multicaster",PlannedServiceAgent.Recorder.value(multicast));List ids=new ArrayList();for(Object instance:instances)ids.add(PlannedServiceAgent.Recorder.value(instance));registration.put("direct_instances",ids);List beans=new ArrayList();registration.put("bean_instances",beans);details.add(registration);boolean valid=true;
  for(Object o:instances)valid=listener(o,details,seen)&&valid;
  if(!names.isEmpty()){Object factory=field(multicast,"beanFactory");if(!SaveEffectHooks.exact(factory,"org.springframework.beans.factory.support.DefaultListableBeanFactory"))return false;Map singletons=(Map)field(factory,"singletonObjects"),products=(Map)field(factory,"factoryBeanObjectCache");for(Object raw:names){String name=(String)raw;boolean factoryRef=name.startsWith("&");while(name.startsWith("&"))name=name.substring(1);Object value=singletons.get(name);if(!factoryRef&&(value==null||!instance(value,"org.springframework.context.ApplicationListener")))value=products.get(name);Map bean=new LinkedHashMap();bean.put("name",raw);bean.put("object",PlannedServiceAgent.Recorder.value(value));beans.add(bean);if(value==null){Map missing=new LinkedHashMap();missing.put("uninitialized_listener_bean",raw);details.add(missing);valid=false;}else valid=listener(value,details,seen)&&valid;}}
  return valid;
 }
 static boolean inspect(Object context,Map proof)throws Exception{
  List details=new ArrayList();proof.put("listener_registry",details);boolean valid=true;Set<Object> seen=Collections.newSetFromMap(new IdentityHashMap<Object,Boolean>());Set<Object> contexts=Collections.newSetFromMap(new IdentityHashMap<Object,Boolean>());
  while(context!=null){if(!contexts.add(context)||contexts.size()>8)return false;valid=registry(field(context,"applicationEventMulticaster"),details,seen)&&valid;context=SaveEffectHooks.call(context,"getParent");}proof.put("listener_filters_verified",valid);return valid;
 }
}
