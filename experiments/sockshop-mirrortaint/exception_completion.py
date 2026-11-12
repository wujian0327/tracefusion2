"""Existing bounded exception dispatch facts shared with completion scopes.

This is not a Throwable/native-effect contract or arbitrary class hierarchy.
"""
HIERARCHY={
    'java.lang.NullPointerException':{'java/lang/NullPointerException','java/lang/RuntimeException','java/lang/Exception','java/lang/Throwable'},
    'java.lang.IllegalArgumentException':{'java/lang/IllegalArgumentException','java/lang/RuntimeException','java/lang/Exception','java/lang/Throwable'},
    'java.lang.IndexOutOfBoundsException':{'java/lang/IndexOutOfBoundsException','java/lang/RuntimeException','java/lang/Exception','java/lang/Throwable'},
}
for name in ('ArrayIndexOutOfBoundsException','ArrayStoreException','NegativeArraySizeException'):
    HIERARCHY['java.lang.'+name]={'java/lang/'+name,'java/lang/RuntimeException','java/lang/Exception','java/lang/Throwable'}
HIERARCHY['java.lang.ArrayIndexOutOfBoundsException'].add('java/lang/IndexOutOfBoundsException')
for name in ('ExecutionException','TimeoutException','CancellationException'):
    HIERARCHY['java.util.concurrent.'+name]={'java/util/concurrent/'+name,'java/lang/Exception','java/lang/Throwable'}
    if name=='CancellationException':HIERARCHY['java.util.concurrent.'+name].add('java/lang/RuntimeException')


def handler_partition(handlers,types):
    if types is None:
        return {h['handler']for h in handlers},None if not any(h['type']is None for h in handlers)else set()
    result=set();unhandled=set()
    for typ in types:
        ancestors=HIERARCHY.get(typ.replace('/','.'))
        if ancestors is None:
            return {h['handler']for h in handlers},None if not any(h['type']is None for h in handlers)else set()
        covered=False
        for h in handlers:
            bound=h['type']
            if bound is None or bound in ancestors:
                result.add(h['handler']);covered=True;break
            narrower=HIERARCHY.get(bound.replace('/','.'))
            if narrower is None or typ in narrower:result.add(h['handler'])
        if not covered:unhandled.add(typ)
    return result,unhandled


def handler_targets(handlers,types):return handler_partition(handlers,types)[0]
