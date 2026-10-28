/** Independent check of fixture password versus original BCrypt saved value.
 * No TF/MT classes, no instrumentation, no credential generation or signing. */
import java.io.*;
import org.springframework.security.crypto.bcrypt.BCrypt;
public final class PortabilityPasswordOracle {
 public static void main(String[] args)throws Exception {
  BufferedReader r=new BufferedReader(new InputStreamReader(System.in,"UTF-8"));String l;
  while((l=r.readLine())!=null){String[] v=l.split("\t",-1);if(v.length!=2)throw new IllegalArgumentException("Two fixture fields required");System.out.println(BCrypt.checkpw(v[0],v[1]));}
 }
}
