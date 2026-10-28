import java.util.*;

/** Exact Date facts and pinned default serialization; no provenance computation. */
public final class TemporalDateHooks {
    static boolean emitted;
    static final Map<Object,Object[]> WIRE=new IdentityHashMap<>();
    static Map config(){return PlannedServiceAgent.plan==null?null:(Map)PlannedServiceAgent.plan.get("date_projection");}
    static boolean date(Object value){if(config()==null||!(value instanceof Date))return false;if(value.getClass()!=Date.class)throw new IllegalStateException("Date subclass outside finite projection");return true;}
    static Map observe(Date value){Map r=new LinkedHashMap();r.put("object",PlannedServiceAgent.Recorder.id(value));r.put("date_epoch_ms",value.getTime());r.put("date_type",value.getClass().getName());return r;}
    static Map runtime()throws Exception{Map r=new LinkedHashMap();r.put("java_runtime_version",System.getProperty("java.runtime.version"));Map hashes=new TreeMap();for(String c:new String[]{"java/util/Date","java/util/Calendar","java/util/GregorianCalendar","java/util/Calendar$Builder","sun/util/locale/provider/LocaleProviderAdapter","sun/util/locale/provider/CalendarProviderImpl"})hashes.put(c,JdkContractProbe.hash(c));r.put("class_sha256",hashes);return r;}
    static void enter()throws Exception{if(config()!=null&&!emitted){PlannedServiceAgent.Recorder.emit("date-runtime",runtime());emitted=true;}}
    static void constructed(Object receiver,Object[] args,Map event)throws Exception{
        if(!date(receiver))return;Map f=new LinkedHashMap();f.put("kind","date-constructor");f.put("epoch_ms",((Date)receiver).getTime());f.put("arity",args.length);event.put("date_contract",f);
    }
    static Map effects(){return PlannedServiceAgent.plan==null?null:(Map)PlannedServiceAgent.plan.get("date_effects");}
    static void begin(Map start){
        if(effects()==null)return;String key=(String)start.get("callee");Object candidate=null;
        if(key.equals("java/util/Date.toString()Ljava/lang/String;"))candidate=start.get("_receiver_ref");
        if(key.equals("java/lang/StringBuilder.append(Ljava/lang/Object;)Ljava/lang/StringBuilder;")){Object[] args=(Object[])start.get("_args_ref");if(args.length==1)candidate=args[0];}
        if(candidate!=null&&candidate.getClass()==Date.class){start.put("_date_effect_ref",candidate);start.put("_date_effect_before",observe((Date)candidate));start.put("_date_effect_zone",TimeZone.getDefault().getClass().getName());}
    }
    static void end(Map start,Object result,Map row)throws Exception{
        if(config()==null)return;String key=(String)start.get("callee");Object receiver=start.get("_receiver_ref");Map f=new LinkedHashMap();
        if(start.containsKey("_date_effect_ref")){
            Object value=start.get("_date_effect_ref");Map proof=new LinkedHashMap();proof.put("kind","date-render");proof.put("before",start.get("_date_effect_before"));proof.put("after",observe((Date)value));Map rt=new LinkedHashMap();rt.put("java_runtime_version",System.getProperty("java.runtime.version"));rt.put("class_sha256",JdkContractProbe.selected(new String[]{"java/util/Date","java/util/TimeZone","sun/util/calendar/ZoneInfo","sun/util/calendar/BaseCalendar","sun/util/calendar/BaseCalendar$Date","sun/util/calendar/CalendarSystem","sun/util/calendar/Gregorian","sun/util/calendar/CalendarUtils"}));proof.put("render_runtime",rt);proof.put("zone",start.get("_date_effect_zone"));proof.put("valid","sun.util.calendar.ZoneInfo".equals(start.get("_date_effect_zone"))&&"sun.util.calendar.ZoneInfo".equals(TimeZone.getDefault().getClass().getName()));row.put("date_effect",proof);
        }
        if(key.equals("java/util/Date.getTime()J")&&date(receiver)){f.put("kind","date-get-time");f.put("date",observe((Date)receiver));f.put("epoch_ms",result);}
        else if(key.equals("java/util/Calendar.getInstance()Ljava/util/Calendar;")){f.put("kind","calendar-environment");Class adapter=Class.forName("sun.util.locale.provider.LocaleProviderAdapter");Object selected=adapter.getMethod("getAdapter",Class.class,Locale.class).invoke(null,Class.forName("sun.util.spi.CalendarProvider"),Locale.getDefault(Locale.Category.FORMAT));Object provider=adapter.getMethod("getCalendarProvider").invoke(selected);f.put("provider_type",provider==null?null:provider.getClass().getName());f.put("valid",result!=null&&result.getClass()==GregorianCalendar.class&&provider!=null&&provider.getClass().getName().equals("sun.util.locale.provider.CalendarProviderImpl"));f.put("calendar",PlannedServiceAgent.Recorder.value(result));}
        else if(key.equals("java/util/Calendar.getTime()Ljava/util/Date;")){f.put("kind","calendar-date");f.put("valid",receiver!=null&&receiver.getClass()==GregorianCalendar.class&&date(result));if(date(result))f.put("date",observe((Date)result));}
        if(!f.isEmpty())row.put("date_contract",f);
    }
    static void bindingCall(String key,Object receiver,Object[] args,Object result)throws Exception{
        if(config()==null||ExecutionKernelHooks.enabled()||!(key.startsWith("java/util/Date.")||key.startsWith("java/util/Calendar.")))return;
        Map start=new LinkedHashMap();start.put("callee",key);start.put("_receiver_ref",receiver);start.put("_args_ref",args);Map row=ResponseBindingHooks.row();end(start,result,row);row.put("callee",key);row.put("receiver",PlannedServiceAgent.Recorder.value(receiver));row.put("result",PlannedServiceAgent.Recorder.value(result));PlannedServiceAgent.Recorder.emit("date-call",row);
    }
    static void serializer(Object s)throws Exception{
        if(!s.getClass().getName().equals("com.fasterxml.jackson.databind.ser.std.DateSerializer")||ResponseBindingHooks.member(s,"_customFormat")!=null||ResponseBindingHooks.member(s,"_useTimestamp")!=null)throw new IllegalStateException("Custom Date serializer/format unsupported");
    }
    static void serialization(Date value,Object mapper)throws Exception{
        Object ser=BusinessJackson.call(BusinessJackson.call(mapper,"getSerializerProviderInstance"),"findValueSerializer",Date.class);serializer(ser);
        if(!BusinessJackson.call(mapper,"getDateFormat").getClass().getName().equals("com.fasterxml.jackson.databind.util.StdDateFormat"))throw new IllegalStateException("Custom DateFormat unsupported");
        Map hashes=new TreeMap();for(Class c:new Class[]{mapper.getClass(),ser.getClass(),ser.getClass().getSuperclass(),BusinessJackson.call(mapper,"getDateFormat").getClass()})hashes.put(c.getName().replace('.','/'),ExecutionKernelHooks.classHash(c));
        boolean reviewed=false;for(Object raw:(List)config().get("jackson_profiles"))if(hashes.equals(((Map)raw).get("class_sha256")))reviewed=true;if(!reviewed)throw new IllegalStateException("Unmodeled Date serializer library");
        Object wire=BusinessJackson.call(mapper,"convertValue",value,Object.class);if(!(wire instanceof String||wire instanceof Long||wire instanceof Integer))throw new IllegalStateException("Date wire type unsupported");
        Map row=ResponseBindingHooks.row();row.put("date",observe(value));row.put("wire_value",wire);row.put("timestamp",BusinessJackson.call(mapper,"isEnabled",BusinessJackson.enumValue(mapper,"SerializationFeature","WRITE_DATES_AS_TIMESTAMPS")));row.put("class_sha256",hashes);PlannedServiceAgent.Recorder.emit("date-serialization",row);WIRE.put(value,new Object[]{value.getTime(),wire});
    }
    static void wire(Object value,Map field){if(date(value)&&WIRE.containsKey(value)){Object[] proof=WIRE.get(value);if(!proof[0].equals(((Date)value).getTime()))throw new IllegalStateException("Date changed between serialization checks");field.put("wire_value",proof[1]);}}
}
