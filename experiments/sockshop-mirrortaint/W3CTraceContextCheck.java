import java.util.*;

/** Protocol boundary tests; run without Spring or a tracing SDK. */
public final class W3CTraceContextCheck {
    static void check(boolean ok,String why){if(!ok)throw new AssertionError(why);}
    public static void main(String[] args){
        String trace="4bf92f3577b34da6a3ce929d0e0e4736",span="00f067aa0ba902b7",wire="00-"+trace+"-"+span+"-01";
        W3CTraceContext p=W3CTraceContext.parse(wire,"vendor=opaque,tenant@system=x");
        check(p!=null&&p.traceId.equals(trace)&&p.spanId.equals(span),"W3C published example");
        for(String invalid:new String[]{"",wire.toUpperCase(),wire+"-extra",wire.substring(0,54),"ff"+wire.substring(2),wire.replace(trace,"00000000000000000000000000000000"),wire.replace(span,"0000000000000000"),wire.replace("-01","-zz"),"01"+wire.substring(2)+"extra"})check(W3CTraceContext.parse(invalid,"v=x")==null,"Invalid parent accepted: "+invalid);
        check(W3CTraceContext.parse("01"+wire.substring(2)+"-future","v=x")!=null,"Future version prefix");
        check(W3CTraceContext.parse(wire,"v=x,v=y").state==null,"Duplicate tracestate key");
        check(W3CTraceContext.parse(wire,"Vendor=x").state==null,"Invalid state key");
        check(W3CTraceContext.parse(wire,"v=x=y").state==null,"Invalid state value");
        check(W3CTraceContext.parse(wire," vendor=x , tenant@system=y ").state.equals("vendor=x,tenant@system=y"),"OWS state");
        StringJoiner many=new StringJoiner(",");for(int i=0;i<32;i++)many.add("v"+i+"=x");check(W3CTraceContext.validState(many.toString())!=null,"32 state entries");many.add("overflow=x");check(W3CTraceContext.validState(many.toString())==null,"33 state entries");
        W3CTraceContext server=W3CTraceContext.server(wire,"vendor=opaque");
        check(server.traceId.equals(trace)&&server.parentId.equals(span)&&server.requestSpanId.equals(span)&&!server.spanId.equals(span),"Server parent relation");
        Set<String> ids=new HashSet<>();for(int i=0;i<1000;i++){W3CTraceContext client=W3CTraceContext.client(server);check(ids.add(client.message())&&client.traceId.equals(trace)&&client.parentId.equals(server.spanId),"Repeated calls must have distinct spans");check(client.state.equals("vendor=opaque"),"State lost");}
        W3CTraceContext restarted=W3CTraceContext.server("invalid","v=x");check(!restarted.traceId.equals(trace)&&restarted.state==null&&restarted.parentId==null,"Invalid context restarts without tracestate");
        W3CTraceContext unsampled=W3CTraceContext.client(W3CTraceContext.server(wire.substring(0,53)+"00","v=x"));check(unsampled.flags.equals("00"),"Unsampled flag propagation");
        W3CTraceContext reserved=W3CTraceContext.client(W3CTraceContext.server(wire.substring(0,53)+"09","v=x"));check(reserved.wire().endsWith("-01"),"Level 1 reserved flags must be cleared");
        System.out.println("W3C parser, state, parent/child, repeated calls, invalid context and sampling flag checks passed");
    }
}
