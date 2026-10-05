import com.compset.gateway.core.*;
import java.net.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

/** Independent DNS64 review. Numeric fixtures and fake sockets only: no network or device calls. */
public final class Nat64ReviewerProof {
    private static int checks;
    private static void check(boolean value,String reason){checks++;if(!value)throw new AssertionError(reason);}
    private static InetAddress v4(int a,int b,int c,int d)throws Exception{
        return InetAddress.getByAddress(new byte[]{(byte)a,(byte)b,(byte)c,(byte)d});
    }
    private static byte[] prefix(int first,int second,int third){
        byte[] bytes=new byte[16];int[] words={first,second,third};
        for(int i=0;i<words.length;i++){bytes[2*i]=(byte)(words[i]>>>8);bytes[2*i+1]=(byte)words[i];}
        return bytes;
    }
    private static InetAddress translated(byte[] prefix,InetAddress a)throws Exception{
        byte[] bytes=prefix.clone();System.arraycopy(a.getAddress(),0,bytes,12,4);
        return Inet6Address.getByAddress(null,bytes,-1);
    }
    private static void rejected(InetAddress[] answers,byte[] prefix,int bits,String reason){
        InetAddress[] result=Nat64Duplicates.filter(answers,prefix,bits);
        check(result==null,reason);
        check(!DestinationPolicy.allPublic(result),reason+" remains denied at tunnel gate");
    }
    private static void retained(InetAddress[] answers,byte[] prefix,int bits,InetAddress[] expected,String reason){
        InetAddress[] snapshot=answers.clone();byte[] prefixSnapshot=prefix==null?null:prefix.clone();
        InetAddress[] result=Nat64Duplicates.filter(answers,prefix,bits);
        check(result!=null&&result.length==expected.length,reason+" count");
        for(int i=0;i<expected.length;i++)check(result[i]==expected[i],reason+" preserves original object/order");
        check(Arrays.equals(snapshot,answers)&&Arrays.equals(prefixSnapshot,prefix),reason+" no input mutation");
        check(DestinationPolicy.allPublic(result),reason+" output still satisfies original policy");
    }
    private static void cases()throws Exception{
        byte[] wkp=prefix(0x64,0xff9b,0),global=prefix(0x2606,0x4700,0x64);
        InetAddress a=v4(8,8,8,8),b=v4(1,1,1,1),privateA=v4(10,2,3,4);
        InetAddress ta=translated(wkp,a),tb=translated(wkp,b),ga=translated(global,a),gp=translated(global,privateA);
        InetAddress native6=Inet6Address.getByAddress(null,new byte[]{0x26,0x06,0x47,0,0x47,0,0,0,0,0,0,0,0,0,0x11,0x11},-1);
        check(DestinationPolicy.isPublic(ga)&&DestinationPolicy.isPublic(gp),"Global translated fixtures pass plain public check");
        retained(new InetAddress[]{tb,b,ta,native6,a,b},wkp,96,new InetAddress[]{b,native6,a,b},"Interleaved translations");
        retained(new InetAddress[]{ga,a,b},global,96,new InetAddress[]{a,b},"Advertised global duplicate");
        retained(new InetAddress[]{a,native6,b},null,-1,new InetAddress[]{a,native6,b},"No prefix ordinary native results");
        retained(new InetAddress[]{a,native6,b},wkp,64,new InetAddress[]{a,native6,b},"Unsupported but nonmatching prefix");
        rejected(new InetAddress[]{gp,a},global,96,"Global prefix embedded private without A");
        rejected(new InetAddress[]{gp,privateA,a},global,96,"Private A cannot authorize global translation");
        rejected(new InetAddress[]{ga,b},global,96,"Global prefix unmatched public target");
        rejected(new InetAddress[]{ga},global,96,"No IPv4 synthesis from global translated-only result");
        rejected(new InetAddress[]{ta},wkp,96,"No IPv4 synthesis from well-known translated-only result");
        rejected(new InetAddress[]{ta,a,tb},wkp,96,"One valid duplicate cannot hide unmatched translation");
        rejected(new InetAddress[]{ta,a},global,96,"Unadvertised well-known prefix remains blocked");
        rejected(new InetAddress[]{ta,a},null,-1,"Absent prefix grants no exemption");
        rejected(new InetAddress[]{ga,a},global,64,"Unsupported global prefix must not fall back to public check");
        for(InetAddress unsafe:new InetAddress[]{privateA,v4(100,64,0,1),v4(169,254,169,254),v4(127,0,0,1),v4(198,18,0,1),v4(224,0,0,1),Inet6Address.getByAddress(null,new byte[]{(byte)0xfd,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1},-1)}){
            rejected(new InetAddress[]{ta,a,unsafe},wkp,96,"Late unsafe native cannot be filtered away");
        }
        rejected(new InetAddress[]{ta,a,null},wkp,96,"Late null cannot be filtered away");
        rejected(null,wkp,96,"Null answer array");rejected(new InetAddress[0],wkp,96,"Empty answer array");
        rejected(new InetAddress[]{a},null,96,"Missing prefix bytes");
        rejected(new InetAddress[]{a},new byte[4],32,"IPv4 prefix is malformed");
        rejected(new InetAddress[]{a},wkp,-1,"Present prefix with absent length");
        rejected(new InetAddress[]{a},wkp,129,"Out-of-range prefix");
        byte[] dirty=wkp.clone();dirty[12]=8;rejected(new InetAddress[]{ta,a},dirty,96,"Noncanonical prefix bytes");
        InetAddress[] original=new InetAddress[16],eight=new InetAddress[8];
        for(int i=0;i<8;i++){eight[i]=v4(8,8,4,i+1);original[i]=translated(wkp,eight[i]);original[i+8]=eight[i];}
        retained(original,wkp,96,eight,"Observed eight-A eight-DNS64 shape");
        InetAddress[] over=Arrays.copyOf(original,17);over[16]=a;rejected(over,wkp,96,"Original cardinality cap before collapse");
        for(int trial=0;trial<32;trial++){
            List<InetAddress> shuffled=new ArrayList<>(Arrays.asList(original));Collections.shuffle(shuffled,new Random(9028+trial));
            List<InetAddress> expected=new ArrayList<>();for(InetAddress item:shuffled)if(item.getAddress().length==4)expected.add(item);
            retained(shuffled.toArray(new InetAddress[0]),wkp,96,expected.toArray(new InetAddress[0]),"Order permutation "+trial);
        }
    }
    private static void tunnel(InetAddress[] original,byte[] prefix,int bits,boolean accepted)throws Exception{
        GatewayReviewerProof.FakeClient client=new GatewayReviewerProof.FakeClient();
        AtomicInteger dnsCalls=new AtomicInteger(),socketCalls=new AtomicInteger();
        SessionBudget budget=new SessionBudget(()->System.nanoTime()/1000000L,10000,100000,10,1);
        TunnelServer server=new TunnelServer(new GatewayReviewerProof.FakeListener(Collections.singletonList(client)),GatewayReviewerProof.CLIENT,new TunnelServer.Route(){
            public InetAddress[] resolve(String host){dnsCalls.incrementAndGet();return Nat64Duplicates.filter(original,prefix,bits);}
            public Socket socket(){socketCalls.incrementAndGet();return new GatewayReviewerProof.FakeTarget(new CountDownLatch(1));}
        },budget,GatewayReviewerProof.TOKEN,reason->{});
        try{
            server.start();String wanted=accepted?"UPSTREAM_REPLY":"HTTP/1.1 403";
            long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(3);
            while(!client.output.toString("US-ASCII").contains(wanted)&&System.nanoTime()<deadline)Thread.sleep(5);
            check(client.output.toString("US-ASCII").contains(wanted),"Tunnel returns expected bounded response");
            check(dnsCalls.get()==1,"Exactly one resolution and no retry");
            check(socketCalls.get()==(accepted?1:0),"Rejected batch never creates upstream socket");
        }finally{server.close();}
    }
    public static void main(String[] args)throws Exception{
        cases();
        byte[] wkp=prefix(0x64,0xff9b,0),global=prefix(0x2606,0x4700,0x64);
        InetAddress a=GatewayReviewerProof.PUBLIC,privateA=v4(10,2,3,4),b=v4(1,1,1,1);
        tunnel(new InetAddress[]{translated(wkp,a),a},wkp,96,true);
        tunnel(new InetAddress[]{translated(wkp,a),a,privateA},wkp,96,false);
        tunnel(new InetAddress[]{translated(global,privateA),a},global,96,false);
        tunnel(new InetAddress[]{translated(global,b),a},global,96,false);
        tunnel(new InetAddress[]{translated(global,a),a},global,64,false);
        tunnel(new InetAddress[]{translated(wkp,a),a,null},wkp,96,false);
        System.out.println("Independent DNS64 checks passed: "+checks+"; fake tunnel cases: 6");
    }
}
