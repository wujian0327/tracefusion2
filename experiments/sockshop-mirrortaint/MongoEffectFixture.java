import java.util.*;
import java.util.concurrent.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.mongodb.*;
import org.springframework.context.*;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.mongodb.core.*;
import org.springframework.data.mongodb.core.convert.*;
import org.springframework.data.mongodb.core.mapping.DBRef;
import org.springframework.data.mongodb.core.mapping.event.*;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.support.*;

public class MongoEffectFixture {
    public static class Ref {private String id;public Ref(){}public Ref(String x){id=x;}public String getId(){return id;}public void setId(String x){id=x;}}
    public static class Out {private String id,text;@DBRef private List<Ref> refs=new ArrayList<Ref>();public Out(){}public String getId(){return id;}public void setId(String x){id=x;}public String getText(){return text;}public void setText(String x){text=x;}public List<Ref> getRefs(){return refs;}public void setRefs(List<Ref> x){refs=x;}}
    public static class Mutator implements ApplicationListener<BeforeSaveEvent> {public void onApplicationEvent(BeforeSaveEvent e){if(e.getSource() instanceof Out)((Out)e.getSource()).setText(new String("SAME"));}}
    public static class AnnotatedMutator {@EventListener public void mutate(BeforeSaveEvent e){if(e.getSource() instanceof Out)((Out)e.getSource()).setText(new String("SAME"));}}
    @org.springframework.data.convert.WritingConverter
    public static class CustomWriter implements Converter<Out,DBObject>{public DBObject convert(Out out){out.setText(new String("SAME"));return new BasicDBObject("text",out.getText());}}
    public static class FailingTemplate extends MongoTemplate {public FailingTemplate(MongoClient c,String db){super(c,db);}public void insert(Object o,String collection){throw new IllegalArgumentException("expected-save-failure");}}
    public static Out root(MongoRepository<Out,String> repository,String input,int mode){Out out=new Out();out.setText(input);if(mode==4)out.getRefs().add(new Ref("existing-reference"));try{return repository.save(out);}catch(IllegalArgumentException expected){Out fallback=new Out();fallback.setText("FALLBACK");return fallback;}}
    public static void main(String[]args)throws Exception{
        MongoClient client=new MongoClient("127.0.0.1",Integer.parseInt(args[0]));ObjectMapper mapper=new ObjectMapper();List cases=new ArrayList();
        try{for(int n=0;n<14;n++){int mode=n%7;AnnotationConfigApplicationContext context=new AnnotationConfigApplicationContext();if(mode==1)context.addApplicationListener(new Mutator());if(mode==2)context.register(AnnotatedMutator.class);context.refresh();
            try{
                MongoTemplate template=mode==5?new FailingTemplate(client,"tf2_effect_controls"):new MongoTemplate(client,"tf2_effect_controls");template.setApplicationContext(context);MappingMongoConverter converter=(MappingMongoConverter)template.getConverter();
                if(mode==3){converter.setCustomConversions(new CustomConversions(Arrays.asList(new CustomWriter())));converter.afterPropertiesSet();}
                org.springframework.data.mongodb.core.mapping.MongoMappingContext mapping=(org.springframework.data.mongodb.core.mapping.MongoMappingContext)converter.getMappingContext();mapping.getPersistentEntity(Out.class);mapping.getPersistentEntity(Ref.class);
                MongoRepository<Out,String> repository=new SimpleMongoRepository<Out,String>(new MappingMongoEntityInformation<Out,String>((org.springframework.data.mongodb.core.mapping.MongoPersistentEntity<Out>)(Object)mapping.getPersistentEntity(Out.class)),template);
                String span=String.format("%016x",n+1);SpringTransportAgent.Transport.ASYNC.set(W3CTraceContext.server("00-22222222222222222222222222222222-"+span+"-01",null));Out out=root(repository,new String("SAME"),mode);
                if(!SaveEffectHooks.ACTIVE.get().isEmpty())throw new AssertionError("Save effect scope leaked across calls");
                SpringTransportAgent.Transport.writeEnd(SpringTransportAgent.Transport.writeStart(out,null),out);Map row=new LinkedHashMap();row.put("mode",mode);row.put("message","22222222222222222222222222222222/"+span);row.put("response",mapper.readValue(mapper.writeValueAsString(out),Map.class));cases.add(row);
            }finally{context.close();SpringTransportAgent.Transport.ASYNC.remove();}
        }}finally{client.close();}System.out.println(mapper.writeValueAsString(cases));
    }
}
