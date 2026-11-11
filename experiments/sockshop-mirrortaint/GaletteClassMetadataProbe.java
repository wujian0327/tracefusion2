import edu.neu.ccs.prl.galette.internal.runtime.Tag;
import edu.neu.ccs.prl.galette.internal.runtime.Tainter;

/** Finite Class-reference export must not initialize or traverse the business type. */
public final class GaletteClassMetadataProbe {
    static int initialized;
    static final class BusinessType {static {initialized++;}}
    static final class Box {Class<?> type;}
    public static void main(String[] args) throws Exception {
        Class<?> type=Class.forName("GaletteClassMetadataProbe$BusinessType",false,
                GaletteClassMetadataProbe.class.getClassLoader());
        if(initialized!=0)throw new AssertionError("lookup initialized business type");
        Box a=new Box(),b=new Box();
        a.type=Tainter.setTag(type,Tag.of("read-1/type/version-1"));
        b.type=Tainter.setTag(type,Tag.of("read-2/type/version-1"));
        if(!a.type.getName().equals("GaletteClassMetadataProbe$BusinessType")||initialized!=0)
            throw new AssertionError("metadata initialized business type");
        Tag one=Tainter.getTag(a.type),two=Tainter.getTag(b.type);
        if(one==null||two==null||one.size()!=1||two.size()!=1
                ||!one.contains("read-1/type/version-1")||!two.contains("read-2/type/version-1"))
            throw new AssertionError("same Class object merged reference-slot labels");
        a.type=type;
        Tag overwritten=Tainter.getTag(a.type);
        if(overwritten!=null&&!overwritten.isEmpty())throw new AssertionError("constant reference overwrite");
        System.out.println("GALETTE_CLASS_METADATA_OK");
    }
}
