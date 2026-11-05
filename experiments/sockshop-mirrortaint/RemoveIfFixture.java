import java.util.*;
import java.util.function.Predicate;
import com.fasterxml.jackson.databind.ObjectMapper;
public class RemoveIfFixture {
 public static class Box{public int id;public String text;public Box(int i,String t){id=i;text=t;}public int getId(){return id;}public String getText(){return text;}}
 public static class Store{public Box read(int n){return new Box(n,"SAME");}}
 public static class Out{public List<Box> items;public Out(List<Box> v){items=v;}public List<Box> getItems(){return items;}}
 public static class UnsupportedList extends ArrayList<Box>{static int iterations;public Iterator<Box> iterator(){iterations++;return super.iterator();}}
 public List<Box> last;
 static final IllegalArgumentException ORIGINAL=new IllegalArgumentException("original");
 public Out root(Store store,int mode,Predicate<Box> opaque){
  List<Box> list=mode==8?new UnsupportedList():new ArrayList<>();list.add(store.read(0));list.add(store.read(1));last=list;
  if(mode==6){list.removeIf(b->{list.add(new Box(2,"SAME"));return true;});return new Out(list);}
  try{
   if(mode==5)list.removeIf(null);
   else if(mode==7)list.removeIf(opaque);
   else list.removeIf(b->{if(mode==4){if(b.id==0){b.text="SAME";return true;}throw ORIGINAL;}if(mode==2)return false;if(mode==3)return true;return b.id==mode;});
  }catch(IllegalArgumentException e){if(e!=ORIGINAL)throw e;}catch(NullPointerException e){}
  return new Out(list);
 }
 public static void main(String[] args)throws Exception{
  boolean observe=Boolean.getBoolean("fixture.observe");RemoveIfFixture f=new RemoveIfFixture();ObjectMapper json=new ObjectMapper();List<Map> results=new ArrayList<>();
  boolean unsupported=args.length>0;for(int mode=unsupported?8:0;mode<(unsupported?9:8);mode++){
   W3CTraceContext ctx=W3CTraceContext.server(null,null);if(observe)SpringTransportAgent.Transport.ASYNC.set(ctx);Map row=new LinkedHashMap();row.put("case",mode);
   try{Out out=f.root(new Store(),mode,new Predicate<Box>(){public boolean test(Box b){return false;}});row.put("status","normal");if(observe)ResponseBindingHooks.verifySerialization(out,json);}
   catch(ConcurrentModificationException e){row.put("status",e.getClass().getName());}
   if(observe&&!unsupported){Map wire=ctx.fields();wire.put("uri",null);wire.put("direction","response");wire.put("phase","write");wire.put("fields",SpringTransportAgent.Transport.snapshot(new Out(f.last)));PlannedServiceAgent.Recorder.emit("http-json",wire);row.put("message",ctx.message());SpringTransportAgent.Transport.ASYNC.remove();}
   if(observe)SpringTransportAgent.Transport.ASYNC.remove();
   row.put("items",json.readValue(json.writeValueAsString(f.last),List.class));row.put("iterator_calls",UnsupportedList.iterations);results.add(row);
  }System.out.println(json.writeValueAsString(results));
 }
}
