import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.lang.reflect.Proxy;
import javax.naming.*;
import javax.naming.spi.InitialContextFactory;
import org.apache.logging.log4j.*;

/** Controlled application fixture, not a claimed vulnerability in Sock Shop.
 * No taint labels or provenance instrumentation are embedded in this application.
 */
public final class SecurityLeakLab {
    static final ObjectMapper JSON = new ObjectMapper();
    public static final class Record {
        public String businessId, secret, publicValue;
    }
    public static final class Box { public String value; }
    public static final class Wire {
        public static void send(HttpExchange exchange, Record record, String message, byte[] body) throws IOException {
            exchange.getResponseHeaders().set("X-TF2-Message", message);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream stream = exchange.getResponseBody()) { stream.write(body); }
        }
    }
    public static final class Flow {
        public static void run(Record record, String mode, String message, byte[] body, String requestId) {
            String selected = record.publicValue;
            if (mode.equals("leak")) selected = record.secret;
            if (mode.equals("overwrite")) { selected = record.secret; selected = "REDACTED"; }
            if (mode.equals("field-copy")) {
                Box box = new Box(); box.value = record.secret; selected = box.value;
            }
            if (mode.equals("field-overwrite")) {
                Box box = new Box(); box.value = record.secret;
                box.value = record.publicValue; selected = box.value;
            }
            if (mode.equals("read-unused")) { String unused = record.secret; selected = record.publicValue; }
            if (mode.equals("constant")) selected = "PUBLIC";
            if (mode.equals("unknown-transform")) selected = opaque(record.secret);
            Sink.write(selected);
        }
        static String opaque(String value) { return new String(value); }
    }
    public static final class Sink {
        static final Logger LOG = LogManager.getLogger("security-leak-lab");
        static final CyclicBarrier CONCURRENT = new CyclicBarrier(12);
        public static void write(String value) {
            // Fixture scheduling only: force all twelve business frames to overlap.
            if (ThreadContext.get("request").startsWith("concurrent-")) {
                try { CONCURRENT.await(15,TimeUnit.SECONDS); }
                catch (Exception error) { throw new IllegalStateException(error); }
            }
            LOG.info(value);
        }
    }
    /** Inert local provider: confirms an actual JNDI call, never loads code or contacts a server. */
    public static final class LocalContextFactory implements InitialContextFactory {
        public Context getInitialContext(Hashtable<?,?> environment) {
            return (Context) Proxy.newProxyInstance(getClass().getClassLoader(), new Class<?>[]{Context.class}, (proxy,method,args) -> {
                if (method.getName().equals("lookup")) {
                    Map<String,Object> row = new LinkedHashMap<>();
                    row.put("request_id", ThreadContext.get("request")); row.put("name",String.valueOf(args[0]));
                    row.put("result","LOCAL_LOOKUP_MARKER");
                    synchronized (LocalContextFactory.class) {
                        Files.write(Paths.get(System.getProperty("lab.callbacks")),
                            (JSON.writeValueAsString(row)+"\n").getBytes(StandardCharsets.UTF_8),
                            StandardOpenOption.CREATE, StandardOpenOption.APPEND);
                    }
                    return "LOCAL_LOOKUP_MARKER";
                }
                if (method.getName().equals("close")) return null;
                if (method.getName().equals("getEnvironment")) return new Hashtable<>();
                if (method.getName().equals("toString")) return "InertLocalContext";
                throw new OperationNotSupportedException(method.getName());
            });
        }
    }
    static Map<String,String> query(HttpExchange exchange) throws Exception {
        Map<String,String> result = new HashMap<>();
        String raw = exchange.getRequestURI().getRawQuery();
        if (raw != null) for (String item : raw.split("&")) {
            String[] pair = item.split("=",2);
            result.put(URLDecoder.decode(pair[0],"UTF-8"),pair.length==2?URLDecoder.decode(pair[1],"UTF-8"):"");
        }
        return result;
    }
    static byte[] read(InputStream input) throws IOException {
        ByteArrayOutputStream result = new ByteArrayOutputStream(); byte[] buffer = new byte[4096]; int n;
        while ((n=input.read(buffer))!=-1) result.write(buffer,0,n);
        return result.toByteArray();
    }
    public static void main(String[] args) throws Exception {
        String role=args[0]; int port=Integer.parseInt(args[1]);
        HttpServer server=HttpServer.create(new InetSocketAddress("127.0.0.1",port),0);
        server.setExecutor(Executors.newFixedThreadPool(16));
        server.createContext("/health",exchange -> {
            byte[] bytes="ok".getBytes(StandardCharsets.UTF_8); exchange.sendResponseHeaders(200,bytes.length);
            exchange.getResponseBody().write(bytes); exchange.close();
        });
        server.createContext(role.equals("source")?"/record":"/run",exchange -> {
            try {
                Map<String,String> q=query(exchange);
                if (role.equals("source")) {
                    Record record=new Record(); record.businessId="same-business-id";
                    record.secret=q.get("secret"); record.publicValue=q.get("publicValue");
                    if (q.containsKey("delay")) Thread.sleep(Integer.parseInt(q.get("delay")));
                    String message=UUID.randomUUID().toString();
                    byte[] bytes=JSON.writeValueAsBytes(record);
                    Wire.send(exchange,record,message,bytes);
                } else {
                    String url="http://127.0.0.1:"+args[2]+"/record?"+exchange.getRequestURI().getRawQuery();
                    HttpURLConnection connection=(HttpURLConnection)new URL(url).openConnection();
                    connection.setConnectTimeout(10000);connection.setReadTimeout(10000);
                    byte[] body;
                    try (InputStream input=connection.getInputStream()) { body=read(input); }
                    String message=connection.getHeaderField("X-TF2-Message");connection.disconnect();
                    Record record=JSON.readValue(body,Record.class);
                    ThreadContext.put("request",q.get("request"));
                    try { Flow.run(record,q.get("mode"),message,body,q.get("request")); }
                    finally { ThreadContext.clearMap(); }
                    byte[] bytes="{\"ok\":true}".getBytes(StandardCharsets.UTF_8);
                    exchange.sendResponseHeaders(200,bytes.length);exchange.getResponseBody().write(bytes);
                }
            } catch (Throwable error) {
                error.printStackTrace();byte[] bytes=error.toString().getBytes(StandardCharsets.UTF_8);
                try { exchange.sendResponseHeaders(500,bytes.length);exchange.getResponseBody().write(bytes); } catch (IOException ignored) { }
            } finally { exchange.close(); }
        });
        server.start();System.out.println("READY "+role+" "+server.getAddress().getPort());
    }
}
