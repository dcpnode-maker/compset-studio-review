package com.compset.gateway.core;

import java.io.Closeable;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.Future;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLSocket;

/** Authenticated opaque TLS tunnels. Only numeric, reviewed DNS answers are connected. */
public final class TunnelServer implements Closeable {
    public interface Route {
        InetAddress[] resolve(String host) throws IOException;
        Socket socket() throws IOException;
    }
    public interface Events { void stopped(String reason); }
    private final SSLServerSocket listener; private final InetAddress pairedClient; private final Route route;
    private final SessionBudget budget; private final Events events;private final String authorization;
    private final AtomicBoolean closed=new AtomicBoolean();
    private final Set<Socket> sockets=Collections.synchronizedSet(new HashSet<Socket>());
    private final ThreadPoolExecutor workers=new ThreadPoolExecutor(4,4,0,TimeUnit.MILLISECONDS,new ArrayBlockingQueue<Runnable>(4));
    private final ThreadPoolExecutor reverse=new ThreadPoolExecutor(4,4,0,TimeUnit.MILLISECONDS,new ArrayBlockingQueue<Runnable>(4));
    private final ThreadPoolExecutor resolver=new ThreadPoolExecutor(2,2,0,TimeUnit.MILLISECONDS,new ArrayBlockingQueue<Runnable>(2));
    private final ScheduledExecutorService timer=Executors.newSingleThreadScheduledExecutor();
    public TunnelServer(SSLServerSocket listener,InetAddress pairedClient,Route route,SessionBudget budget,String token,Events events){
        if(listener==null||!listener.isBound()||DestinationPolicy.privateIpv4(listener.getInetAddress().getHostAddress())==null
            ||pairedClient==null||DestinationPolicy.privateIpv4(pairedClient.getHostAddress())==null)throw new IllegalArgumentException("Private LAN listener and paired IPv4 required");
        this.listener=listener;this.pairedClient=pairedClient;this.route=route;this.budget=budget;this.events=events;
        authorization=ConnectRequest.authorization(token);
    }
    public void start(){
        timer.scheduleWithFixedDelay(new Runnable(){public void run(){if(budget.expired()||budget.connectionLimitReached())stop("Session limit reached");}},1,1,TimeUnit.SECONDS);
        Thread thread=new Thread(new Runnable(){public void run(){acceptLoop();}},"compset-accept");thread.start();
    }
    private void acceptLoop(){
        try{while(!closed.get()){
            final Socket client=listener.accept();
            if(!(client instanceof SSLSocket)||!pairedClient.equals(client.getInetAddress())||!budget.open()){quietClose(client);continue;}
            sockets.add(client);
            try{workers.execute(new Runnable(){public void run(){serve((SSLSocket)client);}});}
            catch(RuntimeException unavailable){sockets.remove(client);quietClose(client);budget.closed();}
        }}catch(IOException failure){if(!closed.get())stop("Listener stopped; start again explicitly after checking the network");}
    }
    private void serve(final SSLSocket client){
        Socket upstream=null;Future<?> pump=null;
        java.util.concurrent.ScheduledFuture<?> deadline=null;
        boolean established=false;
        try{
            client.setSoTimeout(10000);client.setTcpNoDelay(true);client.startHandshake();
            final ConnectRequest request=ConnectRequest.read(client.getInputStream(),authorization);
            if(closed.get()||budget.expired())throw new IOException("Session ended");
            Future<InetAddress[]> dns=resolver.submit(new java.util.concurrent.Callable<InetAddress[]>(){
                public InetAddress[] call()throws IOException{return route.resolve(request.host);}});
            InetAddress[] addresses;
            try{addresses=dns.get(5000,TimeUnit.MILLISECONDS);}catch(Exception failed){dns.cancel(true);throw new IOException("DNS unavailable");}
            if(!DestinationPolicy.allPublic(addresses))throw new ConnectRequest.Rejected(403);
            // Do not retry with another route/IP on failure. Rebinding cannot trigger a second hostname lookup.
            upstream=route.socket();
            sockets.add(upstream);
            if(closed.get()||budget.expired())throw new IOException("Session ended");
            upstream.connect(new InetSocketAddress(addresses[0],443),10000);
            upstream.setSoTimeout(20000);upstream.setTcpNoDelay(true);client.setSoTimeout(20000);
            final Socket target=upstream;
            deadline=timer.schedule(new Runnable(){public void run(){quietClose(client);quietClose(target);}},120,TimeUnit.SECONDS);
            client.getOutputStream().write("HTTP/1.1 200 Connection Established\r\n\r\n".getBytes(StandardCharsets.US_ASCII));client.getOutputStream().flush();
            established=true;
            pump=reverse.submit(new Runnable(){public void run(){try{copy(target.getInputStream(),client.getOutputStream());}catch(IOException ignored){}
                finally{quietClose(client);quietClose(target);}}});
            copy(client.getInputStream(),upstream.getOutputStream());
        }catch(ConnectRequest.Rejected rejected){
            if(rejected.status==407&&budget.authFailed())stop("Pairing failed repeatedly; stopped");
            if(!established)respond(client,rejected.status);
        }catch(Exception failed){if(!established&&!closed.get())respond(client,502);}
        finally{
            if(deadline!=null)deadline.cancel(false);if(pump!=null)pump.cancel(true);
            quietClose(client);quietClose(upstream);sockets.remove(client);if(upstream!=null)sockets.remove(upstream);budget.closed();
        }
    }
    private void copy(InputStream input,OutputStream output)throws IOException{
        byte[] buffer=new byte[8192];
        while(!closed.get()){int count=input.read(buffer);if(count<0)return;
            if(!budget.transfer(count)){stop("Traffic or session limit reached");throw new IOException("Budget exhausted");}
            output.write(buffer,0,count);output.flush();}
    }
    private static void respond(Socket client,int code){try{
        String extra=code==407?"Proxy-Authenticate: Basic realm=\"CompSet paired gateway\"\r\n":"";
        client.getOutputStream().write(("HTTP/1.1 "+code+" Request rejected\r\n"+extra+"Connection: close\r\nContent-Length: 0\r\n\r\n").getBytes(StandardCharsets.US_ASCII));
        client.getOutputStream().flush();}catch(IOException ignored){}
    }
    public void stop(String reason){
        if(!closed.compareAndSet(false,true))return;budget.stop();quietClose(listener);
        synchronized(sockets){for(Socket socket:new ArrayList<Socket>(sockets))quietClose(socket);sockets.clear();}
        workers.shutdownNow();reverse.shutdownNow();resolver.shutdownNow();timer.shutdownNow();events.stopped(reason);
    }
    @Override public void close(){stop("Stopped by user");}
    private static void quietClose(Closeable item){if(item!=null)try{item.close();}catch(IOException ignored){}}
}
