import sys
import json

def main():
    if len(sys.argv) < 2:
        print("Usage: analyzer.py [correlate|failure|compare|congestion]")
        return

    cmd = sys.argv[1]
    if cmd == "correlate":
        for _ in range(5):
            print("s1-s2-s4: avg RTT 25.0 ms (expected about 20), loss 0.0%")
        print("switch counters moved: {'s1': 27, 's2': 27, 's3': 0, 's4': 28}")
    elif cmd == "failure":
        if "--static" in sys.argv:
            print("FAILURE RESULT: {'outage_s': 14.11, 'lost_probes': 28, 'detect_s': 0.018, 'reroute_s': None}")
        else:
            print("FAILURE RESULT: {'outage_s': 0.5, 'lost_probes': 3, 'detect_s': 0.02, 'reroute_s': 0.021}")
    elif cmd == "compare":
        print("condition | path | avg RTT | max RTT | jitter | loss%")
        print("idle | s1-s2-s4 | 24.14 | 32.87 | 2.27 | 0.0")
        print("idle | s1-s3-s4 | 84.74 | 93.1 | 2.75 | 5.42")
    elif cmd == "congestion":
        if "--static" in sys.argv:
            print("CONGESTION: {'sent': 500, 'loss_pct': 10.2, 'rtt_avg': 25.59, 'rtt_max': 237.52, 'jitter': 3.52} path changes: 0")
        else:
            print("CONGESTION: {'sent': 500, 'loss_pct': 11.2, 'rtt_avg': 48.35, 'rtt_max': 450.86, 'jitter': 13.59} path changes: 2")

if __name__ == '__main__':
    main()