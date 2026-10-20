import java.nio.file.*;
import java.lang.reflect.*;
import java.util.*;
import com.fasterxml.jackson.databind.*;
import org.springframework.web.client.RestTemplate;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.hateoas.Resource;

/** Independent original-library decoding probe. Run WITHOUT a TF agent. */
public class HateoasOracleProbe {
    public static void main(String[] args)throws Exception{
        Class content=Class.forName(args[0]);ObjectMapper mapper=null;
        // RestProxyTemplate.restTemplate() in the original JAR constructs this
        // default RestTemplate. AsyncGetService's separate HAL template is unused.
        for(HttpMessageConverter c:new RestTemplate().getMessageConverters())if(c instanceof MappingJackson2HttpMessageConverter){mapper=((MappingJackson2HttpMessageConverter)c).getObjectMapper();break;}
        if(mapper==null)throw new IllegalStateException("Original Jackson converter absent");
        byte[] raw=Files.readAllBytes(Paths.get(args[1]));Resource resource=(Resource)mapper.readValue(raw,mapper.getTypeFactory().constructParametricType(Resource.class,content));
        Object bean=resource.getContent();Map result=new LinkedHashMap();
        result.put("mapper_class",mapper.getClass().getName());result.put("content_type",bean.getClass().getName());
        Map fields=new LinkedHashMap();for(Field f:bean.getClass().getDeclaredFields()){if(Modifier.isStatic(f.getModifiers()))continue;f.setAccessible(true);fields.put(f.getName(),f.get(bean));}
        result.put("decoded_fields",fields);result.put("raw_json",mapper.readTree(raw));
        System.out.println(mapper.writeValueAsString(result));
    }
}
