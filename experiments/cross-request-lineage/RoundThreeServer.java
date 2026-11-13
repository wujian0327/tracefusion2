import com.sun.net.httpserver.*;
import lineage.business.Cache;
import lineage.web.Server;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.Executors;

/** Ordinary HTTP/JSON adapter; the original Cache bytecode is unchanged.
 * One fresh close-delimited TCP connection per RPC makes actual exchange
 * identity observable without reflection into JDK client implementation state.
 */
public final class RoundThreeServer {
    static final Cache CACHE=new Cache();
    static RoundThreeObserver observer; static String role; static int peer; static Path audit;
    static byte[] read(InputStream in)throws IOException { ByteArrayOutputStream b=new ByteArrayOutputStream();byte[] x=new byte[4096];for(int n;(n=in.read(x))>=0;)b.write(x,0,n);return b.toByteArray(); }
    static String[] connection(InetSocketAddress client,InetSocketAddress server){return new String[]{client.getAddress().getHostAddress(),""+client.getPort(),server.getAddress().getHostAddress(),""+server.getPort()};}
    static String line(InputStream in)throws IOException {ByteArrayOutputStream b=new ByteArrayOutputStream();for(int x;(x=in.read())!=-1;){if(x==10)return new String(b.toByteArray(),StandardCharsets.ISO_8859_1).replace("\r","");b.write(x);}throw new EOFException("HTTP header incomplete");}
    static void handle(HttpExchange exchange)throws IOException {
        Map<String,Object> record=new LinkedHashMap<>();int status=200;byte[] output;boolean active=false, sentResponse=false;
        String parent=exchange.getRequestHeaders().getFirst("traceparent");String path=exchange.getRequestURI().getPath();
        record.put("path",path);record.put("traceparent",parent);record.put("pid",java.lang.management.ManagementFactory.getRuntimeMXBean().getName());record.put("thread",Thread.currentThread().getId());
        String[] serverConnection=connection(exchange.getRemoteAddress(),exchange.getLocalAddress());
        try {
            byte[] input=read(exchange.getRequestBody());record.put("request_utf8",new String(input,StandardCharsets.UTF_8));
            if(path.equals("/state")){Map<String,Object>s=new LinkedHashMap<>();s.put("key",CACHE.key);s.put("text",CACHE.cell==null?null:CACHE.cell.text);output=Server.JSON.writeValueAsBytes(s);}
            else {
                observer.enter(role,parent,path);active=true;Cache.Request request=Server.JSON.readValue(input,Cache.Request.class);
                observer.wire(exchange,request,input,serverConnection,parent,"request","read",0);
                Cache.Reply reply;
                if(role.equals("A")){
                    String sent=observer.client("http://127.0.0.1:"+peer+"/call",parent);
                    try(Socket socket=new Socket("127.0.0.1",peer)){
                        socket.setSoTimeout(10000);String[] clientConnection=connection((InetSocketAddress)socket.getLocalSocketAddress(),(InetSocketAddress)socket.getRemoteSocketAddress());
                        byte[] payload=Server.JSON.writeValueAsBytes(request);OutputStream out=socket.getOutputStream();
                        String headers="POST /call HTTP/1.1\r\nHost: 127.0.0.1:"+peer+"\r\nContent-Type: application/json\r\nConnection: close\r\ntraceparent: "+sent+"\r\nContent-Length: "+payload.length+"\r\n\r\n";
                        out.write(headers.getBytes(StandardCharsets.ISO_8859_1));out.write(payload);out.flush();
                        observer.wire(socket,request,payload,clientConnection,sent,"request","write",0);
                        InputStream in=socket.getInputStream();String statusLine=line(in);status=Integer.parseInt(statusLine.split(" ")[1]);Map<String,String> hs=new LinkedHashMap<>();
                        for(String s;!(s=line(in)).isEmpty();){int colon=s.indexOf(':');hs.put(s.substring(0,colon).toLowerCase(Locale.ROOT),s.substring(colon+1).trim());}
                        if(hs.containsKey("transfer-encoding"))throw new IOException("Chunked RPC is outside this adapter");
                        int length=Integer.parseInt(hs.get("content-length"));byte[] returned=new byte[length];for(int pos=0;pos<length;){int n=in.read(returned,pos,length-pos);if(n<0)throw new EOFException("HTTP body incomplete");pos+=n;}
                        reply=Server.JSON.readValue(returned,Cache.Reply.class);observer.wire(socket,reply,returned,clientConnection,sent,"response","read",status);
                        record.put("rpc_traceparent",sent);record.put("rpc_request_utf8",new String(payload,StandardCharsets.UTF_8));record.put("rpc_response_utf8",new String(returned,StandardCharsets.UTF_8));record.put("rpc_status",status);record.put("rpc_connection",clientConnection);
                    }
                    observer.clientEnd();
                }else{
                    if(request.op==1)CACHE.replace(request);else if(request.op==2)CACHE.overwrite(request);else if(request.op==3)CACHE.publish();
                    reply=CACHE.read(request);
                }
                output=Server.JSON.writeValueAsBytes(reply);
                exchange.getResponseHeaders().set("Content-Type","application/json");exchange.sendResponseHeaders(status,output.length);exchange.getResponseBody().write(output);exchange.getResponseBody().flush();
                observer.wire(exchange,reply,output,serverConnection,parent,"response","write",status);
                record.put("response_utf8",new String(output,StandardCharsets.UTF_8));record.put("status",status);record.put("connection",serverConnection);
                sentResponse=true;return;
            }
        }catch(Throwable e){status=500;record.put("exception",e.toString());output=Server.JSON.writeValueAsBytes(Collections.singletonMap("error",e.toString()));}
        finally{
            try{if(active)observer.leave();record.put("status",status);Files.write(audit,(Server.JSON.writeValueAsString(record)+"\n").getBytes(StandardCharsets.UTF_8),StandardOpenOption.CREATE,StandardOpenOption.APPEND);}catch(Exception e){throw new IOException(e);}finally{if(sentResponse)exchange.close();}
        }
        exchange.getResponseHeaders().set("Content-Type","application/json");exchange.sendResponseHeaders(status,output.length);exchange.getResponseBody().write(output);exchange.close();
    }
    public static void main(String[]args)throws Exception {
        role=args[0];peer=Integer.parseInt(args[2]);audit=Paths.get(args[3]);String adapter=System.getProperty("lineage.observer");observer=adapter==null?new RoundThreeObserver(){}:(RoundThreeObserver)Class.forName(adapter).newInstance();
        HttpServer server=HttpServer.create(new InetSocketAddress("127.0.0.1",Integer.parseInt(args[1])),0);server.createContext("/",RoundThreeServer::handle);server.setExecutor(Executors.newSingleThreadExecutor());server.start();System.out.println("READY "+role);
    }
}
