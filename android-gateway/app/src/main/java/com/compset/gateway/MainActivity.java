package com.compset.gateway;

import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.*;
import android.os.*;
import android.view.View;
import android.view.WindowManager;
import android.widget.*;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import com.compset.gateway.core.SessionBudget;

/** Native widgets only: user chooses the route, pairs the desktop, then starts. */
public final class MainActivity extends Activity {
    private final Handler handler=new Handler(Looper.getMainLooper());
    private TextView state,lanLabel,pairing;private EditText client;private Spinner routes;
    private Spinner duration,traffic,tunnels;
    private final long[] durations={3600000L,14400000L,43200000L,86400000L};
    private final long[] trafficLimits={67108864L,268435456L,1073741824L,4294967296L,17179869184L};
    private final int[] tunnelLimits={120,500,2000,10000};
    private Button start,stop,show,rotate;private String fingerprint;private boolean revealed;
    private List<Networks.Entry> entries=new ArrayList<Networks.Entry>();
    private ConnectivityManager.NetworkCallback cellRequest;
    private final Runnable update=new Runnable(){public void run(){renderStatus();handler.postDelayed(this,1000);}};
    @Override public void onCreate(Bundle saved){
        super.onCreate(saved);final ScrollView scroll=new ScrollView(this);LinearLayout layout=new LinearLayout(this);layout.setOrientation(LinearLayout.VERTICAL);layout.setPadding(dp(20),dp(16),dp(20),dp(24));scroll.addView(layout);setContentView(scroll);
        scroll.setOnApplyWindowInsetsListener(new View.OnApplyWindowInsetsListener(){public android.view.WindowInsets onApplyWindowInsets(View view,android.view.WindowInsets insets){
            view.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());return insets.consumeSystemWindowInsets();
        }});scroll.requestApplyInsets();
        TextView title=text(layout,"CompSet Gateway",26);title.setTypeface(null,android.graphics.Typeface.BOLD);
        text(layout,"Your phone, your selected network. An encrypted gateway for one paired desktop on private Wi-Fi.",15);
        state=text(layout,"Stopped",18);lanLabel=text(layout,"",14);
        text(layout,"Outbound network",16);routes=new Spinner(this);layout.addView(routes);
        button(layout,"Refresh available networks",new View.OnClickListener(){public void onClick(View view){refreshNetworks();}});
        button(layout,"Request cellular connection",new View.OnClickListener(){public void onClick(View view){requestCellular();}});
        text(layout,"Only networks Android currently exposes are shown. This does not switch the default SIM or guarantee two simultaneous SIM routes.",13);
        text(layout,"Paired desktop IPv4 (same Wi-Fi subnet)",16);client=new EditText(this);client.setSingleLine(true);client.setInputType(android.text.InputType.TYPE_CLASS_PHONE);client.setHint("192.168.1.20");
        client.setText(getPreferences(MODE_PRIVATE).getString("client",""));layout.addView(client);
        pairing=text(layout,"Generating local pairing certificate…",13);pairing.setTextIsSelectable(true);
        show=button(layout,"Show pairing details",new View.OnClickListener(){public void onClick(View view){revealed=!revealed;showPairing();}});
        button(layout,"Export public pairing certificate",new View.OnClickListener(){public void onClick(View view){
            Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("application/x-pem-file").putExtra(Intent.EXTRA_TITLE,"compset-phone-certificate.pem");startActivityForResult(intent,2);}});
        rotate=button(layout,"Reset pairing token",new View.OnClickListener(){public void onClick(View view){if(!GatewayService.running){Pairing.rotateToken(MainActivity.this);showPairing();}}});
        text(layout,"Session limits you control",16);
        duration=choice(layout,new String[]{"60 minutes","4 hours","12 hours","24 hours"});
        traffic=choice(layout,new String[]{"64 MiB traffic","256 MiB traffic","1 GiB traffic","4 GiB traffic","16 GiB traffic"});
        tunnels=choice(layout,new String[]{"120 tunnel connections","500 tunnel connections","2,000 tunnel connections","10,000 tunnel connections"});
        start=button(layout,"Start gateway",new View.OnClickListener(){public void onClick(View view){startGateway();}});
        stop=button(layout,"Stop gateway",new View.OnClickListener(){public void onClick(View view){startService(new Intent(MainActivity.this,GatewayService.class).setAction(GatewayService.STOP));}});
        text(layout,"Two concurrent connections. Each expires after 2 minutes or 20 seconds idle. HTTPS port 443 only. Long sessions use phone battery/data; Android may still interrupt background work. HTTP request counts inside encrypted tunnels are controlled by the desktop collector.",14);
        text(layout,"No automatic start, route fallback, root, VPN or installed interception CA. Destination TLS stays end to end. The desktop must verify the exported certificate and fingerprint before sending the token. Collector source cooldowns remain in force.",13);
        refreshNetworks();new Thread(new Runnable(){public void run(){try{final String fp=Pairing.fingerprint();handler.post(new Runnable(){public void run(){fingerprint=fp;showPairing();}});}catch(Exception failed){handler.post(new Runnable(){public void run(){pairing.setText("Pairing certificate unavailable; gateway cannot start.");}});}}},"compset-pairing").start();
    }
    private int dp(int value){return Math.round(value*getResources().getDisplayMetrics().density);}
    private TextView text(LinearLayout parent,String value,int size){TextView view=new TextView(this);view.setText(value);view.setTextSize(size);view.setPadding(0,dp(8),0,dp(8));parent.addView(view);return view;}
    private Button button(LinearLayout parent,String title,View.OnClickListener listener){Button button=new Button(this);button.setText(title);button.setOnClickListener(listener);parent.addView(button);return button;}
    private Spinner choice(LinearLayout parent,String[] values){Spinner spinner=new Spinner(this);ArrayAdapter<String> adapter=new ArrayAdapter<String>(this,android.R.layout.simple_spinner_item,values);adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);spinner.setAdapter(adapter);parent.addView(spinner);return spinner;}
    private void refreshNetworks(){
        if(GatewayService.running)return;entries=Networks.available(this);ArrayAdapter<Networks.Entry> adapter=new ArrayAdapter<Networks.Entry>(this,android.R.layout.simple_spinner_item,entries);adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);routes.setAdapter(adapter);
        Networks.Lan lan=Networks.lan(this);lanLabel.setText(lan==null?"Connect phone and desktop to private Wi-Fi first.":"Phone LAN address: "+lan.address.getHostAddress()+" · TLS port 8443");
    }
    private void requestCellular(){
        if(GatewayService.running||cellRequest!=null)return;
        cellRequest=new ConnectivityManager.NetworkCallback(){@Override public void onAvailable(Network network){handler.post(new Runnable(){public void run(){refreshNetworks();}});}};
        try{Networks.manager(this).requestNetwork(new NetworkRequest.Builder().addTransportType(NetworkCapabilities.TRANSPORT_CELLULAR).addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET).build(),cellRequest);state.setText("Waiting for Android to expose cellular; refresh the list shortly.");}
        catch(Exception failed){cellRequest=null;state.setText("Cellular request unavailable on this device/network.");}
    }
    private void showPairing(){
        if(revealed){getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);pairing.setText("Username: compset\nToken: "+Pairing.token(this)+"\nCertificate SHA-256:\n"+(fingerprint==null?"Preparing…":fingerprint));}
        else{getWindow().clearFlags(WindowManager.LayoutParams.FLAG_SECURE);pairing.setText(fingerprint==null?"Preparing pairing certificate…":"Pairing ready. Export the certificate and compare its SHA-256 fingerprint on the desktop.");}
        show.setText(revealed?"Hide pairing details":"Show pairing details");
    }
    private void startGateway(){
        if(GatewayService.running||fingerprint==null)return;
        ArrayList<String> needed=new ArrayList<String>();
        if(Build.VERSION.SDK_INT>=33&&checkSelfPermission("android.permission.POST_NOTIFICATIONS")!=PackageManager.PERMISSION_GRANTED)needed.add("android.permission.POST_NOTIFICATIONS");
        if(Build.VERSION.SDK_INT>=37&&checkSelfPermission("android.permission.ACCESS_LOCAL_NETWORK")!=PackageManager.PERMISSION_GRANTED)needed.add("android.permission.ACCESS_LOCAL_NETWORK");
        if(!needed.isEmpty()){requestPermissions(needed.toArray(new String[needed.size()]),1);state.setText("Allow the requested permissions, then tap Start again.");return;}
        int position=routes.getSelectedItemPosition();if(position<0||position>=entries.size()){state.setText("Choose an available outbound network.");return;}
        String paired=client.getText().toString().trim();getPreferences(MODE_PRIVATE).edit().putString("client",paired).apply();
        Intent intent=new Intent(this,GatewayService.class).setAction(GatewayService.START).putExtra("networkHandle",entries.get(position).network.getNetworkHandle()).putExtra("pairedClient",paired)
            .putExtra("sessionMillis",durations[duration.getSelectedItemPosition()]).putExtra("maxBytes",trafficLimits[traffic.getSelectedItemPosition()]).putExtra("tunnelLimit",tunnelLimits[tunnels.getSelectedItemPosition()]);
        try{if(Build.VERSION.SDK_INT>=26)startForegroundService(intent);else startService(intent);}catch(Exception failed){state.setText("Android could not start the foreground gateway.");}
    }
    private void renderStatus(){
        String line=GatewayService.status;SessionBudget budget=GatewayService.currentBudget;
        if(GatewayService.running){line+="\n"+GatewayService.endpoint;if(budget!=null)line+="\nConnections "+budget.activeConnections()+" / opened "+budget.openedConnections()+" · "+budget.transferredBytes()+" bytes";}
        state.setText(line);start.setEnabled(!GatewayService.running&&fingerprint!=null);stop.setEnabled(GatewayService.running);routes.setEnabled(!GatewayService.running);client.setEnabled(!GatewayService.running);rotate.setEnabled(!GatewayService.running);
        duration.setEnabled(!GatewayService.running);traffic.setEnabled(!GatewayService.running);tunnels.setEnabled(!GatewayService.running);
    }
    @Override protected void onActivityResult(int request,int result,Intent data){super.onActivityResult(request,result,data);
        if(request==2&&result==RESULT_OK&&data!=null&&data.getData()!=null){try{OutputStream stream=getContentResolver().openOutputStream(data.getData());if(stream==null)throw new java.io.IOException();try{stream.write(Pairing.certificatePem().getBytes(StandardCharsets.US_ASCII));}finally{stream.close();}Toast.makeText(this,"Public certificate exported; compare fingerprint before pairing.",Toast.LENGTH_LONG).show();}catch(Exception failed){Toast.makeText(this,"Certificate export failed.",Toast.LENGTH_LONG).show();}}
    }
    @Override protected void onResume(){super.onResume();handler.post(update);}
    @Override protected void onPause(){handler.removeCallbacks(update);super.onPause();}
    @Override protected void onDestroy(){if(cellRequest!=null)try{Networks.manager(this).unregisterNetworkCallback(cellRequest);}catch(Exception ignored){}super.onDestroy();}
}
