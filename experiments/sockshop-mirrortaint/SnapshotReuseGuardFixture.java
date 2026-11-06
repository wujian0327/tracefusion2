import java.lang.reflect.*;
import java.nio.file.*;
import java.util.*;
import com.alibaba.fastjson2.*;
/** Checks mutable contents and Class identity independently of dependency inference. */
public final class SnapshotReuseGuardFixture {
 public static class Metadata {public int value;}
 static int rejected;
 static void reject(JsonTreeObservationHooks.Snapshot s)throws Exception{try{s.verify();throw new AssertionError("changed snapshot accepted");}catch(IllegalStateException expected){rejected++;}}
 public static void main(String[]args)throws Exception{
  JSONArray array=new JSONArray();array.add(new String("same"));JsonTreeObservationHooks.Snapshot a=JsonTreeObservationHooks.snapshot(array);array.set(0,new String("same"));reject(a);
  a=JsonTreeObservationHooks.snapshot(array);array.add(null);reject(a);
  JSONObject map=new JSONObject();map.put("k",new String("same"));JsonTreeObservationHooks.Snapshot m=JsonTreeObservationHooks.snapshot(map);map.put("k",new String("same"));reject(m);
  m=JsonTreeObservationHooks.snapshot(map);map.put("next",null);reject(m);
  JsonTreeObservationHooks.Snapshot fresh=JsonTreeObservationHooks.snapshot(map);fresh.verify();if(fresh==m)throw new AssertionError("old contents reused");
  String name=Metadata.class.getName();byte[] bytes=Files.readAllBytes(Paths.get(args[0],name+".class"));Class<?>[] types=new Class<?>[2];
  for(int i=0;i<2;i++)types[i]=new ClassLoader(null){protected Class<?> findClass(String n)throws ClassNotFoundException{if(!n.equals(name))throw new ClassNotFoundException(n);return defineClass(n,bytes,0,bytes.length);}}.loadClass(name);
  Field left=JsonTreeObservationHooks.field(types[0],"value"),right=JsonTreeObservationHooks.field(types[1],"value");if(left==right||left.getDeclaringClass()==right.getDeclaringClass()||left!=JsonTreeObservationHooks.field(types[0],"value"))throw new AssertionError("Class identity cache differs");
  System.out.println("{\"same_value_and_structure_changes_rejected\":"+rejected+",\"fresh_contents\":true,\"classloader_identity\":true}");
 }
}
