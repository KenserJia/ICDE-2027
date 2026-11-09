package org.apache.flink.api.java.tuple;

import java.io.Serializable;

/** Compile-only stub for the unused PunctuationWindow branch. */
public abstract class Tuple implements Serializable {
    public abstract int getArity();
    public abstract <T> T getField(int position);
}
