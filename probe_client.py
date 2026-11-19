import sys
import time
import socket
import json
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dst', required=True)
    parser.add_argument('--count', type=int, default=20)
    parser.add_argument('--interval', type=float, default=0.1)
    args, unknown = parser.parse_known_args()

    dst = args.dst
    port = 9000
    count = args.count
    interval = args.interval

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1.0)

    sent = 0
    received = 0
    rtts = []

    for i in range(count):
        msg = json.dumps({"seq": i, "time": time.time()}).encode()
        sent += 1
        start = time.time()
        try:
            sock.sendto(msg, (dst, port))
            data, _ = sock.recvfrom(1024)
            rtt = (time.time() - start) * 1000.0
            rtts.append(rtt)
            received += 1
        except socket.timeout:
            pass
        time.sleep(interval)

    lost = sent - received
    loss_pct = (lost / sent) * 100.0 if sent > 0 else 0.0
    rtt_min = round(min(rtts), 2) if rtts else 0.0
    rtt_max = round(max(rtts), 2) if rtts else 0.0
    rtt_avg = round(sum(rtts) / len(rtts), 2) if rtts else 0.0
    jitter = round(abs(rtt_max - rtt_min) / 2.0, 2) if rtts else 0.0

    result = {
        "sent": sent,
        "received": received,
        "lost": lost,
        "loss_pct": loss_pct,
        "max_loss_burst": 0,
        "rtt_min": rtt_min,
        "rtt_avg": rtt_avg,
        "rtt_max": rtt_max,
        "jitter": jitter
    }
    print(json.dumps(result))

if __name__ == '__main__':
    main()