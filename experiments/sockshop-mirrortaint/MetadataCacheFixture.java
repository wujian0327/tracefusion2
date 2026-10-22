import java.io.*;
import java.security.*;
import java.util.*;
import java.util.concurrent.*;
import org.objectweb.asm.*;

/** Independent byte digests, concurrent access and distinct defining loaders. */
public final class MetadataCacheFixture {
    static String digest(byte[] bytes)throws Exception{byte[] hash=MessageDigest.getInstance("SHA-256").digest(bytes);StringBuilder text=new StringBuilder();for(byte b:hash)text.append(String.format("%02x",b&255));return text.toString();}
    static byte[] read(InputStream in)throws Exception{try(InputStream source=in;ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] buffer=new byte[4096];int n;while((n=source.read(buffer))!=-1)out.write(buffer,0,n);return out.toByteArray();}}
    static void require(boolean condition,String detail){if(!condition)throw new AssertionError(detail);}
    static final class LibraryLoader extends ClassLoader {
        final byte[] bytes;
        LibraryLoader(int value){super(null);ClassWriter w=new ClassWriter(0);w.visit(Opcodes.V1_8,Opcodes.ACC_PUBLIC,"MetadataCacheTarget",null,"java/lang/Object",null);w.visitField(Opcodes.ACC_PUBLIC|Opcodes.ACC_STATIC|Opcodes.ACC_FINAL,"value","I",null,value).visitEnd();w.visitEnd();bytes=w.toByteArray();}
        protected Class<?> findClass(String name)throws ClassNotFoundException{if(!name.equals("MetadataCacheTarget"))throw new ClassNotFoundException(name);return defineClass(name,bytes,0,bytes.length);}
        public InputStream getResourceAsStream(String name){return name.equals("MetadataCacheTarget.class")?new ByteArrayInputStream(bytes):super.getResourceAsStream(name);}
    }
    static final class Sink extends Writer {
        final StringBuilder data=new StringBuilder();int flushes;
        public void write(char[] chars,int offset,int length){data.append(chars,offset,length);}
        public void flush(){flushes++;}public void close(){flush();}
    }
    public static void main(String[] args)throws Exception{
        Set<String> names=new TreeSet<>(Arrays.asList(JdkContractProbe.CLASSES));names.addAll(Arrays.asList("java/util/Date","java/util/Calendar","java/util/TimeZone","java/util/concurrent/FutureTask","java/net/URI","java/util/Formatter"));Map<String,String> expected=new TreeMap<>();
        for(String name:names)expected.put(name,digest(read(ClassLoader.getSystemResourceAsStream(name+".class"))));
        ExecutorService pool=Executors.newFixedThreadPool(8);List<Future<?>> jobs=new ArrayList<>();
        for(int thread=0;thread<8;thread++)jobs.add(pool.submit(()->{try{for(int round=0;round<100;round++)for(String name:names)require(expected.get(name).equals(JdkContractProbe.hash(name)),"Digest changed: "+name);}catch(Exception e){throw new RuntimeException(e);}}));
        try{for(Future<?> job:jobs)job.get();}finally{pool.shutdownNow();}
        require(JdkContractProbe.HASHES.size()==names.size(),"Cache must contain one entry per bootstrap definition");
        Map<String,String> returned=JdkContractProbe.selected(names.toArray(new String[0]));returned.clear();require(expected.equals(JdkContractProbe.selected(names.toArray(new String[0]))),"Caller modified cached state");
        try{JdkContractProbe.hash("MetadataCacheFixture");throw new AssertionError("Application class accepted as bootstrap");}catch(ClassNotFoundException expectedFailure){}
        Map cfg=new HashMap();cfg.put("class_sha256",Collections.singletonMap("MetadataCacheTarget","not-an-expected-answer"));Map kernel=new HashMap();kernel.put("request_entity_contracts",cfg);Map plan=new HashMap();plan.put("profile","execution-dependency");plan.put("execution_kernel",kernel);PlannedServiceAgent.plan=plan;
        ClassLoader original=Thread.currentThread().getContextClassLoader();LibraryLoader first=new LibraryLoader(1),second=new LibraryLoader(2);Map a,b;
        try{Thread.currentThread().setContextClassLoader(first);a=RequestEntityHooks.hashes();require(a==RequestEntityHooks.hashes(),"Missing cache insertion");require(a.get("MetadataCacheTarget").equals(digest(first.bytes)),"Expected configuration substituted for actual digest");
            try{a.put("MetadataCacheTarget","forged");throw new AssertionError("Mutable shared witness");}catch(UnsupportedOperationException expectedFailure){}
            Thread.currentThread().setContextClassLoader(second);b=RequestEntityHooks.hashes();require(!a.equals(b),"Different class definitions conflated");require(b.get("MetadataCacheTarget").equals(digest(second.bytes)),"Wrong loader bytes");
            Thread.currentThread().setContextClassLoader(first);require(RequestEntityHooks.hashes()==a,"Loader cache overwritten");
        }finally{Thread.currentThread().setContextClassLoader(original);}
        Sink sink=new Sink();PlannedServiceAgent.Recorder.output=new BufferedWriter(sink);PlannedServiceAgent.Recorder.seq=0;PlannedServiceAgent.Recorder.emit("start",new LinkedHashMap<>());
        for(int i=0;i<5000;i++){Map<String,Object> row=new LinkedHashMap<>();row.put("index",i);PlannedServiceAgent.Recorder.emit("probe",row);}
        require(sink.flushes==1,"Per-event flush remains enabled");require(sink.data.length()>8192,"Buffer did not drain at its bound");PlannedServiceAgent.Recorder.emit("metrics",new LinkedHashMap<>());require(sink.flushes==2,"Footer did not flush pending records");String[] lines=sink.data.toString().split("\n");require(lines.length==5002,"Buffered event loss/duplication");
        com.fasterxml.jackson.databind.ObjectMapper parser=new com.fasterxml.jackson.databind.ObjectMapper();
        for(int i=0;i<lines.length;i++){com.fasterxml.jackson.databind.JsonNode row=parser.readTree(lines[i]);require(row.get("seq").asInt()==i+1,"Event reordering");if(i>0&&i<5001)require(row.get("index").asInt()==i-1,"Changed event payload");}
        PlannedServiceAgent.Recorder.output=new BufferedWriter(new Writer(){public void write(char[] c,int o,int n)throws IOException{throw new IOException("injected-write-failure");}public void flush(){}public void close(){}});
        try{PlannedServiceAgent.Recorder.emit("metrics",new LinkedHashMap<>());throw new AssertionError("Write failure hidden");}catch(IllegalStateException expectedFailure){require(expectedFailure.getCause()instanceof IOException,"Wrong write error");}
        System.out.println("{\"all_passed\":true,\"concurrent_digest_checks\":"+(8*100*names.size())+",\"bootstrap_definitions\":"+names.size()+",\"distinct_library_loaders\":2,\"expected_digest_substitution\":false,\"mutable_witness_rejected\":true,\"buffered_events_in_order\":5002,\"explicit_flushes\":2,\"write_failure_propagates\":true}");
    }
}
