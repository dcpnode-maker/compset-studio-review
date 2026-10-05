package com.compset.gateway;

import android.app.*;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.net.*;
import android.os.*;
import java.net.*;
import javax.net.ssl.SSLServerSocket;
import com.compset.gateway.core.*;

/** Manual foreground lifetime. No boot receiver, sticky restart or fallback route. */
public final class GatewayService extends Service {
    static final String START="com.compset.gateway.START",STOP="com.compset.gateway.STOP";
    static volatile String status="Stopped",endpoint="";
    static volatile boolean running=false;
    static volatile SessionBudget currentBudget;
    private static final java.util.concurrent.atomic.AtomicInteger generations=new java.util.concurrent.atomic.AtomicInteger();
    private int generation;
    private volatile boolean ending;
    private volatile TunnelServer server;
    private volatile SSLServerSocket listener;
    private final Object lifecycle=new Object();
    private long sessionMillis=3600000L,maxBytes=67108864L;private int tunnelLimit=120;
    private ConnectivityManager.NetworkCallback monitor,cellRequest;
    private PowerManager.WakeLock wakeLock;
    private final Handler main=new Handler(Looper.getMainLooper());
    @Override public IBinder onBind(Intent intent){return null;}
    @Override public int onStartCommand(Intent intent,int flags,int id){
        if(intent==null||STOP.equals(intent.getAction())){finish("Stopped by user");return START_NOT_STICKY;}
        if(!START.equals(intent.getAction())||running)return START_NOT_STICKY;
        generation=generations.incrementAndGet();ending=false;running=true;status="Starting encrypted gateway";
        final long handle=intent.getLongExtra("networkHandle",-1);
        final String paired=intent.getStringExtra("pairedClient");
        sessionMillis=intent.getLongExtra("sessionMillis",3600000L);maxBytes=intent.getLongExtra("maxBytes",67108864L);tunnelLimit=intent.getIntExtra("tunnelLimit",120);
        Notification notification=notification();
        if(Build.VERSION.SDK_INT>=34)startForeground(10,notification,ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        else startForeground(10,notification);
        new Thread(new Runnable(){public void run(){startGateway(handle,paired);}},"compset-start").start();
        return START_NOT_STICKY;
    }
    private void startGateway(long handle,String paired){
        try{
            final javax.net.ssl.SSLContext tls=Pairing.tlsContext();
            synchronized(lifecycle){
            if(ending)return;
            currentBudget=new SessionBudget(new SessionBudget.Clock(){public long nowMillis(){return SystemClock.elapsedRealtime();}},sessionMillis,maxBytes,tunnelLimit,2);
            final Network route=Networks.find(this,handle);final Networks.Lan lan=Networks.lan(this);
            InetAddress client=DestinationPolicy.privateIpv4(paired);
            if(route==null){finish("Selected network is no longer available");return;}
            if(lan==null||client==null||!DestinationPolicy.sameSubnet(lan.address,client,lan.prefix)||client.equals(lan.address)){
                finish("Pair a different desktop IPv4 on the same private Wi-Fi subnet");return;}
            if(Build.VERSION.SDK_INT>=37&&checkSelfPermission("android.permission.ACCESS_LOCAL_NETWORK")!=android.content.pm.PackageManager.PERMISSION_GRANTED){finish("Local network permission is required");return;}
            listener=(SSLServerSocket)tls.getServerSocketFactory().createServerSocket();
            listener.setEnabledProtocols(new String[]{"TLSv1.2"});listener.setReuseAddress(true);
            listener.bind(new InetSocketAddress(lan.address,8443),4);
            if(ending){listener.close();return;}
            final ConnectivityManager manager=Networks.manager(this);
            monitor=new ConnectivityManager.NetworkCallback(){@Override public void onLost(Network n){if(n.equals(route)||n.equals(lan.network))finish("Selected network lost; start again explicitly");}};
            manager.registerNetworkCallback(new NetworkRequest.Builder().build(),monitor);
            NetworkCapabilities caps=manager.getNetworkCapabilities(route);
            if(caps!=null&&caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR)){
                cellRequest=new ConnectivityManager.NetworkCallback(){};
                manager.requestNetwork(new NetworkRequest.Builder().addTransportType(NetworkCapabilities.TRANSPORT_CELLULAR).addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET).build(),cellRequest);
            }
            PowerManager power=(PowerManager)getSystemService(POWER_SERVICE);wakeLock=power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,"CompSet:Gateway");wakeLock.acquire(sessionMillis+5000L);
            server=new TunnelServer(listener,client,new TunnelServer.Route(){
                public InetAddress[] resolve(String host)throws java.io.IOException{
                    InetAddress[] answers=route.getAllByName(host);
                    IpPrefix nat64=null;
                    if(Build.VERSION.SDK_INT>=30){LinkProperties links=manager.getLinkProperties(route);if(links!=null)nat64=links.getNat64Prefix();}
                    InetAddress[] accepted=Nat64Duplicates.filter(answers,nat64==null?null:nat64.getRawAddress(),nat64==null?-1:nat64.getPrefixLength());
                    if("httpbin.org".equals(host))dnsDiagnostics(answers,nat64,accepted);
                    return accepted;
                }
                public Socket socket()throws java.io.IOException{
                    Socket socket=new Socket();try{route.bindSocket(socket);return socket;}
                    catch(java.io.IOException failed){try{socket.close();}catch(java.io.IOException ignored){}throw failed;}
                }
            },currentBudget,Pairing.token(this),new TunnelServer.Events(){public void stopped(String reason){finish(reason);}});
            if(ending){server.close();return;}
            endpoint="https://"+lan.address.getHostAddress()+":8443";status="Running · selected network "+route.getNetworkHandle();server.start();
            }
        }catch(Exception failed){finish("Gateway could not start; check permissions, Wi-Fi and pairing certificate");}
    }
    private static void dnsDiagnostics(InetAddress[] answers,IpPrefix nat64,InetAddress[] accepted){
        try{
            int nulls=0,publicV4=0,publicV6=0,rejectedV4=0,rejectedV6=0,nat64Matches=0;
            if(answers!=null)for(InetAddress address:answers){
                if(address==null){nulls++;continue;}
                boolean v4=address.getAddress().length==4;
                if(DestinationPolicy.isPublic(address)){if(v4)publicV4++;else publicV6++;}
                else{if(v4)rejectedV4++;else rejectedV6++;}
                if(nat64!=null&&nat64.contains(address))nat64Matches++;
            }
            // Fixed neutral-target diagnostics only; no address, prefix, credential or request data.
            android.util.Log.i("CompSetDNS","total="+(answers==null?0:answers.length)+" nulls="+nulls
                +" accepted_v4="+publicV4+" accepted_v6="+publicV6+" rejected_v4="+rejectedV4+" rejected_v6="+rejectedV6
                +" over_limit="+(answers!=null&&answers.length>16)+" all_public="+DestinationPolicy.allPublic(answers)
                +" nat64_prefix_present="+(nat64!=null)+" nat64_matches="+nat64Matches
                +" accepted_native_count="+(accepted==null?0:accepted.length));
        }catch(RuntimeException unavailable){android.util.Log.i("CompSetDNS","diagnostic_unavailable");}
    }
    private Notification notification(){
        String channel="gateway";
        if(Build.VERSION.SDK_INT>=26){NotificationChannel c=new NotificationChannel(channel,"Active gateway",NotificationManager.IMPORTANCE_LOW);((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).createNotificationChannel(c);}
        Notification.Builder builder=Build.VERSION.SDK_INT>=26?new Notification.Builder(this,channel):new Notification.Builder(this);
        PendingIntent stop=PendingIntent.getService(this,1,new Intent(this,GatewayService.class).setAction(STOP),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        PendingIntent open=PendingIntent.getActivity(this,2,new Intent(this,MainActivity.class),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        return builder.setSmallIcon(android.R.drawable.stat_sys_upload).setContentTitle("CompSet gateway is active")
            .setContentText("Paired desktop · "+(sessionMillis/60000)+" min / "+(maxBytes/1048576)+" MiB limit").setContentIntent(open).setOngoing(true)
            .addAction(android.R.drawable.ic_media_pause,"Stop",stop).build();
    }
    private synchronized void finish(final String reason){if(ending)return;ending=true;if(generation==generations.get())status=reason;main.post(new Runnable(){public void run(){stopSelf();}});}
    @Override public void onDestroy(){
        if(!ending&&generation==generations.get())status="Stopped";ending=true;
        synchronized(lifecycle){
        if(server!=null)server.close();else if(listener!=null)try{listener.close();}catch(Exception ignored){}
        if(currentBudget!=null)currentBudget.stop();
        ConnectivityManager manager=Networks.manager(this);
        if(monitor!=null)try{manager.unregisterNetworkCallback(monitor);}catch(Exception ignored){}
        if(cellRequest!=null)try{manager.unregisterNetworkCallback(cellRequest);}catch(Exception ignored){}
        if(wakeLock!=null&&wakeLock.isHeld())wakeLock.release();
        if(generation==generations.get()){running=false;endpoint="";}
        }
        stopForeground(true);super.onDestroy();
    }
}
