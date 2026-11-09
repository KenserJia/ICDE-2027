import stream.scotty.core.AggregateWindow;
import stream.scotty.core.windowFunction.CommutativeAggregateFunction;
import stream.scotty.core.windowType.SlidingWindow;
import stream.scotty.core.windowType.TumblingWindow;
import stream.scotty.core.windowType.WindowMeasure;
import stream.scotty.slicing.SlicingWindowOperator;
import stream.scotty.state.memory.MemoryStateFactory;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Random;

/** Adapter only: the vendored Scotty core is unmodified. */
public final class ScottyAdapter {
    static final long WINDOW = 256;
    static final long SLIDE = 64;

    static final class Stats implements Serializable {
        final double sum;
        final long count;
        Stats(double sum, long count) { this.sum = sum; this.count = count; }
        double mean() { return sum / count; }
    }

    static final class MeanFunction implements CommutativeAggregateFunction<Double, Stats, Stats> {
        public Stats lift(Double value) { return new Stats(value, 1); }
        public Stats combine(Stats left, Stats right) {
            return new Stats(left.sum + right.sum, left.count + right.count);
        }
        public Stats lower(Stats aggregate) { return aggregate; }
    }

    static final class Result {
        final long elapsedNs;
        final int outputs;
        final long checked;
        final long wrong;
        final double maxAbsError;
        final long heapDelta;
        Result(long elapsedNs, int outputs, long checked, long wrong,
               double maxAbsError, long heapDelta) {
            this.elapsedNs = elapsedNs; this.outputs = outputs; this.checked = checked;
            this.wrong = wrong; this.maxAbsError = maxAbsError; this.heapDelta = heapDelta;
        }
    }

    static double value(long timestamp) {
        return Math.sin(timestamp * 0.013) + 0.2 * Math.cos(timestamp * 0.003)
                + ((timestamp % 29) - 14) * 0.001;
    }

    static int[] order(int events, boolean outOfOrder, long seed) {
        int[] out = new int[events];
        for (int i = 0; i < events; i++) out[i] = i;
        if (!outOfOrder) return out;
        Random random = new Random(seed);
        final int block = 64;
        // Keep timestamp zero first so Scotty establishes the stream origin,
        // while retaining block boundaries used by periodic watermarks.
        for (int i = Math.min(events, block) - 1; i > 1; i--) {
            int j = 1 + random.nextInt(i);
            int tmp = out[i]; out[i] = out[j]; out[j] = tmp;
        }
        for (int begin = block; begin < events; begin += block) {
            int end = Math.min(events, begin + block);
            for (int i = end - 1; i > begin; i--) {
                int j = begin + random.nextInt(i - begin + 1);
                int tmp = out[i]; out[i] = out[j]; out[j] = tmp;
            }
        }
        return out;
    }

    static Map<String, List<Double>> expected(int events) {
        double[] prefix = new double[events + 1];
        for (int i = 0; i < events; i++) prefix[i + 1] = prefix[i] + value(i);
        Map<String, List<Double>> result = new HashMap<>();
        for (long start = 0; start + WINDOW <= events; start += SLIDE) {
            add(result, start, start + WINDOW,
                    (prefix[(int)(start + WINDOW)] - prefix[(int)start]) / WINDOW);
        }
        for (long start = 0; start + WINDOW <= events; start += WINDOW) {
            add(result, start, start + WINDOW,
                    (prefix[(int)(start + WINDOW)] - prefix[(int)start]) / WINDOW);
        }
        return result;
    }

    static void add(Map<String, List<Double>> map, long start, long end, double value) {
        map.computeIfAbsent(start + ":" + end, key -> new ArrayList<>()).add(value);
    }

    static long usedHeap() {
        Runtime runtime = Runtime.getRuntime();
        return runtime.totalMemory() - runtime.freeMemory();
    }

    static Result runScotty(int events, boolean outOfOrder, long seed, boolean check) {
        System.gc();
        long heapBefore = usedHeap();
        SlicingWindowOperator<Double> operator = new SlicingWindowOperator<>(new MemoryStateFactory());
        operator.addWindowFunction(new MeanFunction());
        operator.addWindowAssigner(new SlidingWindow(WindowMeasure.Time, WINDOW, SLIDE));
        operator.addWindowAssigner(new TumblingWindow(WindowMeasure.Time, WINDOW));
        operator.setMaxLateness(128);
        int[] arrival = order(events, outOfOrder, seed);
        List<AggregateWindow> windows = new ArrayList<>();
        // Establish an initial watermark before ingestion, then advance it only
        // after a complete 4096-event arrival block.  The shuffled 64-event
        // blocks therefore remain within declared lateness and no early output
        // is silently skipped by Scotty's first-watermark initialization.
        operator.processWatermark(0);
        long startNs = System.nanoTime();
        for (int index = 0; index < arrival.length; index++) {
            int timestamp = arrival[index];
            operator.processElement(value(timestamp), timestamp);
            if ((index + 1) % 4096 == 0) {
                windows.addAll(operator.processWatermark(index + 1));
            }
        }
        if (events % 4096 != 0) windows.addAll(operator.processWatermark(events));
        long elapsedNs = System.nanoTime() - startNs;
        long heapAfter = usedHeap();
        long checked = 0, wrong = 0; double maxError = 0;
        if (check) {
            Map<String, List<Double>> truth = expected(events);
            Map<String, List<Double>> actual = new HashMap<>();
            for (AggregateWindow window : windows) {
                if (!window.hasValue()) continue;
                Stats stats = (Stats)window.getAggValues().get(0);
                add(actual, window.getStart(), window.getEnd(), stats.mean());
            }
            for (Map.Entry<String, List<Double>> entry : truth.entrySet()) {
                List<Double> expectedValues = entry.getValue();
                List<Double> actualValues = actual.getOrDefault(entry.getKey(), Collections.emptyList());
                checked += expectedValues.size();
                if (actualValues.size() != expectedValues.size()) {
                    wrong += Math.abs(actualValues.size() - expectedValues.size());
                }
                for (int i = 0; i < Math.min(expectedValues.size(), actualValues.size()); i++) {
                    double error = Math.abs(expectedValues.get(i) - actualValues.get(i));
                    maxError = Math.max(maxError, error);
                    if (error > 1e-11) wrong++;
                }
            }
        }
        return new Result(elapsedNs, windows.size(), checked, wrong, maxError, heapAfter - heapBefore);
    }

    /** Exact local reference: updates every overlapping materialized window. */
    static Result runBuckets(int events, boolean outOfOrder, long seed, boolean check) {
        System.gc(); long heapBefore = usedHeap();
        Map<String, Stats> buckets = new HashMap<>();
        int[] arrival = order(events, outOfOrder, seed);
        long startNs = System.nanoTime();
        for (int timestamp : arrival) {
            double v = value(timestamp);
            long lastSliding = (timestamp / SLIDE) * SLIDE;
            for (long windowStart = lastSliding; windowStart + WINDOW > timestamp && windowStart >= 0; windowStart -= SLIDE) {
                merge(buckets, "S:" + windowStart + ":" + (windowStart + WINDOW), v);
                if (windowStart < SLIDE) break;
            }
            long tumblingStart = (timestamp / WINDOW) * WINDOW;
            merge(buckets, "T:" + tumblingStart + ":" + (tumblingStart + WINDOW), v);
        }
        int outputs = 0;
        for (Map.Entry<String, Stats> entry : buckets.entrySet()) {
            String[] parts = entry.getKey().split(":");
            long end = Long.parseLong(parts[2]);
            if (end <= events) outputs++;
        }
        long elapsedNs = System.nanoTime() - startNs;
        long heapAfter = usedHeap();
        long checked = 0, wrong = 0; double maxError = 0;
        if (check) {
            Map<String, List<Double>> truth = expected(events);
            Map<String, List<Double>> actual = new HashMap<>();
            for (Map.Entry<String, Stats> entry : buckets.entrySet()) {
                String[] parts = entry.getKey().split(":");
                long begin = Long.parseLong(parts[1]), end = Long.parseLong(parts[2]);
                if (end <= events) add(actual, begin, end, entry.getValue().mean());
            }
            for (Map.Entry<String, List<Double>> entry : truth.entrySet()) {
                List<Double> expectedValues = entry.getValue();
                List<Double> actualValues = actual.getOrDefault(entry.getKey(), Collections.emptyList());
                checked += expectedValues.size();
                if (actualValues.size() != expectedValues.size()) wrong += Math.abs(actualValues.size() - expectedValues.size());
                for (int i = 0; i < Math.min(expectedValues.size(), actualValues.size()); i++) {
                    double error = Math.abs(expectedValues.get(i) - actualValues.get(i));
                    maxError = Math.max(maxError, error); if (error > 1e-11) wrong++;
                }
            }
        }
        return new Result(elapsedNs, outputs, checked, wrong, maxError, heapAfter - heapBefore);
    }

    static void merge(Map<String, Stats> buckets, String key, double value) {
        Stats old = buckets.get(key);
        buckets.put(key, old == null ? new Stats(value, 1) : new Stats(old.sum + value, old.count + 1));
    }

    static String json(String method, boolean outOfOrder, int events, int repeat, Result r) {
        double seconds = r.elapsedNs / 1e9;
        return String.format(Locale.ROOT,
                "{\"method\":\"%s\",\"out_of_order\":%s,\"events\":%d,\"repeat\":%d," +
                "\"elapsed_s\":%.9f,\"events_per_s\":%.3f,\"outputs\":%d," +
                "\"checked\":%d,\"wrong\":%d,\"max_abs_error\":%.17g,\"heap_delta_bytes\":%d}",
                method, outOfOrder, events, repeat, seconds, events / seconds, r.outputs,
                r.checked, r.wrong, r.maxAbsError, r.heapDelta);
    }

    public static void main(String[] args) {
        int events = args.length > 0 ? Integer.parseInt(args[0]) : 1_000_000;
        int repeats = args.length > 1 ? Integer.parseInt(args[1]) : 5;
        String methodFilter = args.length > 2 ? args[2] : "all";
        String arrivalFilter = args.length > 3 ? args[3] : "all";
        int warmups = args.length > 4 ? Integer.parseInt(args[4]) : 0;
        int correctnessEvents = Math.min(events, 100_000);
        for (boolean outOfOrder : new boolean[]{false, true}) {
            if (!arrivalFilter.equals("all") &&
                    outOfOrder != arrivalFilter.equals("out_of_order")) continue;
            if (methodFilter.equals("all") || methodFilter.equals("scotty")) {
                Result checked = runScotty(correctnessEvents, outOfOrder, 7300, true);
                System.out.println(json("scotty", outOfOrder, correctnessEvents, -1, checked));
                for (int warmup = 0; warmup < warmups; warmup++)
                    runScotty(events, outOfOrder, 7200 + warmup, false);
                for (int repeat = 0; repeat < repeats; repeat++)
                    System.out.println(json("scotty", outOfOrder, events, repeat,
                            runScotty(events, outOfOrder, 7300 + repeat, false)));
            }
            if (methodFilter.equals("all") || methodFilter.equals("window_buckets_local")) {
                Result checked = runBuckets(correctnessEvents, outOfOrder, 7300, true);
                System.out.println(json("window_buckets_local", outOfOrder, correctnessEvents, -1, checked));
                for (int warmup = 0; warmup < warmups; warmup++)
                    runBuckets(events, outOfOrder, 7200 + warmup, false);
                for (int repeat = 0; repeat < repeats; repeat++)
                    System.out.println(json("window_buckets_local", outOfOrder, events, repeat,
                            runBuckets(events, outOfOrder, 7300 + repeat, false)));
            }
        }
    }
}
