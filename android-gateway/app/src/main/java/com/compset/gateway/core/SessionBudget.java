package com.compset.gateway.core;

/** Monotonic finite session, concurrency, connection and aggregate-byte bounds. */
public final class SessionBudget {
    public interface Clock { long nowMillis(); }
    private final Clock clock;private final long deadline,maxBytes;private final int maxConnections,maxConcurrent;
    private long bytes;private int opened,active,authFailures;private boolean stopped;
    public SessionBudget(Clock clock,long durationMillis,long maxBytes,int maxConnections,int maxConcurrent){
        if(durationMillis<=0 || durationMillis>86400000L || maxBytes<=0 || maxBytes>17179869184L
            || maxConnections<1 || maxConnections>10000 || maxConcurrent<1 || maxConcurrent>4
            || clock.nowMillis()<0 || clock.nowMillis()>Long.MAX_VALUE-durationMillis)throw new IllegalArgumentException("Invalid session limits");
        this.clock=clock;deadline=clock.nowMillis()+durationMillis;this.maxBytes=maxBytes;
        this.maxConnections=maxConnections;this.maxConcurrent=maxConcurrent;
    }
    public synchronized boolean open(){if(expired()||active>=maxConcurrent||opened>=maxConnections)return false;opened++;active++;return true;}
    public synchronized void closed(){if(active>0)active--;}
    public synchronized boolean transfer(int count){if(count<0||expired()||count>maxBytes-bytes)return false;bytes+=count;return true;}
    public synchronized boolean authFailed(){authFailures++;if(authFailures>=8)stopped=true;return stopped;}
    public synchronized boolean expired(){return stopped||clock.nowMillis()>=deadline||bytes>=maxBytes;}
    public synchronized boolean connectionLimitReached(){return opened>=maxConnections&&active==0;}
    public synchronized void stop(){stopped=true;}
    public synchronized long transferredBytes(){return bytes;}
    public synchronized int openedConnections(){return opened;}
    public synchronized int activeConnections(){return active;}
}
