package com.compset.gateway.core;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.Locale;

/** CONNECT authority and resolved-address policy, independent of Android. */
public final class DestinationPolicy {
    private static final String[] DOMAINS = {"airbnb.com", "airbnb.co.in", "airbnb.ae",
        "booking.com", "bstatic.com", "expedia.com", "expedia.co.in", "agoda.com", "agoda.net",
        "makemytrip.com", "goibibo.com", "bnbmehomes.com", "google.com", "gstatic.com",
        "googleusercontent.com", "lemontreehotels.com", "wyndhamhotels.com", "sarovarhotels.com",
        "sterlingholidays.com", "spreehotels.com", "hoteltheonix.com"};
    private DestinationPolicy() {}

    public static String allowedAuthority(String authority) {
        if (authority == null || !authority.matches("[A-Za-z0-9.-]{1,253}:443")) return null;
        String host = authority.substring(0, authority.length() - 4).toLowerCase(Locale.US);
        if (host.startsWith(".") || host.endsWith(".") || host.contains("..")) return null;
        for (String label : host.split("\\.")) {
            if (label.length() > 63 || label.startsWith("-") || label.endsWith("-")) return null;
        }
        if (host.equals("api.ipify.org") || host.equals("checkip.amazonaws.com") || host.equals("httpbin.org")) return host;
        for (String domain : DOMAINS) if (host.equals(domain) || host.endsWith("." + domain)) return host;
        return null;
    }

    public static InetAddress privateIpv4(String literal) {
        if (literal == null || !literal.matches("(?:0|[1-9][0-9]{0,2})(?:\\.(?:0|[1-9][0-9]{0,2})){3}")) return null;
        String[] parts = literal.split("\\."); byte[] bytes = new byte[4];
        for (int i=0; i<4; i++) { int n=Integer.parseInt(parts[i]); if(n>255)return null; bytes[i]=(byte)n; }
        int a=bytes[0]&255,b=bytes[1]&255;
        if (!(a==10 || a==172 && b>=16 && b<=31 || a==192 && b==168)) return null;
        try { return InetAddress.getByAddress(bytes); } catch (UnknownHostException impossible) { return null; }
    }

    public static boolean sameSubnet(InetAddress first, InetAddress second, int prefix) {
        if (first == null || second == null || prefix < 1 || prefix > 32) return false;
        byte[] a=first.getAddress(),b=second.getAddress();
        if(a.length!=4 || b.length!=4)return false;
        for(int i=0;i<4;i++){int bits=Math.min(8,Math.max(0,prefix-i*8));int mask=bits==0?0:(255 << (8-bits))&255;
            if(((a[i]&255)&mask)!=((b[i]&255)&mask))return false;}
        return true;
    }

    public static boolean isPublic(InetAddress address) {
        if(address==null || address.isAnyLocalAddress() || address.isLoopbackAddress()
            || address.isLinkLocalAddress() || address.isSiteLocalAddress() || address.isMulticastAddress()) return false;
        byte[] ip=address.getAddress();
        if(ip.length==4){
            int a=ip[0]&255,b=ip[1]&255,c=ip[2]&255;
            return !(a==0 || a==10 || a==127 || a>=224 || a==100 && b>=64 && b<=127
                || a==169 && b==254 || a==172 && b>=16 && b<=31 || a==192 && (b==168 || b==0 && (c==0 || c==2) || b==88 && c==99)
                || a==198 && (b==18 || b==19 || b==51 && c==100) || a==203 && b==0 && c==113);
        }
        if(ip.length!=16 || (ip[0]&0xe0)!=0x20)return false; // Global unicast only; excludes ULA, mapped, NAT64, local.
        int b=ip[1]&255,c=ip[2]&255,d=ip[3]&255;
        if((ip[0]&255)==0x20 && b==0x02)return false; // 6to4 embeds an arbitrary IPv4 destination.
        if((ip[0]&255)==0x20 && b==0x01 && (c<2 || c==0x0d && d==0xb8))return false;
        if((ip[0]&255)==0x3f && b==0xff && (c&0xf0)==0)return false; // Documentation prefix 3fff::/20.
        return true;
    }

    public static boolean allPublic(InetAddress[] addresses) {
        if(addresses==null || addresses.length==0 || addresses.length>16)return false;
        for(InetAddress address:addresses)if(!isPublic(address))return false;
        return true;
    }
}
