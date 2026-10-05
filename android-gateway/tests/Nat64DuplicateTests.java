package com.compset.gateway.core;

import java.net.InetAddress;
import java.util.Arrays;

/** Numeric fixtures only: this proof performs no DNS or network operations. */
public final class Nat64DuplicateTests {
    private static int checks;
    private static void check(boolean value,String message){checks++;if(!value)throw new AssertionError(message);}
    private static InetAddress v4(int a,int b,int c,int d)throws Exception{return InetAddress.getByAddress(new byte[]{(byte)a,(byte)b,(byte)c,(byte)d});}
    private static InetAddress v6(int... words)throws Exception{
        byte[] bytes=new byte[16];for(int i=0;i<8;i++){bytes[i*2]=(byte)(words[i]>>8);bytes[i*2+1]=(byte)words[i];}
        return InetAddress.getByAddress(bytes);
    }
    private static InetAddress translated(byte[] prefix,InetAddress nativeV4)throws Exception{
        byte[] bytes=prefix.clone();System.arraycopy(nativeV4.getAddress(),0,bytes,12,4);return InetAddress.getByAddress(bytes);
    }
    private static void rejects(InetAddress[] original,byte[] prefix,int length,String reason){check(Nat64Duplicates.filter(original,prefix,length)==null,reason);}
    private static void same(InetAddress[] result,InetAddress[] expected,String reason){
        check(result!=null&&result.length==expected.length,reason+" length");
        if(result!=null&&result.length==expected.length)for(int i=0;i<result.length;i++)check(result[i]==expected[i],reason+" identity/order");
    }
    public static int run()throws Exception{
        checks=0;
        InetAddress a=v4(8,8,8,8),b=v4(1,1,1,1),privateA=v4(10,1,2,3);
        InetAddress nativeV6=v6(0x2001,0x4860,0x4860,0,0,0,0,0x8888);
        byte[] wellKnown=v6(0x64,0xff9b,0,0,0,0,0,0).getAddress();
        byte[] global=v6(0x2606,0x4700,0x64,0,0,0,0,0).getAddress();
        InetAddress ta=translated(wellKnown,a),tb=translated(wellKnown,b);
        InetAddress ga=translated(global,a),gp=translated(global,privateA);

        same(Nat64Duplicates.filter(new InetAddress[]{a,nativeV6,b},null,-1),new InetAddress[]{a,nativeV6,b},"No advertised prefix preserves public native answers");
        same(Nat64Duplicates.filter(new InetAddress[]{ta,a,nativeV6,tb,b,a},wellKnown,96),new InetAddress[]{a,nativeV6,b,a},"Translated duplicates removed without deduplicating/reordering natives");
        check(DestinationPolicy.isPublic(ga)&&DestinationPolicy.isPublic(gp),"Global translation fixtures would pass ordinary IPv6 policy");
        same(Nat64Duplicates.filter(new InetAddress[]{ga,a},global,96),new InetAddress[]{a},"Global advertised prefix classified before public test");
        rejects(new InetAddress[]{ga,b},global,96,"Global translation missing exact same-response A rejected");
        rejects(new InetAddress[]{gp,a},global,96,"Global translation with private embedded address rejected");
        rejects(new InetAddress[]{gp,privateA},global,96,"Matching private A does not authorize translation");
        rejects(new InetAddress[]{ga},global,96,"Global translated IPv6-only response rejected");
        rejects(new InetAddress[]{ta},wellKnown,96,"Well-known translated IPv6-only response rejected");
        rejects(new InetAddress[]{ta,b},wellKnown,96,"Matching A cannot come from another response");
        rejects(new InetAddress[]{ta,a,privateA},wellKnown,96,"Private native A remains fatal after valid duplicate");
        rejects(new InetAddress[]{a,ga,privateA},global,96,"Private native A remains fatal for global prefix");
        rejects(new InetAddress[]{ta,a,tb},wellKnown,96,"One unmatched translation rejects whole response");
        rejects(new InetAddress[]{ta,a},null,-1,"No advertised prefix cannot exempt DNS64 answers");
        rejects(new InetAddress[]{ta,a},global,96,"Different prefix cannot exempt DNS64 answers");

        InetAddress[] sixteen=new InetAddress[16];
        InetAddress[] expected=new InetAddress[8];
        for(int i=0;i<8;i++){expected[i]=v4(8,8,8,i+1);sixteen[i]=expected[i];sixteen[i+8]=translated(wellKnown,expected[i]);}
        same(Nat64Duplicates.filter(sixteen,wellKnown,96),expected,"Observed sixteen-answer shape retains eight native answers");
        InetAddress[] seventeen=Arrays.copyOf(sixteen,17);seventeen[16]=a;
        rejects(seventeen,wellKnown,96,"Original bound applies before duplicates collapse");
        rejects(null,wellKnown,96,"Null response");
        rejects(new InetAddress[0],wellKnown,96,"Empty response");
        rejects(new InetAddress[]{a,null,ta},wellKnown,96,"Null member before collapse");

        for(InetAddress invalid:new InetAddress[]{privateA,v4(127,0,0,1),v4(169,254,169,254),v4(100,64,0,1),v4(203,0,113,1),v4(224,0,0,1),v6(0,0,0,0,0,0,0,1),v6(0xfc00,0,0,0,0,0,0,1),v6(0x2001,0xdb8,0,0,0,0,0,1)}){
            rejects(new InetAddress[]{a,invalid},null,-1,"Unsafe native address rejected without prefix");
            rejects(new InetAddress[]{a,ta,invalid},wellKnown,96,"Unsafe native address cannot disappear with duplicate collapse");
        }

        // Unsupported advertised lengths must reject matching addresses even inside 2000::/3.
        for(int length:new int[]{0,32,40,48,56,64,95,97,128}){
            byte[] prefix=ga.getAddress().clone();
            for(int bit=length;bit<128;bit++)prefix[bit/8]&=(byte)~(1<<(7-bit%8));
            rejects(new InetAddress[]{a,ga},prefix,length,"Unsupported matching prefix /"+length);
            same(Nat64Duplicates.filter(new InetAddress[]{a,b},prefix,length),new InetAddress[]{a,b},"Unsupported prefix without any matching answer /"+length);
        }
        same(Nat64Duplicates.filter(new InetAddress[]{a,nativeV6},global,64),new InetAddress[]{a,nativeV6},"Unsupported nonmatching global prefix does not reject ordinary native IPv6");
        same(Nat64Duplicates.filter(new InetAddress[]{a,nativeV6},wellKnown,96),new InetAddress[]{a,nativeV6},"Supported prefix with no translations preserves ordinary public answers");

        rejects(new InetAddress[]{a},null,96,"Absent prefix with present length is invalid");
        rejects(new InetAddress[]{a},null,0,"Absent prefix requires unambiguous sentinel");
        rejects(new InetAddress[]{a},new byte[4],32,"IPv4 prefix invalid");
        rejects(new InetAddress[]{a},new byte[0],0,"Empty prefix invalid");
        rejects(new InetAddress[]{a},wellKnown,-1,"Present prefix with absent length invalid");
        rejects(new InetAddress[]{a},wellKnown,129,"Out-of-range prefix length invalid");
        byte[] dirty=wellKnown.clone();dirty[15]=1;
        rejects(new InetAddress[]{a,ta},dirty,96,"Noncanonical prefix input invalid");
        byte[] odd=global.clone();odd[11]=1;
        rejects(new InetAddress[]{a},odd,95,"Noncanonical partial byte invalid");
        InetAddress[] original={ta,a,nativeV6};InetAddress[] originalCopy=original.clone();byte[] prefixCopy=wellKnown.clone();
        Nat64Duplicates.filter(original,wellKnown,96);
        check(Arrays.equals(original,originalCopy)&&Arrays.equals(wellKnown,prefixCopy),"Caller arrays are not mutated");
        check(DestinationPolicy.allPublic(Nat64Duplicates.filter(sixteen,wellKnown,96)),"Retained result still passes existing policy gate");
        return checks;
    }
}
