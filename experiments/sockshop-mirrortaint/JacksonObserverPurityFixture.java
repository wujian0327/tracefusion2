import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.core.Version;

/** Recording loader metadata must not dispatch to a user mapper override. */
public final class JacksonObserverPurityFixture {
    static int calls;
    static class CustomMapper extends ObjectMapper {
        public Version version(){calls++;return super.version();}
    }
    public static void main(String[] args)throws Exception{
        CustomMapper mapper=new CustomMapper();BusinessJackson.observe(mapper);
        if(calls!=0)throw new AssertionError("Observer invoked user mapper.version override "+calls+" times");
        System.out.println("{\"all_passed\":true,\"user_override_calls\":0}");
    }
}
