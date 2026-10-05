package com.compset.gateway.core;

import java.net.InetAddress;
import java.util.Arrays;

/** Removes only advertised /96 DNS64 duplicates of public native A answers. */
public final class Nat64Duplicates {
    private Nat64Duplicates() {}

    /**
     * Returns original address objects in their original order, or null on rejection.
     * No advertised prefix is represented by (null, -1). This never resolves a name,
     * synthesizes an address, or permits connecting to a translated address.
     */
    public static InetAddress[] filter(InetAddress[] original, byte[] prefix, int prefixLength) {
        if (original == null || original.length == 0 || original.length > 16) return null;
        for (InetAddress address : original) if (address == null) return null;
        if (prefix == null) {
            if (prefixLength != -1) return null;
        } else if (!validPrefix(prefix, prefixLength)) return null;

        InetAddress[] kept = new InetAddress[original.length];
        int count = 0;
        for (InetAddress address : original) {
            byte[] bytes = address.getAddress();
            // A network-specific translation prefix can look like ordinary global IPv6.
            // Classify it first; generic isPublic must never authorize that translation.
            if (prefix != null && bytes.length == 16 && matches(bytes, prefix, prefixLength)) {
                if (prefixLength != 96 || !hasPublicNativeDuplicate(original, bytes)) return null;
                continue;
            }
            if (!DestinationPolicy.isPublic(address)) return null;
            kept[count++] = address;
        }
        if (count == 0) return null;
        return Arrays.copyOf(kept, count);
    }

    private static boolean hasPublicNativeDuplicate(InetAddress[] original, byte[] translated) {
        for (InetAddress address : original) {
            byte[] bytes = address.getAddress();
            if (bytes.length != 4 || !DestinationPolicy.isPublic(address)) continue;
            boolean same = true;
            for (int i = 0; i < 4; i++) if (bytes[i] != translated[12 + i]) same = false;
            if (same) return true;
        }
        return false;
    }

    private static boolean validPrefix(byte[] prefix, int length) {
        if (prefix.length != 16 || length < 0 || length > 128) return false;
        // Android IpPrefix supplies canonical network bytes; reject malformed callers.
        for (int i = length; i < 128; i++)
            if ((prefix[i / 8] & (1 << (7 - i % 8))) != 0) return false;
        return true;
    }

    private static boolean matches(byte[] address, byte[] prefix, int length) {
        for (int i = 0; i < length; i++) {
            int mask = 1 << (7 - i % 8);
            if ((address[i / 8] & mask) != (prefix[i / 8] & mask)) return false;
        }
        return true;
    }
}
