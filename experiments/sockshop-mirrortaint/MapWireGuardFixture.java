import java.util.*;
import java.lang.reflect.*;
import com.fasterxml.jackson.databind.ObjectMapper;
public class MapWireGuardFixture {
 static class BadList extends ArrayList<Object>{static int hits;public Iterator<Object> iterator(){hits++;throw new IllegalStateException("unknown iterator");}public Object get(int i){hits++;throw new IllegalStateException("unknown get");}}
 public static void main(String[] args)throws Exception{
  ObjectMapper mapper=new ObjectMapper();int rejected=0;
  for(MapWrapperFixture.Wrapper w:Arrays.asList(new MapWrapperFixture.BadGet(),new MapWrapperFixture.BadKeys())){
   w.put("data",null);
   try{ResponseBindingHooks.checkPath(w,mapper,new String[]{"data"},0);throw new AssertionError();}catch(IllegalStateException expected){rejected++;}
   try{SpringTransportAgent.Transport.snapshot(w,true);throw new AssertionError();}catch(IllegalStateException expected){rejected++;}
   try{SpringTransportAgent.Transport.snapshot(w);throw new AssertionError();}catch(IllegalStateException expected){rejected++;}
   if(SpringTransportAgent.Transport.TARGET_MAPS.get()!=null)throw new AssertionError("target scope leaked");
  }
  MapWrapperFixture.Wrapper good=new MapWrapperFixture.Wrapper();good.put("data",null);
  Field cache=java.util.AbstractMap.class.getDeclaredField("keySet");cache.setAccessible(true);Object before=cache.get(good);
  ResponseBindingHooks.checkPath(good,mapper,new String[]{"data"},0);SpringTransportAgent.Transport.snapshot(good,true);
  if(cache.get(good)!=before)throw new AssertionError("observer created key view");
  MapWrapperFixture.Wrapper nested=new MapWrapperFixture.Wrapper();nested.put("data",new BadList());
  try{SpringTransportAgent.Transport.snapshot(nested,true);throw new AssertionError();}catch(IllegalStateException expected){rejected++;}
  try{ResponseBindingHooks.checkPath(nested,mapper,new String[]{"data","0"},0);throw new AssertionError();}catch(IllegalStateException expected){rejected++;}
  if(MapWrapperFixture.BadGet.hits!=0||MapWrapperFixture.BadKeys.hits!=0||BadList.hits!=0)throw new AssertionError("application override executed");
  System.out.println("{\"rejected\":"+rejected+",\"get_hits\":0,\"key_hits\":0,\"list_hits\":0,\"key_view_unchanged\":true}");
 }
}
