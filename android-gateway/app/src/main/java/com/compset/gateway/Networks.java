package com.compset.gateway;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.LinkAddress;
import android.net.LinkProperties;
import android.net.Network;
import android.net.NetworkCapabilities;
import java.net.InetAddress;
import java.util.ArrayList;
import java.util.List;
import com.compset.gateway.core.DestinationPolicy;

final class Networks {
    static final class Entry {
        final Network network;final String label;final boolean cellular;
        Entry(Network n,String label,boolean cell){network=n;this.label=label;cellular=cell;}
        @Override public String toString(){return label;}
    }
    static final class Lan {
        final Network network;final InetAddress address;final int prefix;
        Lan(Network n,InetAddress a,int p){network=n;address=a;prefix=p;}
    }
    static ConnectivityManager manager(Context context){return (ConnectivityManager)context.getSystemService(Context.CONNECTIVITY_SERVICE);}
    static List<Entry> available(Context context){
        ConnectivityManager manager=manager(context);List<Entry> entries=new ArrayList<Entry>();
        for(Network network:manager.getAllNetworks()){
            NetworkCapabilities caps=manager.getNetworkCapabilities(network);
            if(caps==null||!caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)||caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN))continue;
            boolean wifi=caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI),cell=caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR);
            if(!wifi&&!cell)continue;
            String label=(cell?"Cellular":"Wi-Fi")+" · network "+network.getNetworkHandle()+" · "+(caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)?"validated":"not validated");
            entries.add(new Entry(network,label,cell));
        }return entries;
    }
    static Network find(Context context,long handle){for(Entry entry:available(context))if(entry.network.getNetworkHandle()==handle)return entry.network;return null;}
    static Lan lan(Context context){
        ConnectivityManager manager=manager(context);
        for(Network network:manager.getAllNetworks()){
            NetworkCapabilities caps=manager.getNetworkCapabilities(network);LinkProperties links=manager.getLinkProperties(network);
            if(caps==null||links==null||!caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)||caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN))continue;
            for(LinkAddress link:links.getLinkAddresses())if(DestinationPolicy.privateIpv4(link.getAddress().getHostAddress())!=null)
                return new Lan(network,link.getAddress(),link.getPrefixLength());
        }return null;
    }
}
