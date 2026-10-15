import edu.columbia.cs.psl.phosphor.runtime.*;
import java.util.*;

/** Native labels through primitive arithmetic and a sequential Stream lambda. */
public class PropagationProbe {
    static class Item {int quantity;float price;Item(int q,float p){quantity=q;price=p;}}
    public static void main(String[] args)throws Exception {
        Item item=new Item(MultiTainter.taintedInt(2,"quantity"),MultiTainter.taintedFloat(5.0f,"price"));
        float total=(float)Collections.singletonList(item).stream().mapToDouble(i->i.quantity*i.price).sum()+4.99f;
        if(Math.abs(total-14.99f)>0.001f)throw new AssertionError("Value changed: "+total);
        Taint tags=MultiTainter.getTaint(total);
        if(tags==null)throw new AssertionError("Missing native source labels");
        Set<String> actual=new TreeSet<>();
        for(Object tag:(Object[])tags.getClass().getMethod("getLabels").invoke(tags))actual.add(tag.toString());
        if(!actual.equals(new TreeSet<>(Arrays.asList("quantity","price"))))throw new AssertionError(actual);
        System.out.println("PHOSPHOR_PROPAGATION_PASS "+actual);
    }
}
