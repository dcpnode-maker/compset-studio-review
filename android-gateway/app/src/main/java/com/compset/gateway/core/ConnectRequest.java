package com.compset.gateway.core;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/** Small strict HTTP CONNECT parser; never consumes bytes after the header. */
public final class ConnectRequest {
    public final String host;
    private ConnectRequest(String host) { this.host=host; }
    public static final class Rejected extends IOException {
        public final int status;
        public Rejected(int status){super("Request rejected");this.status=status;}
    }
    public static ConnectRequest read(InputStream stream,String expectedAuthorization)throws IOException{
        ByteArrayOutputStream bytes=new ByteArrayOutputStream(); int tail=0;
        while(bytes.size()<8192){int value=stream.read();if(value<0)throw new Rejected(400);
            if(value>126 || value<32 && value!=13 && value!=10)throw new Rejected(400);
            bytes.write(value);tail=(tail<<8)|value;if(tail==0x0d0a0d0a)break;}
        if(tail!=0x0d0a0d0a)throw new Rejected(431);
        String[] lines=new String(bytes.toByteArray(),StandardCharsets.US_ASCII).split("\r\n");
        if(lines.length>50)throw new Rejected(431);
        String auth=null,hostHeader=null;
        for(int i=1;i<lines.length;i++){
            String line=lines[i];int colon=line.indexOf(':');
            if(colon<=0 || line.charAt(0)==' ' || !line.substring(0,colon).matches("[A-Za-z0-9-]+"))throw new Rejected(400);
            String name=line.substring(0,colon),value=line.substring(colon+1).trim();
            if(name.equalsIgnoreCase("Proxy-Authorization")){if(auth!=null)throw new Rejected(400);auth=value;}
            if(name.equalsIgnoreCase("Host")){if(hostHeader!=null)throw new Rejected(400);hostHeader=value;}
            if(name.equalsIgnoreCase("Transfer-Encoding") || name.equalsIgnoreCase("Content-Length") && !value.equals("0"))throw new Rejected(400);
        }
        if(auth==null || !MessageDigest.isEqual(auth.getBytes(StandardCharsets.US_ASCII),expectedAuthorization.getBytes(StandardCharsets.US_ASCII)))throw new Rejected(407);
        String[] first=lines[0].split(" ",-1);
        if(first.length!=3 || !first[0].equals("CONNECT") || !(first[2].equals("HTTP/1.1")||first[2].equals("HTTP/1.0")))throw new Rejected(405);
        String host=DestinationPolicy.allowedAuthority(first[1]);if(host==null)throw new Rejected(403);
        if(hostHeader!=null && !hostHeader.equalsIgnoreCase(first[1]))throw new Rejected(400);
        return new ConnectRequest(host);
    }
    public static String authorization(String token){
        if(token==null || !token.matches("[0-9a-f]{32}"))throw new IllegalArgumentException("Invalid pairing token");
        byte[] input=("compset:"+token).getBytes(StandardCharsets.US_ASCII);
        final String alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        StringBuilder out=new StringBuilder("Basic ");
        for(int i=0;i<input.length;i+=3){int a=input[i]&255,b=i+1<input.length?input[i+1]&255:0,c=i+2<input.length?input[i+2]&255:0;
            out.append(alphabet.charAt(a>>2)).append(alphabet.charAt((a&3)<<4|b>>4));
            out.append(i+1<input.length?alphabet.charAt((b&15)<<2|c>>6):'=').append(i+2<input.length?alphabet.charAt(c&63):'=');}
        return out.toString();
    }
}
