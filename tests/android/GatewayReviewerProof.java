import com.compset.gateway.core.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import javax.net.ssl.*;

/** Independent reviewer proof. Fake transport only; no device or network access. */
public final class GatewayReviewerProof {
    static int checks;
    static final String TOKEN="«REDACTED-SECRET»";
    static final String AUTH=ConnectRequest.authorization(TOKEN);
    static final InetAddress LAN=ip("192.168.23.2"), CLIENT=ip("192.168.23.3"), PUBLIC=ip("8.8.8.8");
    static InetAddress ip(String value) { try{return InetAddress.getByName(value);}catch(Exception e){throw new RuntimeException(e);} }
    static synchronized void check(boolean value,String message){checks++;if(!value)throw new AssertionError(message);}
    static byte[] ascii(String text){return text.getBytes(StandardCharsets.US_ASCII);}
    static String request(String extra){return "CONNECT httpbin.org:443 HTTP/1.1\r\nHost: httpbin.org:443\r\nProxy-Authorization: "+AUTH+"\r\n"+extra+"\r\n";}
    static void rejected(String text,int status)throws Exception{
        try{ConnectRequest.read(new ByteArrayInputStream(ascii(text)),AUTH);throw new AssertionError("Accepted malformed request");}
        catch(ConnectRequest.Rejected e){check(e.status==status,"Expected "+status+" got "+e.status);}
    }
    static void parser()throws Exception{
        check(AUTH.equals("Basic "+Base64.getEncoder().encodeToString(ascii("compset:"+TOKEN))),"Pairing auth matches standard Base64");
        ByteArrayInputStream input=new ByteArrayInputStream(ascii(request("")+"TLS_CLIENT_HELLO"));
        check(ConnectRequest.read(input,AUTH).host.equals("httpbin.org"),"Owned-device fixed probe endpoint permitted");
        check(input.read()=='T',"CONNECT parser leaves TLS bytes unread");
        rejected(request("").replace(AUTH,ConnectRequest.authorization("1123456789abcdef0123456789abcdef")),407);
        rejected(request("Proxy-Authorization: "+AUTH+"\r\n"),400);
        rejected(request("Host: httpbin.org:443\r\n"),400);
        rejected(request("Content-Length: 1\r\n"),400);
        rejected(request("Transfer-Encoding: chunked\r\n"),400);
        rejected(request(" folded: value\r\n"),400);
        rejected(request("").replace("Host: httpbin.org:443","Host: airbnb.com:443"),400);
        rejected(request("").replace("CONNECT httpbin.org:443","GET https://httpbin.org/ip"),405);
        rejected(request("").replace("httpbin.org:443","httpbin.org:80"),403);
        rejected(request("").replace("httpbin.org:443","httpbin.org.attacker.test:443"),403);
        rejected(request("X-Fill: "+new String(new char[8200]).replace('\0','x')+"\r\n"),431);
        rejected(request("X-Bad: \tvalue\r\n"),400);
        rejected(request("").replace("\r\n\r\n","\r\n"),400);
    }
    static void policy(){
        String[] denied={"127.0.0.1:443","192.168.23.1:443","[::1]:443","airbnb.com:444","airbnb.com.:443","airbnb.com.evil.test:443","evilairbnb.com:443","a..airbnb.com:443","-bad.airbnb.com:443","user@airbnb.com:443","sub.httpbin.org:443"};
        for(String value:denied)check(DestinationPolicy.allowedAuthority(value)==null,"Denied authority "+value);
        check("www.airbnb.com".equals(DestinationPolicy.allowedAuthority("WWW.AIRBNB.COM:443")),"Exact domain boundary accepts legitimate subdomain");
        String[] privateOrSpecial={"0.0.0.0","10.0.0.1","100.64.1.1","127.0.0.1","169.254.1.1","172.16.0.1","192.168.1.1","192.0.2.1","198.18.0.1","198.51.100.1","203.0.113.1","224.0.0.1","255.255.255.255","::1","fc00::1","fe80::1","2001:db8::1","2002:7f00:1::","64:ff9b::7f00:1"};
        for(String value:privateOrSpecial)check(!DestinationPolicy.isPublic(ip(value)),"Denied resolved address "+value);
        check(DestinationPolicy.isPublic(PUBLIC),"Public IPv4 accepted");
        check(DestinationPolicy.isPublic(ip("2606:4700:4700::1111")),"Public IPv6 accepted");
        check(!DestinationPolicy.allPublic(new InetAddress[]{PUBLIC,LAN}),"Mixed DNS answer cannot smuggle LAN destination");
        check(!DestinationPolicy.allPublic(new InetAddress[0]),"Empty DNS denied");
        InetAddress[] tooMany=new InetAddress[17];Arrays.fill(tooMany,PUBLIC);check(!DestinationPolicy.allPublic(tooMany),"DNS cardinality capped");
        check(DestinationPolicy.privateIpv4("192.168.23.2")!=null,"LAN literal accepted");
        check(DestinationPolicy.privateIpv4("192.168.023.2")==null,"Ambiguous zero-padded literal denied");
        check(DestinationPolicy.privateIpv4("8.8.8.8")==null,"Public listener denied");
        check(DestinationPolicy.sameSubnet(LAN,CLIENT,24),"Same subnet accepted");
        check(!DestinationPolicy.sameSubnet(LAN,ip("192.168.24.3"),24),"Other subnet denied");
        check(!DestinationPolicy.sameSubnet(LAN,CLIENT,0),"Wildcard subnet denied");
    }
    static void budgets(){
        AtomicLong now=new AtomicLong(0);SessionBudget b=new SessionBudget(now::get,1000,10,2,1);
        check(b.open(),"First admission");check(!b.open(),"Concurrency limit");b.closed();check(b.open(),"Second admission");b.closed();check(!b.open(),"Connection total limit");
        check(b.connectionLimitReached(),"Total limit closes session when drained");
        check(!b.transfer(-1),"Negative bytes denied");check(b.transfer(9),"Within byte budget");check(!b.transfer(2),"Excess denied before accounting");check(b.transferredBytes()==9,"Denied bytes not counted");check(b.transfer(1),"Exact remaining byte accepted");check(b.expired(),"Full byte budget expires");
        SessionBudget timed=new SessionBudget(now::get,1000,10,10,1);now.set(1000);check(!timed.open(),"Deadline inclusive");
        SessionBudget auth=new SessionBudget(()->0L,1000,10,10,1);for(int i=0;i<7;i++)check(!auth.authFailed(),"Auth failure count before cap");check(auth.authFailed()&&auth.expired(),"Eight auth failures halt whole session");
        check(new SessionBudget(()->0L,86400000L,17179869184L,10000,4).open(),"Finite advertised maximum accepted");
        long[][] invalid={{0,1,1,1},{86400001L,1,1,1},{1,0,1,1},{1,17179869185L,1,1},{1,1,10001,1},{1,1,1,5}};
        for(long[] values:invalid){try{new SessionBudget(()->0L,values[0],values[1],(int)values[2],(int)values[3]);throw new AssertionError("Invalid resource bound accepted");}catch(IllegalArgumentException expected){checks++;}}
        try{new SessionBudget(()->Long.MAX_VALUE,1000,1,1,1);throw new AssertionError("Overflowing deadline accepted");}catch(IllegalArgumentException expected){checks++;}
    }
    static class BlockingInput extends InputStream {
        final byte[] prefix;int position;boolean closed;
        BlockingInput(String prefix){this.prefix=ascii(prefix);}
        @Override public synchronized int read()throws IOException{
            if(position<prefix.length)return prefix[position++]&255;
            while(!closed){try{wait();}catch(InterruptedException e){throw new IOException("Interrupted");}}
            return -1;
        }
        @Override public synchronized int read(byte[] b,int off,int len)throws IOException{
            if(position>=prefix.length)return read();int count=Math.min(len,prefix.length-position);System.arraycopy(prefix,position,b,off,count);position+=count;return count;
        }
        @Override public synchronized void close(){closed=true;notifyAll();}
    }
    static class FakeClient extends SSLSocket {
        final BlockingInput input=new BlockingInput(request(""));final ByteArrayOutputStream output=new ByteArrayOutputStream();
        @Override public InetAddress getInetAddress(){return CLIENT;}
        @Override public InputStream getInputStream(){return input;}
        @Override public OutputStream getOutputStream(){return output;}
        @Override public synchronized void close(){input.close();}
        @Override public void setSoTimeout(int value){} @Override public void setTcpNoDelay(boolean value){}
        @Override public void startHandshake(){} @Override public SSLSession getSession(){return null;}
        @Override public String[] getSupportedCipherSuites(){return new String[0];} @Override public String[] getEnabledCipherSuites(){return new String[0];} @Override public void setEnabledCipherSuites(String[] v){}
        @Override public String[] getSupportedProtocols(){return new String[0];} @Override public String[] getEnabledProtocols(){return new String[0];} @Override public void setEnabledProtocols(String[] v){}
        @Override public void addHandshakeCompletedListener(HandshakeCompletedListener v){} @Override public void removeHandshakeCompletedListener(HandshakeCompletedListener v){}
        @Override public void setUseClientMode(boolean v){} @Override public boolean getUseClientMode(){return false;}
        @Override public void setNeedClientAuth(boolean v){} @Override public boolean getNeedClientAuth(){return false;}
        @Override public void setWantClientAuth(boolean v){} @Override public boolean getWantClientAuth(){return false;}
        @Override public void setEnableSessionCreation(boolean v){} @Override public boolean getEnableSessionCreation(){return true;}
    }
    static class FakeListener extends SSLServerSocket {
        final Queue<FakeClient> clients=new ConcurrentLinkedQueue<>();volatile boolean closed;
        FakeListener(List<FakeClient> values)throws IOException{clients.addAll(values);}
        @Override public boolean isBound(){return true;} @Override public InetAddress getInetAddress(){return LAN;}
        @Override public Socket accept()throws IOException{while(!closed){FakeClient c=clients.poll();if(c!=null)return c;try{Thread.sleep(10);}catch(InterruptedException e){throw new IOException(e);}}throw new IOException("Closed");}
        @Override public void close(){closed=true;}
        @Override public String[] getEnabledCipherSuites(){return new String[0];} @Override public void setEnabledCipherSuites(String[] v){} @Override public String[] getSupportedCipherSuites(){return new String[0];}
        @Override public String[] getSupportedProtocols(){return new String[0];} @Override public String[] getEnabledProtocols(){return new String[0];} @Override public void setEnabledProtocols(String[] v){}
        @Override public void setNeedClientAuth(boolean v){} @Override public boolean getNeedClientAuth(){return false;} @Override public void setWantClientAuth(boolean v){} @Override public boolean getWantClientAuth(){return false;}
        @Override public void setUseClientMode(boolean v){} @Override public boolean getUseClientMode(){return false;} @Override public void setEnableSessionCreation(boolean v){} @Override public boolean getEnableSessionCreation(){return true;}
    }
    static class FakeTarget extends Socket {
        final BlockingInput input=new BlockingInput("UPSTREAM_REPLY");final CountDownLatch barrier;volatile boolean closed;
        FakeTarget(CountDownLatch barrier){this.barrier=barrier;}
        @Override public void connect(SocketAddress address,int timeout)throws IOException{
            check(address instanceof InetSocketAddress&&((InetSocketAddress)address).getAddress().equals(PUBLIC)&&((InetSocketAddress)address).getPort()==443,"Only reviewed numeric address is connected");
            barrier.countDown();try{if(!barrier.await(2,TimeUnit.SECONDS))throw new IOException("Barrier timed out");}catch(InterruptedException e){throw new IOException(e);}
        }
        @Override public InputStream getInputStream(){return input;} @Override public OutputStream getOutputStream(){return new ByteArrayOutputStream();}
        @Override public void setSoTimeout(int value){} @Override public void setTcpNoDelay(boolean value){}
        @Override public void close(){closed=true;input.close();}
    }
    static void concurrentTransport()throws Exception{
        List<FakeClient> clients=new ArrayList<>();for(int i=0;i<4;i++)clients.add(new FakeClient());
        CountDownLatch connected=new CountDownLatch(4);List<FakeTarget> targets=Collections.synchronizedList(new ArrayList<>());
        SessionBudget b=new SessionBudget(()->System.nanoTime()/1000000L,10000,100000,20,4);
        TunnelServer server=new TunnelServer(new FakeListener(clients),CLIENT,new TunnelServer.Route(){
            public InetAddress[] resolve(String host){return new InetAddress[]{PUBLIC};}
            public Socket socket(){FakeTarget t=new FakeTarget(connected);targets.add(t);return t;}
        },b,TOKEN,reason->{});
        try{
            server.start();long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(3);boolean all=false;
            while(System.nanoTime()<deadline){all=true;for(FakeClient c:clients)if(!c.output.toString("US-ASCII").contains("UPSTREAM_REPLY"))all=false;if(all)break;Thread.sleep(10);}
            check(all,"All four admitted tunnels receive upstream bytes without reverse-pump starvation");
        }finally{server.close();}
        long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(2);while(b.activeConnections()!=0&&System.nanoTime()<deadline)Thread.sleep(10);
        check(b.activeConnections()==0,"Stop drains admitted connections");for(FakeTarget target:targets)check(target.closed,"Stop closes every registered target");
    }
    static void stopPendingConnect()throws Exception{
        FakeClient client=new FakeClient();CountDownLatch entered=new CountDownLatch(1),released=new CountDownLatch(1);
        SessionBudget b=new SessionBudget(()->System.nanoTime()/1000000L,10000,100000,20,1);
        AtomicBoolean socketClosed=new AtomicBoolean();
        Socket pending=new Socket(){
            @Override public void connect(SocketAddress address,int timeout)throws IOException{
                entered.countDown();try{if(!released.await(2,TimeUnit.SECONDS))throw new IOException("Stop failed to cancel connect");}catch(InterruptedException e){throw new IOException(e);}throw new IOException("Closed");
            }
            @Override public void close(){socketClosed.set(true);released.countDown();}
        };
        TunnelServer server=new TunnelServer(new FakeListener(Collections.singletonList(client)),CLIENT,new TunnelServer.Route(){
            public InetAddress[] resolve(String host){return new InetAddress[]{PUBLIC};}
            public Socket socket(){return pending;}
        },b,TOKEN,reason->{});
        try{server.start();check(entered.await(2,TimeUnit.SECONDS),"Connect started");server.close();check(socketClosed.get(),"Stop immediately closes in-progress numeric connect");}
        finally{server.close();}
        long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(2);while(b.activeConnections()!=0&&System.nanoTime()<deadline)Thread.sleep(10);
        check(b.activeConnections()==0,"Stopped in-progress connect releases admission");
    }
    static void rejectMixedDnsBeforeSocket()throws Exception{
        FakeClient client=new FakeClient();AtomicInteger socketsCreated=new AtomicInteger();
        SessionBudget b=new SessionBudget(()->System.nanoTime()/1000000L,10000,100000,20,1);
        TunnelServer server=new TunnelServer(new FakeListener(Collections.singletonList(client)),CLIENT,new TunnelServer.Route(){
            public InetAddress[] resolve(String host){return new InetAddress[]{PUBLIC,LAN};}
            public Socket socket(){socketsCreated.incrementAndGet();return new Socket();}
        },b,TOKEN,reason->{});
        try{server.start();long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(2);while(!client.output.toString("US-ASCII").contains("403")&&System.nanoTime()<deadline)Thread.sleep(10);
            check(client.output.toString("US-ASCII").contains("403"),"Mixed DNS response rejected");check(socketsCreated.get()==0,"Mixed DNS creates no destination socket");}
        finally{server.close();}
    }
    public static void main(String[] args)throws Exception{parser();policy();budgets();concurrentTransport();stopPendingConnect();rejectMixedDnsBeforeSocket();System.out.println("Independent gateway checks passed: "+checks);}
}
