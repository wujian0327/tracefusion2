import java.lang.ref.*;
import java.util.*;
import java.util.function.*;

/** Recorder-lock protected identity index. Values must not reach their key.
 * Weak clearing is NOT retirement: only the independent phantom queue is proof.
 */
public final class WeakIdentityMap<K,V> extends AbstractMap<K,V> {
    static class Key<K> extends WeakReference<K> {
        final int hash;
        Key(K k,ReferenceQueue<K> queue){super(k,queue);hash=System.identityHashCode(k);}
        public int hashCode(){return hash;}
        public boolean equals(Object other){if(this==other)return true;if(!(other instanceof Key))return false;Object a=get();return a!=null&&a==((Key)other).get();}
    }
    static final class Node<K,V> extends Key<K> {
        V value;String ownerId;final PhantomReference<K> finalReference;boolean ready,weakSeen;
        Node(K key,V value,ReferenceQueue<K> weak,ReferenceQueue<K> terminal){super(key,weak);this.value=value;finalReference=new PhantomReference<>(key,terminal);}
    }
    final String name;final int limit;final Consumer<V> retired;final Predicate<V> allowed;
    final ReferenceQueue<K> weak=new ReferenceQueue<>(),terminal=new ReferenceQueue<>();
    final Map<Key<K>,Node<K,V>> nodes=new HashMap<>();
    final Map<PhantomReference<K>,Node<K,V>> proofs=new IdentityHashMap<>();
    final Map<Integer,List<Node<K,V>>> buckets=new HashMap<>();
    final Deque<Node<K,V>> ready=new ArrayDeque<>();
    long retiredCount,weakClearedCount;
    WeakIdentityMap(String name){this(name,100000,v->{},v->true);}
    WeakIdentityMap(String name,int limit,Consumer<V> retired,Predicate<V> allowed){this.name=name;this.limit=limit;this.retired=retired;this.allowed=allowed;}
    public void drain(int budget){synchronized(PlannedServiceAgent.Recorder.class){
        if(budget<0||budget>1024)throw new IllegalArgumentException("Retirement budget");
        for(int i=0;i<budget;i++){Node<K,V> n=(Node<K,V>)weak.poll();if(n==null)break;if(!n.weakSeen){n.weakSeen=true;weakClearedCount++;}}
        for(int i=0;i<budget;i++){PhantomReference<K> p=(PhantomReference<K>)terminal.poll();if(p==null)break;Node<K,V> n=proofs.get(p);if(n!=null&&!n.ready){n.ready=true;ready.addLast(n);}}
        int available=Math.min(budget,ready.size());
        for(int i=0;i<available;i++){Node<K,V> n=ready.removeFirst();if(!allowed.test(n.value)||n.ownerId!=null&&!PlannedServiceAgent.Recorder.canRetireIdentity(n.ownerId)){ready.addLast(n);continue;}
            retired.accept(n.value);nodes.remove(n);proofs.remove(n.finalReference);List<Node<K,V>> bucket=buckets.get(n.hash);bucket.remove(n);if(bucket.isEmpty())buckets.remove(n.hash);n.finalReference.clear();n.clear();retiredCount++;
        }
    }}
    Node<K,V> find(Object key){if(key==null)return null;Node<K,V> n=nodes.get(new Key<>((K)key,null));if(n!=null)return n;
        List<Node<K,V>> bucket=buckets.get(System.identityHashCode(key));if(bucket!=null)for(Node<K,V> pending:bucket)if(pending.get()==null&&!pending.ready)throw new IllegalStateException("Uncertified identity after weak clearing (resurrection/hash collision): "+name);return null;
    }
    public V get(Object key){synchronized(PlannedServiceAgent.Recorder.class){drain(16);Node<K,V> n=find(key);return n==null?null:n.value;}}
    public boolean containsKey(Object key){synchronized(PlannedServiceAgent.Recorder.class){drain(16);return find(key)!=null;}}
    public V put(K key,V value){synchronized(PlannedServiceAgent.Recorder.class){
        if(key==null||value==null)throw new IllegalArgumentException("Null weak identity state");drain(16);Node<K,V> existing=find(key);if(existing!=null){V old=existing.value;existing.value=value;return old;}
        if(nodes.size()>=limit)throw new IllegalStateException("Live/pending state bound: "+name);
        String ownerId=name.equals("IDS")?null:PlannedServiceAgent.Recorder.id(key);
        // id() can advance other queues: register no unindexed reference before it.
        Node<K,V> n=new Node<>(key,value,weak,terminal);n.ownerId=ownerId;nodes.put(n,n);proofs.put(n.finalReference,n);buckets.computeIfAbsent(n.hash,h->new ArrayList<>()).add(n);return null;
    }}
    public int size(){synchronized(PlannedServiceAgent.Recorder.class){drain(16);return nodes.size();}}
    public int pending(){synchronized(PlannedServiceAgent.Recorder.class){return ready.size();}}
    public Set<Map.Entry<K,V>> entrySet(){synchronized(PlannedServiceAgent.Recorder.class){drain(16);List<Map.Entry<K,V>> result=new ArrayList<>();for(Node<K,V> n:nodes.values()){K k=n.get();if(k!=null)result.add(new SimpleImmutableEntry<>(k,n.value));}return new AbstractSet<Map.Entry<K,V>>(){public int size(){return result.size();}public Iterator<Map.Entry<K,V>> iterator(){return Collections.unmodifiableList(result).iterator();}};}}
    public V remove(Object key){throw new UnsupportedOperationException("Identity state requires terminal queue proof: "+name);}
    public void clear(){throw new UnsupportedOperationException("Cannot clear live identity state: "+name);}
}
