import disttaint.OTMonitor;
import java.lang.reflect.Field;
import java.net.URI;
import java.util.Collections;
import java.util.concurrent.TimeUnit;
import org.springframework.boot.SpringApplication;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.web.client.RestTemplate;
import org.springframework.http.ResponseEntity;
import works.weave.socks.orders.config.RestProxyTemplate;
import works.weave.socks.orders.services.AsyncGetService;
import works.weave.socks.orders.entities.Shipment;
import works.weave.socks.shipping.ShippingServiceApplication;

/** HTTP compatibility probe, not a full Orders.newOrder deployment or oracle.
 * Original service/controller bytecode is untouched. Explicit method hooks
 * exercise the original monitor; full FlowDist static instrumentation is pending. */
public final class FlowDistSockShopHttpProbe {
    public static void main(String[] args) throws Exception {
        OTMonitor.initialize();
        OTMonitor.enter("<FlowDistSockShopHttpProbe: void main(java.lang.String[])>");
        if (args[0].equals("shipping")) {
            OTMonitor.enter("<FlowDistSockShopHttpProbe: void shippingEntry()>");
            SpringApplication.run(new Object[]{ShippingServiceApplication.class, FlowDistHttpConfiguration.class},
                new String[]{"--server.port=18080", "--spring.zipkin.enabled=false", "--spring.sleuth.enabled=false",
                    "--spring.rabbitmq.host=127.0.0.1", "--spring.rabbitmq.port=1"});
            return;
        }
        URI peer = URI.create("http://127.0.0.1:18080/shipping");
        Shipment control = new Shipment("plain-http-id", "plain-http-name");
        ResponseEntity<Shipment> plain = new RestTemplate().postForEntity(peer, control, Shipment.class);
        if (plain.getStatusCodeValue() != 201 || plain.getHeaders().containsKey(disttaint.FlowDistHttpClock.HEADER)
            || !control.getId().equals(plain.getBody().getId()) || !control.getName().equals(plain.getBody().getName()))
            throw new IllegalStateException("Plain HTTP compatibility changed");
        System.out.println("FLOWDIST_PLAIN_HTTP_CONTROL_PASSED");
        RestTemplate template = new RestTemplate();
        template.setInterceptors(Collections.singletonList(FlowDistHttpConfiguration.client(peer)));
        RestProxyTemplate proxy = new RestProxyTemplate();
        Field field = RestProxyTemplate.class.getDeclaredField("restTemplate");
        field.setAccessible(true); field.set(proxy, template);
        AsyncGetService service = new AsyncGetService(proxy);
        // Same-value fields exercise identity-independent transport; verify both returned fields.
        Shipment input = new Shipment("flowdist-http-fixture", "flowdist-http-fixture");
        OTMonitor.enter("<works.weave.socks.orders.services.AsyncGetService: java.util.concurrent.Future postResource(java.net.URI,java.lang.Object,org.springframework.core.ParameterizedTypeReference)>");
        Shipment output = service.postResource(peer, input, new ParameterizedTypeReference<Shipment>(){}).get(20, TimeUnit.SECONDS);
        OTMonitor.returnInto("<FlowDistSockShopHttpProbe: void main(java.lang.String[])>", "postResource");
        if (!input.getId().equals(output.getId()) || !input.getName().equals(output.getName()))
            throw new IllegalStateException("Original HTTP business payload changed");
        System.out.println("FLOWDIST_HTTP_BUSINESS_PASSED");
        // Original initialize() registered a shutdown hook; flush exactly once.
    }
}
