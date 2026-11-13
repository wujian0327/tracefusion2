package lineage.web;

/** Boundary-only hooks. Implementations may observe; business code knows no tags. */
public interface Observer {
    default void enter(String role, String traceparent, String uri) throws Exception {}
    default void json(Object body, String direction, String phase, byte[] bytes) throws Exception {}
    default String client(String uri, String traceparent) throws Exception { return traceparent; }
    default void clientEnd() throws Exception {}
    default void leave() throws Exception {}
}
