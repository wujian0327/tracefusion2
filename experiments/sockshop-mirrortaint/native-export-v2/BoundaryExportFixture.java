import java.util.*;
public class BoundaryExportFixture {
 static final IllegalArgumentException ORIGINAL=new IllegalArgumentException("business-original");
 static int cleaned;
 public static class Item {private String text;public Item(String s){text=s;}public String getText(){return text;}public void setText(String s){text=s;}}
 public static class Repo {public Item read(Item i){return i;}public Item save(Item i,boolean fail){if(fail)throw ORIGINAL;return i;}public void remove(Item i){if(i==null)throw ORIGINAL;}}
 static String root(Repo r,Item input,int mode){try{Item i=r.read(input);if(mode==2)r.remove(null);r.save(i,mode==1);return i.text;}catch(IllegalArgumentException e){if(e!=ORIGINAL)throw new AssertionError("Exception identity changed");return"caught";}finally{cleaned++;}}
 public static void main(String[]args){MirrorCapabilityAgent.ATOMIC_SOURCE.set("fixture-only-do-not-tag");try{if(!Boolean.FALSE.equals(NativeBoundaryFactsAgent.snapshot(UUID.randomUUID()).get("complete")))throw new AssertionError("Observer entered native tagging scope");}finally{MirrorCapabilityAgent.ATOMIC_SOURCE.remove();}Repo r=new Repo();for(int mode:new int[]{0,1,0,2,0}){String v=root(r,new Item(new String("SAME")),mode);System.out.println("BUSINESS|"+mode+"|"+v+"|"+cleaned);}}
}
