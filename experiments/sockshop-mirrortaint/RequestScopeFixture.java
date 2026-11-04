import java.io.*;
import java.lang.reflect.*;
import java.util.*;
import javax.servlet.*;
import javax.servlet.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.context.request.*;
import org.springframework.web.context.request.async.StandardServletAsyncWebRequest;
import org.springframework.web.method.support.*;
import org.springframework.web.servlet.mvc.method.annotation.ServletInvocableHandlerMethod;
import org.springframework.http.server.ServletServerHttpResponse;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Actual synchronous MVC dispatch/converter; one worker, independent messages. */
@RestController
public class RequestScopeFixture {
 public static class DTO {public String text="same";public String getText(){return text;}}
 public static class Wrap extends HashMap<String,Object>{}
 public static class UnknownSet extends HashSet<String>{static int iterations;public Iterator<String> iterator(){iterations++;return super.iterator();}}
 public static class UnverifiedWeb extends StandardServletAsyncWebRequest{public UnverifiedWeb(HttpServletRequest r,HttpServletResponse s){super(r,s);}}
 static final IllegalArgumentException ORIGINAL=new IllegalArgumentException("original");
 static int finalized;static String scenario;
 @GetMapping("/query") public Wrap query(DTO input){return body(input);}
 static Wrap body(DTO input){try{if(scenario.equals("exception"))throw ORIGINAL;Wrap w=new Wrap();w.put("data",input);if(scenario.equals("formal-bad"))w.put("bad",bad());return w;}finally{finalized++;}}
 @GetMapping("/prepare") public Wrap prepare(){Wrap w=new Wrap();w.put("unrelated",bad());return w;}
 static UnknownSet bad(){UnknownSet s=new UnknownSet();s.add("same");s.add("other");return s;}
 static Object defaultValue(Class<?> c){if(!c.isPrimitive())return null;if(c==boolean.class)return false;if(c==int.class)return 0;if(c==long.class)return 0L;return null;}
 public static void main(String[] args)throws Exception{
  boolean observing=Boolean.getBoolean("fixture.observe");String variant=args.length==0?"normal":args[0];RequestScopeFixture bean=new RequestScopeFixture();ObjectMapper json=new ObjectMapper();List<Map> cases=new ArrayList<>();int serial=0;
  for(String name:variant.equals("normal")?new String[]{"prepare","query","prepare","exception","query"}:new String[]{variant,"query"}){
   scenario=name;boolean prep=name.equals("prepare")||name.equals("parented")||name.equals("plain-prep");Map<String,Object> attrs=new HashMap<>();ByteArrayOutputStream bytes=new ByteArrayOutputStream();String parent="00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-"+String.format("%016x",++serial)+"-01";
   HttpServletRequest req=(HttpServletRequest)Proxy.newProxyInstance(RequestScopeFixture.class.getClassLoader(),new Class[]{HttpServletRequest.class},(p,m,a)->{
    switch(m.getName()){case "getAttribute":return attrs.get(a[0]);case "setAttribute":attrs.put((String)a[0],a[1]);return null;case "removeAttribute":attrs.remove(a[0]);return null;case "getHeaders":return Collections.enumeration(name.equals("parented")&&a[0].equals("traceparent")?Arrays.asList(parent):Collections.emptyList());case "getRequestURI":return prep?"/prepare":"/query";case "getMethod":return "GET";case "getAttributeNames":return Collections.enumeration(attrs.keySet());default:return defaultValue(m.getReturnType());}
   });
   ServletOutputStream output=new ServletOutputStream(){public void write(int v){bytes.write(v);}public boolean isReady(){return true;}public void setWriteListener(WriteListener l){}};
   HttpServletResponse resp=(HttpServletResponse)Proxy.newProxyInstance(RequestScopeFixture.class.getClassLoader(),new Class[]{HttpServletResponse.class},(p,m,a)->m.getName().equals("getOutputStream")?output:defaultValue(m.getReturnType()));
   ServletWebRequest web=name.startsWith("plain")?new ServletWebRequest(req,resp):name.equals("unverified")?new UnverifiedWeb(req,resp):new StandardServletAsyncWebRequest(req,resp);RequestContextHolder.setRequestAttributes(web);
   Method selected=RequestScopeFixture.class.getMethod(prep?"prepare":"query",prep?new Class[0]:new Class[]{DTO.class});ServletInvocableHandlerMethod handler=new ServletInvocableHandlerMethod(bean,selected);
   HandlerMethodReturnValueHandlerComposite handlers=new HandlerMethodReturnValueHandlerComposite();handlers.addHandler(new HandlerMethodReturnValueHandler(){public boolean supportsReturnType(org.springframework.core.MethodParameter p){return true;}public void handleReturnValue(Object body,org.springframework.core.MethodParameter p,ModelAndViewContainer c,NativeWebRequest w)throws Exception{new MappingJackson2HttpMessageConverter(json).write(body,null,new ServletServerHttpResponse((HttpServletResponse)w.getNativeResponse()));}});handler.setHandlerMethodReturnValueHandlers(handlers);
   Map row=new LinkedHashMap();row.put("case",name);int before=UnknownSet.iterations;
   try{handler.invokeAndHandle(web,new ModelAndViewContainer(),prep?new Object[0]:new Object[]{new DTO()});row.put("normal",true);}catch(IllegalArgumentException e){if(e!=ORIGINAL)throw e;row.put("same_original_exception",true);}
   finally{RequestContextHolder.resetRequestAttributes();}
   row.put("output",bytes.toString("UTF-8"));row.put("set_iterations",UnknownSet.iterations-before);if(observing&&(!RequestScopeHooks.ACTIVE.get().isEmpty()||!CollectionServiceHooks.CALLS.get().isEmpty()))throw new AssertionError("scope/call leaked");cases.add(row);
  }
  Map result=new LinkedHashMap();result.put("cases",cases);result.put("finally",finalized);System.out.println(json.writeValueAsString(result));
 }
}
