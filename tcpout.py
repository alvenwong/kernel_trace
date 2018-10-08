#!/usr/bin/env python

from __future__ import print_function
from bcc import BPF
from time import strftime
from socket import inet_ntop, AF_INET, AF_INET6
from struct import pack
import ctypes as ct
from bcc import tcp
import os
import signal
import argparse

# arguments
examples = """examples:
    ./out_probe             # trace all TCP packets
    ./out_porbe -p  5205    # only trace port 5205
    ./out_porbe -dp 5205    # only trace remote port 5205
    ./out_porbe -sp 5205    # only trace local port 5205
    ./out_porbe -s  5       # only trace one packet in every 5 packets
"""

parser = argparse.ArgumentParser(
    description="Trace the duration in TCP, IP and MAC layers",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog=examples)
parser.add_argument("-p", "--port", 
    help="TCP port")
parser.add_argument("-sp", "--sport", 
    help="TCP source port")
parser.add_argument("-dp", "--dport",
    help="TCP destination port")
parser.add_argument("-s", "--sample",
    help="Trace sampling")

args = parser.parse_args()

# define BPF program
bpf_text = """
#include <uapi/linux/ptrace.h>
#define KBUILD_MODNAME "foo"
#include <linux/tcp.h>
#include <linux/ip.h>
#include <uapi/linux/tcp.h>
#include <uapi/linux/ip.h>
#include <net/sock.h>
#include <bcc/proto.h>
#include <linux/skbuff.h>
#include <linux/netdevice.h>
#include <net/tcp.h>
#include <net/ip.h>
#include <net/sch_generic.h>


struct flow_tuple {
    u32 saddr;
    u32 daddr;
    u16 sport;
    u16 dport;
};


struct packet_tuple {
    u32 daddr;
    u16 dport;
    u32 seq;
    u32 ack;
};


struct ktime_info {
    u64 qdisc_time;
    u64 mac_time;
    u64 ip_time;
    u64 tcp_time;
};

struct data_t {
    u64 total_time;
    u64 qdisc_time;
    u64 ip_time;
    u64 tcp_time;
    u32 saddr;
    u32 daddr;
    u32 nat_saddr;
    u16 nat_sport;
    u16 sport;
    u16 dport;
    u32 seq;
    u32 ack;
};

BPF_HASH(flows, struct packet_tuple, struct flow_tuple);
BPF_HASH(out_timestamps, struct packet_tuple, struct ktime_info);
BPF_PERF_OUTPUT(timestamp_events);

static struct tcphdr *skb_to_tcphdr(const struct sk_buff *skb)
{
    // unstable API. verify logic in tcp_hdr() -> skb_transport_header().
    return (struct tcphdr *)(skb->head + skb->transport_header);
}

static inline struct iphdr *skb_to_iphdr(const struct sk_buff *skb)
{
    // unstable API. verify logic in ip_hdr() -> skb_network_header().
    return (struct iphdr *)(skb->head + skb->network_header);
}


int trace_sch_direct_xmit(struct pt_regs *ctx, struct sk_buff *skb)
{
    if (skb == NULL)
        return 0;

    struct iphdr *ip = skb_to_iphdr(skb);
    struct tcphdr *tcp = skb_to_tcphdr(skb);

    struct packet_tuple pkt_tuple = {};
    pkt_tuple.daddr = ip->daddr;
    u16 dport = 0, sport = 0;
    u32 seq = 0, ack = 0;
    dport = tcp->dest;
    sport = tcp->source;
    pkt_tuple.dport = ntohs(dport);
    seq = tcp->seq;
    ack = tcp->ack_seq;
    pkt_tuple.seq = ntohl(seq);
    pkt_tuple.ack = ntohl(ack);

    FILTER_DPORT

    struct flow_tuple *ftuple;
    if((ftuple = flows.lookup(&pkt_tuple)) == NULL)
        return 0;
 
    struct ktime_info *tinfo;
    if ((tinfo = out_timestamps.lookup(&pkt_tuple)) == NULL)
        return 0;
    tinfo->qdisc_time = bpf_ktime_get_ns();
    struct data_t data = {};
    data.total_time = tinfo->qdisc_time - tinfo->tcp_time;
    data.qdisc_time = tinfo->qdisc_time - tinfo->mac_time;
    data.ip_time = tinfo->mac_time - tinfo->ip_time;
    data.tcp_time = tinfo->ip_time - tinfo->tcp_time;
    data.saddr = ftuple->saddr;
    data.daddr = pkt_tuple.daddr;
    data.nat_saddr = ip->saddr;
    data.nat_sport = ntohs(sport);
    data.sport = ftuple->sport;
    data.dport = pkt_tuple.dport;
    data.seq = pkt_tuple.seq;
    data.ack = pkt_tuple.ack;
    
    flows.delete(&pkt_tuple);
    out_timestamps.delete(&pkt_tuple);
    timestamp_events.perf_submit(ctx, &data, sizeof(data));

    return 0;
}


int trace_dev_hard_start_xmit(struct pt_regs *ctx, struct sk_buff *skb)
{
    if (skb == NULL)
        return 0;

    struct iphdr *ip = skb_to_iphdr(skb);
    struct tcphdr *tcp = skb_to_tcphdr(skb);

    struct packet_tuple pkt_tuple = {};
    pkt_tuple.daddr = ip->daddr;
    u16 dport = 0, sport = 0;
    u32 seq = 0, ack = 0;
    dport = tcp->dest;
    sport = tcp->source;
    pkt_tuple.dport = ntohs(dport);
    seq = tcp->seq;
    ack = tcp->ack_seq;
    pkt_tuple.seq = ntohl(seq);
    pkt_tuple.ack = ntohl(ack);

    FILTER_DPORT

    struct flow_tuple *ftuple;
    if((ftuple = flows.lookup(&pkt_tuple)) == NULL)
        return 0;
 
    struct ktime_info *tinfo;
    if ((tinfo = out_timestamps.lookup(&pkt_tuple)) == NULL)
        return 0;
    tinfo->qdisc_time = bpf_ktime_get_ns();
    struct data_t data = {};
    data.total_time = tinfo->qdisc_time - tinfo->tcp_time;
    data.qdisc_time = tinfo->qdisc_time - tinfo->mac_time;
    data.ip_time = tinfo->mac_time - tinfo->ip_time;
    data.tcp_time = tinfo->ip_time - tinfo->tcp_time;
    data.saddr = ftuple->saddr;
    data.daddr = pkt_tuple.daddr;
    data.nat_saddr = ip->saddr;
    data.nat_sport = ntohs(sport);
    data.sport = ftuple->sport;
    data.dport = pkt_tuple.dport;
    data.seq = pkt_tuple.seq;
    data.ack = pkt_tuple.ack;
    
    flows.delete(&pkt_tuple);
    out_timestamps.delete(&pkt_tuple);
    timestamp_events.perf_submit(ctx, &data, sizeof(data));

    return 0;
}


int trace_dev_queue_xmit(struct pt_regs *ctx, struct sk_buff *skb)
{
    if (skb == NULL)
        return 0;

    struct iphdr *ip = skb_to_iphdr(skb);
    struct tcphdr *tcp = skb_to_tcphdr(skb);

    struct packet_tuple pkt_tuple = {};
    pkt_tuple.daddr = ip->daddr;
    u16 dport = 0, sport = 0;
    u32 seq = 0, ack = 0;
    dport = tcp->dest;
    sport = tcp->source;
    pkt_tuple.dport = ntohs(dport);
    seq = tcp->seq;
    ack = tcp->ack_seq;
    pkt_tuple.seq = ntohl(seq);
    pkt_tuple.ack = ntohl(ack);

    FILTER_DPORT
    
    struct ktime_info *tinfo;
    if ((tinfo = out_timestamps.lookup(&pkt_tuple)) == NULL)
        return 0;
    tinfo->mac_time = bpf_ktime_get_ns();

    return 0;
}


int trace_ip_queue_xmit(struct pt_regs *ctx, struct sock *sk, struct sk_buff *skb)
{
    if (skb == NULL)
        return 0;

    u16 family = sk->__sk_common.skc_family;
    if (family == AF_INET) {
        struct packet_tuple pkt_tuple = {};
        u16 dport = 0;
        u32 seq = 0, ack = 0;
        pkt_tuple.daddr = sk->__sk_common.skc_daddr;
        dport = sk->__sk_common.skc_dport;
        pkt_tuple.dport = ntohs(dport);
        struct tcphdr *tcp = skb_to_tcphdr(skb);
        seq = tcp->seq;
        ack = tcp->ack_seq;
        pkt_tuple.seq = ntohl(seq);
        pkt_tuple.ack = ntohl(ack);

        FILTER_DPORT

        struct ktime_info *tinfo;
        if ((tinfo = out_timestamps.lookup(&pkt_tuple)) == NULL)
            return 0;
        tinfo->ip_time = bpf_ktime_get_ns();
    }
    
    return 0;
}

int trace___tcp_transmit_skb(struct pt_regs *ctx, struct sock *sk, struct sk_buff *skb, int clone_it, gfp_t gfp_mask, u32 rcv_nxt)
{
    if (skb == NULL)
        return 0;

    u64 time = bpf_ktime_get_ns();
    SAMPLING

    u16 family = sk->__sk_common.skc_family;
    if (family == AF_INET) {
        struct flow_tuple ftuple = {};
        struct packet_tuple pkt_tuple = {};
        struct tcp_skb_cb *tcb;
        u16 dport = 0;
        ftuple.saddr = sk->__sk_common.skc_rcv_saddr;
        ftuple.daddr = sk->__sk_common.skc_daddr;
        ftuple.sport = sk->__sk_common.skc_num;

        pkt_tuple.daddr = sk->__sk_common.skc_daddr;
        dport = sk->__sk_common.skc_dport;
        pkt_tuple.dport = ntohs(dport);
        ftuple.dport = pkt_tuple.dport;
        tcb = TCP_SKB_CB(skb);
        pkt_tuple.seq = tcb->seq; 
        pkt_tuple.ack = rcv_nxt;

        FILTER_PORT
        FILTER_DPORT
        FILTER_SPORT

        flows.lookup_or_init(&pkt_tuple, &ftuple);
        struct ktime_info *tinfo, zero = {};

        if ((tinfo = out_timestamps.lookup_or_init(&pkt_tuple, &zero)) == NULL)
            return 0;

        tinfo->tcp_time = bpf_ktime_get_ns();
    }
    
    return 0;
}

"""

# code substitutions
if args.port:
    bpf_text = bpf_text.replace('FILTER_PORT',
        'if (ftuple.sport != %s && ftuple.dport != %s) { return 0; }' % (args.port, args.port))
else:
    bpf_text = bpf_text.replace('FILTER_SPORT', '')
if args.sport:
    bpf_text = bpf_text.replace('FILTER_SPORT',
        'if (ftuple.sport != %s) { return 0; }' % args.sport)
else:
    bpf_text = bpf_text.replace('FILTER_SPORT', '')
    
if args.dport:
    bpf_text = bpf_text.replace('FILTER_DPORT',
        'if (pkt_tuple.dport != %s) { return 0; }' % args.dport)
else:
    bpf_text = bpf_text.replace('FILTER_DPORT', '')
if args.sample:
    bpf_text = bpf_text.replace('SAMPLING',
        'if ((time << (64-%s) >> (64-%s)) != ((0x01 << %s) - 1)) { return 0;}' % (args.sample, args.sample, args.sample))
else:
    bpf_text = bpf_text.replace('SAMPLING', '')

class Data_t(ct.Structure):
    _fields_ = [
        ("total_time", ct.c_ulonglong),
        ("qdisc_time", ct.c_ulonglong),
        ("ip_time", ct.c_ulonglong),
        ("tcp_time", ct.c_ulonglong),
        ("saddr", ct.c_uint),
        ("daddr", ct.c_uint),
        ("nat_saddr", ct.c_uint),
        ("nat_sport", ct.c_ushort),
        ("sport", ct.c_ushort),
        ("dport", ct.c_ushort),
        ("seq", ct.c_uint),
        ("ack", ct.c_uint),
    ]

# process event
def print_event(cpu, data, size):
    event = ct.cast(data, ct.POINTER(Data_t)).contents
    print("%-20s -> %-20s > %-20s %-12s %-12s %-10s %-10s %-10s %-10s" % (
        "%s:%d" % (inet_ntop(AF_INET, pack('I', event.saddr)), event.sport),
        "%s:%d" % (inet_ntop(AF_INET, pack('I', event.nat_saddr)), event.nat_sport),
        "%s:%d" % (inet_ntop(AF_INET, pack('I', event.daddr)), event.dport),
        "%d" % (event.seq),
        "%d" % (event.ack),
        "%d" % (event.total_time/1000),
        "%d" % (event.qdisc_time/1000),
        "%d" % (event.ip_time/1000),
        "%d" % (event.tcp_time/1000)))


# initialize BPF
b = BPF(text=bpf_text)
trace_prefix = "trace_"
kprobe_functions_list = ["__tcp_transmit_skb", "ip_queue_xmit", "dev_queue_xmit", "dev_hard_start_xmit", "sch_direct_xmit"]
kretprobe_functions_list = []
for i in range(len(kprobe_functions_list)):
    function = kprobe_functions_list[i]
    trace_function = trace_prefix + function
    if b.get_kprobe_functions(function):
        b.attach_kprobe(event=function, fn_name=trace_function)
    else:
        print("ERROR: %s() kernel function not found or traceable." % (function))
        exit()

for i in range(len(kretprobe_functions_list)):
    function = kretprobe_functions_list[i]
    trace_function = trace_prefix + function
    if b.get_kprobe_functions(function):
        b.attach_kretprobe(event=function, fn_name=trace_function)
    else:
        print("ERROR: %s() kernel function not found or traceable." % (function))
        exit()

# header
print("%-20s -> %-20s > %-20s %-12s %-12s %-10s %-10s %-10s %-10s" % ("SADDR:SPORT", "NAT:PORT", "DADDR:DPORT", "SEQ", "ACK", "TOTAL", "QDisc", "IP", "TCP"))

# read events
b["timestamp_events"].open_perf_buffer(print_event)
while 1:
    try:
        b.perf_buffer_poll()
    except KeyboardInterrupt:
        os.kill(os.getpid(), signal.SIGKILL)