package com.compset.gateway.core;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public final class CoreTests {
    private static int checks;
    private static final String TOKEN="«REDACTED-SECRET»";
    private static void check(boolean value,String message){checks++;if(!value)throw new AssertionError(message);}
    private static String header(String target){return "CONNECT "+target+" HTTP/1.1\r\nHost: "+target+"\r\nProxy-Authorization: "+ConnectRequest.authorization(TOKEN)+"\r\n\r\n";}
    private static ConnectRequest parse(String input)throws IOException{return ConnectRequest.read(new ByteArrayInputStream(input.getBytes(StandardCharsets.US_ASCII)),ConnectRequest.authorization(TOKEN));}
    private static void rejected(String input,int status)throws Exception{try{parse(input);throw new AssertionError("Request accepted");}catch(ConnectRequest.Rejected error){check(error.status==status,"Wrong rejection status");}}
    public static void main(String[] args)throws Exception{
        checks+=Nat64DuplicateTests.run();
        check("www.airbnb.com".equals(DestinationPolicy.allowedAuthority("WWW.AIRBNB.COM:443")),"Canonical host");
        check("httpbin.org".equals(DestinationPolicy.allowedAuthority("httpbin.org:443")),"Desktop probe destination");
        for(String authority:new String[]{"airbnb.com.evil.test:443","evilairbnb.com:443","127.0.0.1:443","[::1]:443","airbnb.com:80","user@airbnb.com:443","airbnb.com.:443","sub.httpbin.org:443"})check(DestinationPolicy.allowedAuthority(authority)==null,"Authority rejection");
        for(String ip:new String[]{"0.0.0.0","127.0.0.1","10.0.0.1","192.168.1.1","172.16.0.1","169.254.169.254","100.64.0.1","192.0.2.1","198.51.100.1","203.0.113.1","198.18.0.1","224.1.1.1","255.255.255.255","::1","::","fc00::1","fe80::1","ff02::1","::ffff:127.0.0.1","64:ff9b::a00:1","2001:db8::1","2001:20::1","2002:0a00:0001::","3fff::1"})check(!DestinationPolicy.isPublic(InetAddress.getByName(ip)),"Nonpublic address "+ip);
        check(DestinationPolicy.isPublic(InetAddress.getByName("8.8.8.8")),"Public IPv4");
        check(DestinationPolicy.isPublic(InetAddress.getByName("2001:4860:4860::8888")),"Public IPv6");
        check(!DestinationPolicy.allPublic(new InetAddress[]{InetAddress.getByName("8.8.8.8"),InetAddress.getByName("10.1.2.3")}),"Mixed DNS answer rejected");
        check(!DestinationPolicy.allPublic(new InetAddress[0]),"Empty DNS response rejected");
        check(DestinationPolicy.privateIpv4("192.168.1.20")!=null,"Private pairing IPv4");
        for(String ip:new String[]{"192.168.001.20","example.com","8.8.8.8","127.0.0.1","192.168.1.999","192.168.1.20:8443"})check(DestinationPolicy.privateIpv4(ip)==null,"Invalid pairing input");
        check(DestinationPolicy.sameSubnet(DestinationPolicy.privateIpv4("192.168.1.20"),DestinationPolicy.privateIpv4("192.168.1.10"),24),"Same subnet");
        check(!DestinationPolicy.sameSubnet(DestinationPolicy.privateIpv4("192.168.2.20"),DestinationPolicy.privateIpv4("192.168.1.10"),24),"Other subnet");
        check(ConnectRequest.authorization(TOKEN).equals("Basic "+java.util.Base64.getEncoder().encodeToString(("compset:"+TOKEN).getBytes(StandardCharsets.US_ASCII))),"Android6-compatible Basic encoder");
        check(parse(header("api.ipify.org:443")).host.equals("api.ipify.org"),"Authenticated CONNECT");
        ByteArrayInputStream pipelined=new ByteArrayInputStream((header("httpbin.org:443")+"TLSBYTES").getBytes(StandardCharsets.US_ASCII));ConnectRequest.read(pipelined,ConnectRequest.authorization(TOKEN));check(pipelined.read()=='T',"No TLS bytes consumed by parser");
        rejected("CONNECT httpbin.org:443 HTTP/1.1\r\n\r\n",407);
        rejected(header("httpbin.org:443").replace(ConnectRequest.authorization(TOKEN),"Basic incorrect"),407);
        rejected(header("httpbin.org:443").replace("\r\n\r\n","\r\nProxy-Authorization: duplicate\r\n\r\n"),400);
        rejected(header("httpbin.org:443").replace("CONNECT ","GET "),405);
        rejected(header("localhost:443"),403);
        rejected(header("httpbin.org:443").replace("Host: httpbin.org:443","Host: airbnb.com:443"),400);
        rejected(header("httpbin.org:443").replace("\r\n\r\n","\r\nTransfer-Encoding: chunked\r\n\r\n"),400);
        rejected(header("httpbin.org:443").replace("\r\n\r\n","\r\nContent-Length: 1\r\n\r\n"),400);
        StringBuilder huge=new StringBuilder("CONNECT ");for(int i=0;i<9000;i++)huge.append('a');rejected(huge.toString(),431);
        final long[] now={0};SessionBudget.Clock clock=new SessionBudget.Clock(){public long nowMillis(){return now[0];}};
        SessionBudget b=new SessionBudget(clock,1000,10,3,2);check(b.open()&&b.open()&&!b.open(),"Concurrent cap");b.closed();check(b.open(),"Slot reused");b.closed();b.closed();check(!b.open()&&b.connectionLimitReached(),"Total connection cap");
        SessionBudget bytes=new SessionBudget(clock,1000,10,3,2);check(bytes.transfer(6)&&!bytes.transfer(5)&&bytes.transfer(4)&&bytes.expired(),"Exact shared byte ceiling");
        SessionBudget expiry=new SessionBudget(clock,1000,10,3,2);now[0]=1000;check(!expiry.open()&&!expiry.transfer(1),"Monotonic expiry");now[0]=0;
        SessionBudget failures=new SessionBudget(clock,1000,100,100,2);for(int i=0;i<7;i++)check(!failures.authFailed(),"Bounded failure allowance");check(failures.authFailed()&&!failures.open(),"Repeated auth stop");
        SessionBudget longSession=new SessionBudget(clock,86400000L,17179869184L,10000,2);check(longSession.open(),"Explicit24h/16GiB maximum");longSession.stop();check(!longSession.transfer(1),"User stop blocks transfer");
        final SessionBudget concurrent=new SessionBudget(clock,100000,1000,100,4);final AtomicInteger opened=new AtomicInteger();final CountDownLatch ready=new CountDownLatch(20),go=new CountDownLatch(1),done=new CountDownLatch(20);
        for(int i=0;i<20;i++)new Thread(new Runnable(){public void run(){ready.countDown();try{go.await();if(concurrent.open())opened.incrementAndGet();}catch(InterruptedException ignored){}finally{done.countDown();}}}).start();ready.await();go.countDown();done.await();check(opened.get()==4&&concurrent.activeConnections()==4,"Concurrent admission is atomic");
        System.out.println("Core proof passed: "+checks+" assertions");
    }
}
