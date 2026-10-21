import java.util.*;import java.util.concurrent.*;
/** Concurrent equal-but-distinct identities. Does not use provenance inference. */
public class RecorderIdentityStress {
    public static void main(String[]args)throws Exception{
        final int threads=8,rounds=2000;final CyclicBarrier gate=new CyclicBarrier(threads);ExecutorService pool=Executors.newFixedThreadPool(threads);List<Future<List<String>>> jobs=new ArrayList<>();
        for(int t=0;t<threads;t++)jobs.add(pool.submit(new Callable<List<String>>(){public List<String> call()throws Exception{List<String> ids=new ArrayList<>();for(int i=0;i<rounds;i++){Object object=new String("SAME");gate.await();String first=PlannedServiceAgent.Recorder.id(object);if(!first.equals(PlannedServiceAgent.Recorder.id(object)))throw new AssertionError("identity changed");ids.add(first);}return ids;}}));
        Set<String> unique=new HashSet<>();for(Future<List<String>> f:jobs)for(String id:f.get())if(!unique.add(id))throw new AssertionError("distinct objects share identity: "+id);pool.shutdown();System.out.println("unique="+unique.size()+" repeated_identity_stable=true");
    }
}
