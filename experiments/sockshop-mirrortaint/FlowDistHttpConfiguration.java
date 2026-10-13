import disttaint.FlowDistHttpClock;
import java.io.IOException;
import java.net.URI;
import javax.servlet.*;
import javax.servlet.http.HttpServletRequest;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.MethodParameter;
import org.springframework.http.*;
import org.springframework.http.client.*;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.server.*;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.servlet.mvc.method.annotation.ResponseBodyAdvice;
import org.springframework.web.method.HandlerMethod;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.handler.HandlerInterceptorAdapter;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurerAdapter;
import javax.servlet.http.HttpServletResponse;
import disttaint.OTMonitor;

/** HTTP boundary adapter for the selected Java shipping endpoint only. */
@Configuration
public class FlowDistHttpConfiguration extends WebMvcConfigurerAdapter {
    @Override public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new HandlerInterceptorAdapter() {
            @Override public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
                if (handler instanceof HandlerMethod) {
                    HandlerMethod method = (HandlerMethod)handler;
                    if (method.getBeanType().getName().equals("works.weave.socks.shipping.controllers.ShippingController")
                        && method.getMethod().getName().equals("postShipping"))
                        OTMonitor.enter("<works.weave.socks.shipping.controllers.ShippingController: works.weave.socks.shipping.entities.Shipment postShipping(works.weave.socks.shipping.entities.Shipment)>");
                }
                return true;
            }
        }).addPathPatterns("/shipping");
    }
    @Bean public FilterRegistrationBean flowDistReceiveFilter() {
        FilterRegistrationBean bean = new FilterRegistrationBean();
        bean.setFilter(new Filter() {
            public void init(FilterConfig config) {}
            public void destroy() {}
            public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain)
                throws IOException, ServletException {
                HttpServletRequest http = (HttpServletRequest)request;
                FlowDistHttpClock.receive(http.getHeader(FlowDistHttpClock.HEADER));
                chain.doFilter(request, response);
            }
        });
        bean.addUrlPatterns("/shipping");
        bean.setOrder(Integer.MIN_VALUE);
        return bean;
    }
    @Bean public ShippingReplyClock shippingReplyClock() { return new ShippingReplyClock(); }
    @ControllerAdvice
    public static class ShippingReplyClock implements ResponseBodyAdvice<Object> {
        public boolean supports(MethodParameter method, Class<? extends HttpMessageConverter<?>> converter) {
            return method.getDeclaringClass().getName().equals("works.weave.socks.shipping.controllers.ShippingController");
        }
        public Object beforeBodyWrite(Object body, MethodParameter method, MediaType media,
            Class<? extends HttpMessageConverter<?>> converter, ServerHttpRequest request, ServerHttpResponse response) {
            if (request.getHeaders().getFirst(FlowDistHttpClock.HEADER) != null)
                response.getHeaders().set(FlowDistHttpClock.HEADER, FlowDistHttpClock.send());
            return body;
        }
    }
    public static ClientHttpRequestInterceptor client(final URI peer) {
        return new ClientHttpRequestInterceptor() {
            public ClientHttpResponse intercept(HttpRequest request, byte[] body, ClientHttpRequestExecution execution)
                throws IOException {
                // Explicit peer selection: no metadata added to payment/Go/DB/MQ traffic.
                if (!request.getURI().equals(peer)) return execution.execute(request, body);
                request.getHeaders().set(FlowDistHttpClock.HEADER, FlowDistHttpClock.send());
                ClientHttpResponse response = execution.execute(request, body);
                FlowDistHttpClock.receive(response.getHeaders().getFirst(FlowDistHttpClock.HEADER));
                return response;
            }
        };
    }
}
