import java.security.SecureRandom;
import java.util.*;

/** W3C Trace Context Level 1 propagation. No field/taint labels or exporter. */
public final class W3CTraceContext {
    private static final SecureRandom RANDOM=new SecureRandom();
    public final String traceId,spanId,parentId,requestSpanId,flags,state;
    private W3CTraceContext(String trace,String span,String parent,String request,String flags,String state){
        this.traceId=trace;this.spanId=span;this.parentId=parent;this.requestSpanId=request;this.flags=flags;this.state=state;
    }
    private static boolean hex(String s,int n){return s!=null&&s.length()==n&&s.matches("[0-9a-f]+")&&!s.matches("0+");}
    private static String id(int n){byte[] bytes=new byte[n];StringBuilder s;do{RANDOM.nextBytes(bytes);s=new StringBuilder();for(byte b:bytes)s.append(String.format("%02x",b&255));}while(s.toString().matches("0+"));return s.toString();}
    public static W3CTraceContext parse(String parent,String state){
        if(parent==null||parent.length()<55)return null;
        String v=parent.substring(0,2);if(!v.matches("[0-9a-f]{2}")||v.equals("ff"))return null;
        if(parent.charAt(2)!='-'||parent.charAt(35)!='-'||parent.charAt(52)!='-')return null;
        if((v.equals("00")&&parent.length()!=55)||(parent.length()>55&&parent.charAt(55)!='-'))return null;
        String trace=parent.substring(3,35),span=parent.substring(36,52),f=parent.substring(53,55);
        if(!hex(trace,32)||!hex(span,16)||!f.matches("[0-9a-f]{2}"))return null;
        return new W3CTraceContext(trace,span,null,span,(Integer.parseInt(f,16)&1)==0?"00":"01",validState(state));
    }
    public static String validState(String state){
        if(state==null||state.isEmpty()||state.length()>512)return null;
        String[] members=state.split(",",-1);if(members.length>32)return null;
        Set<String> keys=new HashSet<>();List<String> out=new ArrayList<>();
        for(String member:members){
            // OWS around list members is permitted; whitespace inside a value
            // is retained. Empty members are allowed by the HTTP list grammar.
            String m=member.replaceAll("^[ \\t]+|[ \\t]+$","");if(m.isEmpty())continue;
            int eq=m.indexOf('=');if(eq<1)return null;String k=m.substring(0,eq).replaceAll("[ \\t]+$",""),value=m.substring(eq+1);
            if(k.length()>256||!k.matches("(?:[a-z][a-z0-9_*/-]{0,255}|[a-z0-9][a-z0-9_*/-]{0,240}@[a-z][a-z0-9_*/-]{0,13})")||!keys.add(k))return null;
            if(value.isEmpty()||value.length()>256||!value.matches("[\\x20-\\x2b\\x2d-\\x3c\\x3e-\\x7e]*[\\x21-\\x2b\\x2d-\\x3c\\x3e-\\x7e]"))return null;
            out.add(k+"="+value);
        }
        return out.isEmpty()?null:String.join(",",out);
    }
    public static W3CTraceContext server(String header,String state){
        W3CTraceContext p=parse(header,state);String span=id(8);
        return p==null?new W3CTraceContext(id(16),span,null,span,"01",null):new W3CTraceContext(p.traceId,span,p.spanId,p.spanId,p.flags,p.state);
    }
    public static W3CTraceContext client(W3CTraceContext p){String span=id(8);return p==null?new W3CTraceContext(id(16),span,null,span,"01",null):new W3CTraceContext(p.traceId,span,p.spanId,span,p.flags,p.state);}
    public String wire(){return "00-"+traceId+"-"+spanId+"-"+flags;}
    public String message(){return traceId+"/"+requestSpanId;}
    public Map<String,Object> fields(){Map<String,Object> r=new LinkedHashMap<>();r.put("transport_protocol","w3c-trace-context");r.put("message",message());r.put("trace_id",traceId);r.put("request_span_id",requestSpanId);r.put("span_id",spanId);r.put("parent_span_id",parentId);r.put("trace_flags",flags);r.put("tracestate",state);return r;}
}
