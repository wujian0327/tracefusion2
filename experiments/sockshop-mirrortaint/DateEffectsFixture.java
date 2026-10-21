import java.util.*;
import com.fasterxml.jackson.databind.*;
import com.mongodb.*;
import org.springframework.context.*;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.data.mongodb.core.*;
import org.springframework.data.mongodb.core.mapping.event.*;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.support.*;
public class DateEffectsFixture {
 public static class Input{public Date date;public Input(){date=new Date(1000);}public Date getDate(){return date;}}
 public static class Out{private String id;private Date date;public Out(){}public String getId(){return id;}public void setId(String x){id=x;}public Date getDate(){return date;}public void setDate(Date x){date=x;}}
 public static class Mutator implements ApplicationListener<BeforeSaveEvent>{public void onApplicationEvent(BeforeSaveEvent e){if(e.getSource() instanceof Out){Date d=((Out)e.getSource()).getDate();d.setTime(d.getTime());}}}
 static Date opaque(Date d){int[] unsupported=new int[1];return d;}
 public static Out root(MongoRepository<Out,String> repo,Input left,Input right,int mode){
  Out out=new Out();Date d=mode==1||mode==10?right.getDate():left.getDate();
  if(mode==2)d=Calendar.getInstance().getTime();
  if(mode==3)d.setTime(d.getTime());
  if(mode==4)d=opaque(d);
  if(mode>=5&&mode<=8)d=new Date(d.getTime());
  if(mode==11)d=new Date(1000);
  if(mode==12)d=new Date(left.getDate().getTime());
  out.setDate(d);
  if(mode==10)new StringBuilder().append((Object)left.getDate()).append((Object)right.getDate()).toString();
  else if(mode==13)d.toString();
  else new StringBuilder().append((Object)d).toString();
  if(mode>=5&&mode<=8)return repo.save(out);
  return out;
 }
 public static void main(String[]args)throws Exception{
  MongoClient client=new MongoClient("127.0.0.1",Integer.parseInt(args[0]));ObjectMapper json=new ObjectMapper();List cases=new ArrayList();TimeZone original=TimeZone.getDefault();
  try{for(int n=0;n<28;n++){int mode=n%14;AnnotationConfigApplicationContext context=new AnnotationConfigApplicationContext();if(mode==6)context.addApplicationListener(new Mutator());context.refresh();
   try{MongoTemplate template=new MongoTemplate(client,"tf2_date_effects");template.setApplicationContext(context);org.springframework.data.mongodb.core.mapping.MongoMappingContext mapping=(org.springframework.data.mongodb.core.mapping.MongoMappingContext)template.getConverter().getMappingContext();mapping.getPersistentEntity(Out.class);MongoRepository<Out,String> repo=new MongoRepositoryFactory(template).getRepository(DateRepo.class);
    template.getCollection(template.getCollectionName(Out.class)).setDBEncoderFactory(DefaultDBEncoder.FACTORY);
    if(mode==7)template.getCollection(template.getCollectionName(Out.class)).setDBEncoderFactory(new DBEncoderFactory(){public DBEncoder create(){return new DefaultDBEncoder();}});
    if(mode==8)org.bson.BSON.addEncodingHook(Date.class,new org.bson.Transformer(){public Object transform(Object value){Date d=(Date)value;d.setTime(d.getTime());return d;}});
    if(mode==9)TimeZone.setDefault(new SimpleTimeZone(0,"same-UTC-custom-class"));
    String span=String.format("%016x",n+1);SpringTransportAgent.Transport.ASYNC.set(W3CTraceContext.server("00-dddddddddddddddddddddddddddddddd-"+span+"-01",null));Out out=root(repo,new Input(),new Input(),mode);ResponseBindingHooks.verifySerialization(out,json);SpringTransportAgent.Transport.writeEnd(SpringTransportAgent.Transport.writeStart(out,null),out);Map c=new LinkedHashMap();c.put("mode",mode);c.put("message","dddddddddddddddddddddddddddddddd/"+span);c.put("response",json.readValue(json.writeValueAsString(out),Map.class));cases.add(c);
   }finally{org.bson.BSON.clearAllHooks();TimeZone.setDefault(original);context.close();SpringTransportAgent.Transport.ASYNC.remove();}
  }}finally{client.close();}System.out.println(json.writeValueAsString(cases));
 }
 public interface DateRepo extends MongoRepository<Out,String>{}
}
