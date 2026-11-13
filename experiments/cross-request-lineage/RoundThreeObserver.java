import lineage.web.Observer;

/** Boundary observations after the actual blocking HTTP I/O completes. */
public interface RoundThreeObserver extends Observer {
    default void wire(Object carrier, Object dto, byte[] bytes, String[] connection,
                      String parent, String direction, String phase, int status) throws Exception {
        json(dto,direction,phase,bytes);
    }
}
