package lineage.web;

import com.sun.net.httpserver.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import lineage.business.Cache;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;

/** Two ordinary HTTP+JSON services; one persistent worker and cache per JVM. */
public final class Server {
    public static final ObjectMapper JSON = new ObjectMapper();
    static final Cache CACHE = new Cache();
    static Observer observer;
    static String role, upstream;
    static Path audit;
    static byte[] read(InputStream in) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream(); byte[] b = new byte[4096];
        for (int n; (n = in.read(b)) >= 0;) out.write(b, 0, n);
        return out.toByteArray();
    }
    static void record(Map<String,Object> row) throws Exception {
        row.put("pid", java.lang.management.ManagementFactory.getRuntimeMXBean().getName());
        row.put("thread", Thread.currentThread().getId());
        Files.write(audit, (JSON.writeValueAsString(row)+"\n").getBytes(StandardCharsets.UTF_8), StandardOpenOption.CREATE, StandardOpenOption.APPEND);
    }
    static void handle(HttpExchange exchange) throws IOException {
        int status = 200; byte[] response; Map<String,Object> receipt = new LinkedHashMap<>();
        String parent = exchange.getRequestHeaders().getFirst("traceparent");
        receipt.put("traceparent", parent); receipt.put("path", exchange.getRequestURI().toString());
        try {
            byte[] input = read(exchange.getRequestBody());
            receipt.put("request_utf8", new String(input, StandardCharsets.UTF_8));
            if (exchange.getRequestURI().getPath().equals("/state")) {
                Map<String,Object> state = new LinkedHashMap<>(); state.put("key", CACHE.key);
                state.put("text", CACHE.cell == null ? null : CACHE.cell.text);
                response = JSON.writeValueAsBytes(state);
            } else {
                observer.enter(role, parent, exchange.getRequestURI().toString());
                Cache.Request body = JSON.readValue(input, Cache.Request.class);
                observer.json(body, "request", "read", input);
                Cache.Reply reply;
                if (role.equals("A")) {
                    HttpURLConnection connection = (HttpURLConnection)new URL(upstream+"/call").openConnection();
                    connection.setRequestMethod("POST"); connection.setDoOutput(true);
                    connection.setConnectTimeout(10000); connection.setReadTimeout(10000);
                    connection.setRequestProperty("Content-Type", "application/json");
                    String sent = observer.client(upstream+"/call", parent);
                    connection.setRequestProperty("traceparent", sent);
                    byte[] payload = JSON.writeValueAsBytes(body);
                    observer.json(body, "request", "write", payload);
                    connection.getOutputStream().write(payload);
                    status = connection.getResponseCode();
                    byte[] returned = read(status < 400 ? connection.getInputStream() : connection.getErrorStream());
                    receipt.put("rpc_traceparent", sent); receipt.put("rpc_request_utf8", new String(payload, StandardCharsets.UTF_8));
                    receipt.put("rpc_response_utf8", new String(returned, StandardCharsets.UTF_8));
                    receipt.put("rpc_status", status);
                    reply = JSON.readValue(returned, Cache.Reply.class);
                    observer.json(reply, "response", "read", returned);
                    observer.clientEnd(); connection.disconnect();
                } else if (System.getProperty("lineage.dispatch", "original").equals("split")) {
                    if (body.op == 1) CACHE.replace(body);
                    else if (body.op == 2) CACHE.overwrite(body);
                    else if (body.op == 3) CACHE.publish();
                    reply = CACHE.read(body);
                } else reply = CACHE.process(body);
                response = JSON.writeValueAsBytes(reply);
                observer.json(reply, "response", "write", response);
            }
        } catch (Throwable error) {
            status = 500; receipt.put("exception", error.toString());
            StringWriter stack = new StringWriter(); error.printStackTrace(new PrintWriter(stack));
            receipt.put("stack", stack.toString());
            response = ("{\"error\":"+JSON.writeValueAsString(error.toString())+"}").getBytes(StandardCharsets.UTF_8);
        } finally { try { observer.leave(); } catch (Exception e) { throw new IOException(e); } }
        receipt.put("status", status); receipt.put("response_utf8", new String(response, StandardCharsets.UTF_8));
        try { record(receipt); } catch (Exception e) { throw new IOException(e); }
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(status, response.length); exchange.getResponseBody().write(response); exchange.close();
    }
    public static void main(String[] args) throws Exception {
        role = args[0]; upstream = args[2]; audit = Paths.get(args[3]);
        String adapter = System.getProperty("lineage.observer");
        observer = adapter == null ? new Observer(){} : (Observer)Class.forName(adapter).newInstance();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", Integer.parseInt(args[1])), 0);
        server.createContext("/", Server::handle);
        server.setExecutor(Executors.newSingleThreadExecutor()); server.start();
        System.out.println("READY "+role+" "+server.getAddress().getPort());
    }
}
