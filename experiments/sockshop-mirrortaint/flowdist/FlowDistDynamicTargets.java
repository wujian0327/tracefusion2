package dua.util;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import soot.RefLikeType;
import soot.RefType;
import soot.SootClass;
import soot.Type;
import soot.Value;

/** Disclosed model extension: lambda factory values have their declared
 * reference return type and its known subtypes, like the original Local case.
 * This is not a model of captured-variable or callback-body dependencies. */
public final class FlowDistDynamicTargets {
    public static List<RefLikeType> targets(Value value) {
        Type type = value.getType();
        if (!(type instanceof RefLikeType))
            throw new IllegalArgumentException("Unsupported primitive invokedynamic reference model");
        List<RefLikeType> result = new ArrayList<>();
        result.add((RefLikeType)type);
        if (type instanceof RefType) {
            for (SootClass subtype : Util.getAllSubtypes(((RefType)type).getSootClass()))
                result.add(subtype.getType());
        }
        Collections.sort(result, new Util.HashCodeComparator<RefLikeType>());
        return result;
    }
}
