import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.mongodb.*;
import org.bson.Document;
import org.bson.codecs.*;
import org.bson.codecs.configuration.CodecRegistries;
import org.springframework.context.*;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.mongodb.core.*;
import org.springframework.data.mongodb.core.convert.*;
import org.springframework.data.mongodb.core.mapping.event.*;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.support.*;
public class Mongo2EffectFixture {
 public static class Input {private Date date=new Date(1000);public Date getDate(){return date;}}
 public static class Out {private String id,text;private Date date;public Out(){}public String getId(){return id;}public void setId(String x){id=x;}public String getText(){return text;}public void setText(String x){text=x;}public Date getDate(){return date;}public void setDate(Date d){date=d;}}
 public static class Mutator implements ApplicationListener<BeforeSaveEvent>{public void onApplicationEvent(BeforeSaveEvent e){if(e.getSource()instanceof Out)((Out)e.getSource()).setText(new String("SAME"));}}
 public static class AnnotatedMutator {@EventListener public void mutate(BeforeSaveEvent e){if(e.getSource()instanceof Out)((Out)e.getSource()).setText(new String("SAME"));}}
 @org.springframework.data.convert.WritingConverter public static class CustomWriter implements Converter<Out,Document>{public Document convert(Out out){out.setText(new String("SAME"));return new Document("_id",out.getId()).append("text",out.getText()).append("date",out.getDate());}}
 public static class SameDateCodec extends DateCodec {public void encode(org.bson.BsonWriter w,Date d,EncoderContext c){d.setTime(d.getTime());super.encode(w,d,c);}}
 public static class FilteredSmart implements org.springframework.context.event.SmartApplicationListener {public boolean supportsEventType(Class<? extends org.springframework.context.ApplicationEvent> type){return false;}public boolean supportsSourceType(Class<?> type){return true;}public int getOrder(){return 0;}public void onApplicationEvent(org.springframework.context.ApplicationEvent event){throw new AssertionError("Filtered callback executed");}}
 public static int conversionConstructions;public static class ConversionsSubclass extends MongoCustomConversions {public ConversionsSubclass(List<?> list){super(list);conversionConstructions++;}}
 public static class FailingTemplate extends MongoTemplate {public FailingTemplate(MongoClient c,String db){super(c,db);}public void save(Object o,String collection){throw new IllegalArgumentException("expected-save-failure");}}
 public interface Repo extends MongoRepository<Out,String>{}
 public static Out root(Repo repo,String text,Input input,int mode){Out out=new Out();out.setId("fixed-control-id");out.setText(text);out.setDate(input.getDate());try{if(mode==8)out.getDate().setTime(out.getDate().getTime());Out saved=repo.save(out);if(mode==7)saved.getDate().setTime(saved.getDate().getTime());return saved;}catch(IllegalArgumentException expected){Out fallback=new Out();fallback.setId("fallback");fallback.setText("FALLBACK");fallback.setDate(new Date(1000));return fallback;}}
 public static void main(String[]args)throws Exception{
  int port=Integer.parseInt(args[0]);ObjectMapper mapper=new ObjectMapper();List cases=new ArrayList();
  for(int n=0;n<22;n++){int mode=n%11;MongoClientOptions options=mode==4?MongoClientOptions.builder().codecRegistry(CodecRegistries.fromRegistries(CodecRegistries.fromCodecs(new SameDateCodec()),MongoClient.getDefaultCodecRegistry())).build():MongoClientOptions.builder().build();MongoClient client=new MongoClient(new ServerAddress("127.0.0.1",port),options);AnnotationConfigApplicationContext context=new AnnotationConfigApplicationContext();if(mode==1)context.addApplicationListener(new Mutator());if(mode==2)context.register(AnnotatedMutator.class);if(mode==9)context.addApplicationListener(new FilteredSmart());context.refresh();
   try{MongoTemplate template=mode==5?new FailingTemplate(client,"tf2_mongo2_effects"):new MongoTemplate(client,"tf2_mongo2_effects");template.setApplicationContext(context);MappingMongoConverter converter=(MappingMongoConverter)template.getConverter();if(mode==3){converter.setCustomConversions(new MongoCustomConversions(Arrays.asList(new CustomWriter())));converter.afterPropertiesSet();}if(mode==10){converter.setCustomConversions(new ConversionsSubclass(Collections.emptyList()));converter.afterPropertiesSet();}org.springframework.data.mongodb.core.mapping.MongoMappingContext mapping=(org.springframework.data.mongodb.core.mapping.MongoMappingContext)converter.getMappingContext();mapping.getPersistentEntity(Out.class);final SimpleMongoRepository<Out,String> nativeRepo=new SimpleMongoRepository<>(new MappingMongoEntityInformation<>((org.springframework.data.mongodb.core.mapping.MongoPersistentEntity<Out>)(Object)mapping.getPersistentEntity(Out.class)),template);Repo repo=(Repo)java.lang.reflect.Proxy.newProxyInstance(Repo.class.getClassLoader(),new Class[]{Repo.class},(proxy,method,a)->{try{return nativeRepo.getClass().getMethod(method.getName(),method.getParameterTypes()).invoke(nativeRepo,a);}catch(java.lang.reflect.InvocationTargetException original){throw original.getCause();}});
    String span=String.format("%016x",n+1);W3CTraceContext c=W3CTraceContext.server("00-33333333333333333333333333333333-"+span+"-01",null);SpringTransportAgent.Transport.ASYNC.set(c);Out out=root(repo,new String("SAME"),new Input(),mode);Map row=new LinkedHashMap();row.put("mode",mode);row.put("conversion_constructions",conversionConstructions);row.put("message",c.message());row.put("response",mapper.readValue(mapper.writeValueAsString(out),Map.class));cases.add(row);if(PlannedServiceAgent.plan!=null){ResponseBindingHooks.verifySerialization(out,mapper);SpringTransportAgent.Transport.writeEnd(SpringTransportAgent.Transport.writeStart(out,null),out);for(Object v:MonitorSafety.inspect().values())if(v instanceof Integer&&((Integer)v)!=0)throw new AssertionError("Monitor scope leak: "+MonitorSafety.inspect());}
   }finally{context.close();client.close();SpringTransportAgent.Transport.ASYNC.remove();}
  }System.out.println(mapper.writeValueAsString(cases));
 }
}
