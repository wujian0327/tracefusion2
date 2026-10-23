import java.lang.instrument.*;
import java.security.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;

/** Read-only class-definition witness; never invokes application methods. */
public final class NativeLibraryWitness implements ClassFileTransformer {
    static Path output;
    public static void premain(String argument, Instrumentation instrumentation) {
        output=Paths.get(System.getProperty("native.library.events"));
        instrumentation.addTransformer(new NativeLibraryWitness());
    }
    static String quote(String value) {
        return "\""+value.replace("\\","\\\\").replace("\"","\\\"").replace("\n","\\n").replace("\r","\\r")+"\"";
    }
    public byte[] transform(ClassLoader loader,String name,Class<?> prior,ProtectionDomain domain,byte[] bytes) {
        if(!"com/fasterxml/jackson/databind/ObjectMapper".equals(name))return null;
        try {
            StringBuilder hash=new StringBuilder();
            for(byte b:MessageDigest.getInstance("SHA-256").digest(bytes))hash.append(String.format("%02x",b&255));
            String source=domain==null||domain.getCodeSource()==null||domain.getCodeSource().getLocation()==null?"":domain.getCodeSource().getLocation().toExternalForm();
            String identity=loader==null?"bootstrap":loader.getClass().getName()+"@"+Integer.toHexString(System.identityHashCode(loader));
            String row="{\"kind\":\"native-library-definition\",\"class\":"+quote(name)+",\"sha256\":"+quote(hash.toString())+",\"loader\":"+quote(identity)+",\"source\":"+quote(source)+"}\n";
            synchronized(NativeLibraryWitness.class){Files.write(output,row.getBytes(StandardCharsets.UTF_8),StandardOpenOption.CREATE,StandardOpenOption.APPEND);}
        } catch(Exception error) { throw new IllegalStateException("Native library witness failed",error); }
        return null;
    }
}
