#!/usr/bin/env python

'''
See dnsflow.c header comment for packet formats.
'''

import os, sys, time, json, pprint, getopt, signal, re
import traceback, tempfile, stat
import urllib2
import socket
import gzip
import dpkt, pcap
import dns, dns.message
import json
import commands
import subprocess
import random
import urllib
import struct
import ipaddr

verbosity = 0

DNSFLOW_FLAG_STATS = 0x0001

def process_pkt(dl_type, ts, buf):
    if dl_type == dpkt.pcap.DLT_NULL:
        # Loopback
        try:
            lo = dpkt.loopback.Loopback(buf)
        except:
            print 'Loopback parse failed: %s' % (buf)
            return
        if lo.family == socket.AF_UNSPEC:
            # dnsflow dumped straight to pcap
            pkt = lo.data
        elif lo.family == socket.AF_INET:
            # dl, ip, udp, pkt
            pkt = lo.data.data.data
    elif dl_type == dpkt.pcap.DLT_EN10MB:
        # Ethernet
        try:
            eth = dpkt.ethernet.Ethernet(buf)
        except:
            print 'Ethernet parse failed: %s' % (buf)
            return
        pkt = eth.data.data.data

    cp = 0

    # vers, sets_count, flags, seq_num
    fmt = '!BBHI'
    vers, sets_count, flags, seq_num = struct.unpack(fmt,
            pkt[cp:cp + struct.calcsize(fmt)])
    cp += struct.calcsize(fmt)
    if verbosity > 0:
        print 'HEADER|%d|%d' % (sets_count, seq_num)

    if flags & DNSFLOW_FLAG_STATS:
        fmt = '!4I'
        stats = struct.unpack(fmt, pkt[cp:cp + struct.calcsize(fmt)])
        print "STATS|%s" % ('|'.join([str(x) for x in stats]))
    else:
        # data pkt
        for i in range(sets_count):
            # client_ip, names_count, ips_count, names_len
            fmt = '!IBBH'
            client_ip, names_count, ips_count, names_len = struct.unpack(fmt,
                    pkt[cp:cp + struct.calcsize(fmt)])
            cp += struct.calcsize(fmt)
            client_ip = str(ipaddr.IPAddress(client_ip))

            # names are Nul terminated, and padded with Nuls on the end to word
            # align.
            fmt = '%ds' % (names_len)
            name_set = struct.unpack(fmt, pkt[cp:cp + struct.calcsize(fmt)])[0]
            cp += struct.calcsize(fmt)
            names = name_set.split('\0')
            names = names[0:names_count]

            fmt = '!%dI' % (ips_count)
            ips = struct.unpack(fmt, pkt[cp:cp + struct.calcsize(fmt)])
            cp += struct.calcsize(fmt)
            ips = [str(ipaddr.IPAddress(x)) for x in ips]

            print 'DATA|%s|%s|%s' % (client_ip, ','.join(names), ','.join(ips))

                
def read_pcapfile(pcap_files):
    for pcap_file in pcap_files:
        try:
            f = gzip.open(pcap_file, 'rb')
            pcap = dpkt.pcap.Reader(f)
        except:
            try:
                f = open(pcap_file, 'rb')
                pcap = dpkt.pcap.Reader(f)
            except:
                print 'Failed opening file: %s' % (pcap_file)
                continue

        pcap.setfilter("udp and dst port 5300", optimize=1)

        print 'Parsing file: %s' % (pcap_file)
        for ts, buf in pcap:
            process_pkt(pcap.datalink(), ts, buf)

def mode_livecapture(interface):
    print 'Capturing on', interface
    p = pcap.pcapObject()
    p.open_live(interface, 65535, 1, 100)
    # filter, optimize, netmask
    p.setfilter('udp and dst port 5300', 1, 0)

    try:
        while 1:
            rv = p.next()
            if rv != None:
                pktlen, buf, ts = rv
                process_pkt(p.datalink(), ts, buf)
    except KeyboardInterrupt:
        print '\nshutting down'
        print '%d packets received, %d packets dropped, %d packets dropped by interface' % p.stats()
   

def main(argv):
    global verbosity

    usage = ('Usage: %s [-v] [-r pcap_file] [-i interface]' % (argv[0]))

    try:
        opts, args = getopt.getopt(argv[1:], 'i:r:v')
    except getopt.GetoptError:
        print >>sys.stderr, usage
        return 1

    filename = None
    interface = None
    
    for o, a in opts:
        if o == '-v':
            verbosity += 1
        elif o == '-r':
            filename = a
        elif o == '-i':
            interface = a

    if filename is not None:
        read_pcapfile([filename])
    elif interface is not None:
        mode_livecapture(interface)

if __name__ == '__main__':
    main(sys.argv)

    
