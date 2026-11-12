import java.util.*;

/** String-only ownership index; bounded cleanup after owner phantom proof. */
public final class OwnerVersions extends AbstractMap<String,Integer> {
    final Map<String,Integer> data=new HashMap<>();
    final Map<String,Set<String>> owners=new HashMap<>();
    final Deque<Iterator<String>> cleanup=new ArrayDeque<>();long retiredEntries;int pending;
    public Integer put(String key,Integer version){synchronized(PlannedServiceAgent.Recorder.class){
        drain(64);int colon=key.indexOf(':');if(colon<=0||version==null||version<0)throw new IllegalArgumentException("Version owner/value absent");
        if(!data.containsKey(key)&&data.size()>=1000000)throw new IllegalStateException("Live/pending field version bound");
        owners.computeIfAbsent(key.substring(0,colon),id->new HashSet<>()).add(key);return data.put(key,version);
    }}
    public Integer get(Object key){synchronized(PlannedServiceAgent.Recorder.class){return data.get(key);}}
    public Integer getOrDefault(Object key,Integer fallback){synchronized(PlannedServiceAgent.Recorder.class){return data.getOrDefault(key,fallback);}}
    public boolean containsKey(Object key){synchronized(PlannedServiceAgent.Recorder.class){return data.containsKey(key);}}
    public int size(){synchronized(PlannedServiceAgent.Recorder.class){drain(64);return data.size();}}
    public Set<Map.Entry<String,Integer>> entrySet(){synchronized(PlannedServiceAgent.Recorder.class){return Collections.unmodifiableMap(new HashMap<>(data)).entrySet();}}
    void retireOwner(String owner){Set<String> keys=owners.remove(owner);if(keys!=null){pending+=keys.size();cleanup.addLast(keys.iterator());}}
    void drain(int budget){synchronized(PlannedServiceAgent.Recorder.class){for(int i=0;i<budget&&!cleanup.isEmpty();i++){Iterator<String> keys=cleanup.peekFirst();if(keys.hasNext()){data.remove(keys.next());pending--;retiredEntries++;}if(!keys.hasNext())cleanup.removeFirst();}}}
    public Integer remove(Object key){throw new UnsupportedOperationException("Cannot remove live field versions");}
    public void clear(){throw new UnsupportedOperationException("Cannot clear live field versions");}
}
