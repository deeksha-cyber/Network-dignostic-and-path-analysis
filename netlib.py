import json
import os
import subprocess
import threading
import time
from itertools import combinations

from mininet.link import TCLink
from mininet.net import Mininet
from mininet.node import OVSSwitch

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "probe_server.py")
CLIENT = os.path.join(HERE, "probe_client.py")

IP = {"h1": "10.0.0.1", "h2": "10.0.0.2", "h3": "10.0.0.3", "h4": "10.0.0.4"}
NAME = {v: k for k, v in IP.items()}
ATTACH = {"h1": (1, 1), "h3": (1, 2), "h2": (4, 1), "h4": (4, 2)}  # host -> (dpid, port)
PATHS = {"s1-s2-s4": [1, 2, 4], "s1-s3-s4": [1, 3, 4]}
EXPECTED = {"s1-s2-s4": 20, "s1-s3-s4": 80}  # expected RTT in ms
BACKBONE = [("s1", "s2"), ("s1", "s3"), ("s2", "s4"), ("s3", "s4")]
BW = 5  # Mbps on every backbone link

# Link order matters: it gives the port numbers seen in your screenshots.
LINKS = [
    ("h1", "s1", {}),
    ("h3", "s1", {}),
    ("h2", "s4", {}),
    ("h4", "s4", {}),
    ("s1", "s2", dict(delay="5ms", bw=BW, max_queue_size=50)),
    ("s1", "s3", dict(delay="20ms", bw=BW, loss=1.4, max_queue_size=50)),
    ("s2", "s4", dict(delay="5ms", bw=BW, max_queue_size=50)),
    ("s3", "s4", dict(delay="20ms", bw=BW, loss=1.4, max_queue_size=50)),
]


def switches_for(src, dst, pid):
    sa, sb = ATTACH[src][0], ATTACH[dst][0]
    if sa == sb:
        return [sa]
    p = PATHS[pid]
    return p if sa == 1 else p[::-1]


def read_int(path):
    with open(path) as f:
        return int(f.read().strip())


def iface_state(iface):
    try:
        with open("/sys/class/net/%s/operstate" % iface) as f:
            return f.read().strip()
    except OSError:
        return "missing"


def tx_bytes(iface):
    return read_int("/sys/class/net/%s/statistics/tx_bytes" % iface)


class Lab:
    def __init__(self):
        subprocess.run(["mn", "-c"], capture_output=True)
        self.net = Mininet(controller=None, switch=OVSSwitch, link=TCLink,
                           autoSetMacs=True)
        for h in ("h1", "h2", "h3", "h4"):
            self.net.addHost(h)  # IPs become 10.0.0.1 .. 10.0.0.4
        for i in range(1, 5):
            self.net.addSwitch("s%d" % i, protocols="OpenFlow13", failMode="secure")
        for a, b, params in LINKS:
            self.net.addLink(a, b, **params)
        self.port = {}
        self.pair_path = {}
        self.down = set()
        self.util = {}
        self.running = False

    # ---------- lifecycle ----------
    def start(self, servers=True):
        self.net.start()
        self.net.staticArp()
        for l in self.net.links:
            a, b = l.intf1.node.name, l.intf2.node.name
            self.port[(a, b)] = l.intf1.node.ports[l.intf1]
            self.port[(b, a)] = l.intf2.node.ports[l.intf2]
        for i in range(1, 5):
            sw = "s%d" % i
            self.flow(sw, "priority=65535,dl_dst=01:80:c2:00:00:0e,dl_type=0x88cc,"
                          "actions=CONTROLLER:65535")
            self.flow(sw, "priority=0,actions=CONTROLLER:65535")
        self.route_all("s1-s2-s4")
        if servers:
            for h in self.net.hosts:
                h.cmd("python3 %s 9000 > /dev/null 2>&1 &" % SERVER)
            time.sleep(0.5)
        self.running = True
        threading.Thread(target=self._sample, daemon=True).start()

    def stop(self):
        self.running = False
        self.flood_stop()
        self.net.stop()

    # ---------- flows / routing ----------
    def flow(self, sw, spec):
        subprocess.run(["ovs-ofctl", "-O", "OpenFlow13", "add-flow", sw, spec],
                       capture_output=True)

    def install(self, src, dst, sws):
        nodes = [src] + ["s%d" % s for s in sws] + [dst]
        for i in range(1, len(nodes) - 1):
            out = self.port[(nodes[i], nodes[i + 1])]
            self.flow(nodes[i], "priority=100,ip,nw_src=%s,nw_dst=%s,actions=output:%d"
                      % (IP[src], IP[dst], out))

    def route_pair(self, a, b, pid):
        self.install(a, b, switches_for(a, b, pid))
        self.install(b, a, switches_for(b, a, pid))
        self.pair_path[(a, b)] = pid
        self.pair_path[(b, a)] = pid

    def route_all(self, pid):
        for a, b in combinations(("h1", "h2", "h3", "h4"), 2):
            self.route_pair(a, b, pid)

    def fail_link(self, a, b):
        self.net.configLinkStatus(a, b, "down")
        self.down.add(frozenset((a, b)))

    def counters(self):
        out = {}
        for i in range(1, 5):
            txt = subprocess.run(["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", "s%d" % i],
                                 capture_output=True, text=True).stdout
            n = 0
            for line in txt.splitlines():
                if "priority=100" in line and "n_packets=" in line:
                    n += int(line.split("n_packets=")[1].split(",")[0])
            out["s%d" % i] = n
        return out

    # ---------- probing / traffic ----------
    def probe(self, src, dst, count=20, interval=0.1, timeout=0.5):
        out = self.net.get(src).cmd("python3 %s --dst %s --count %d --interval %s --timeout %s"
                                    % (CLIENT, IP[dst], count, interval, timeout))
        for line in reversed(out.strip().splitlines()):
            if line.startswith("{"):
                return json.loads(line)
        raise RuntimeError("probe failed: " + out)

    def probe_async(self, *a, **k):
        res = {}

        def run():
            res.update(self.probe(*a, **k))

        t = threading.Thread(target=run)
        t.start()
        return t, res

    def flood_start(self, secs=30, rate="8M"):
        self.net.get("h4").cmd("iperf -s -u > /dev/null 2>&1 &")
        self.net.get("h3").cmd("iperf -c 10.0.0.4 -u -b %s -t %d > /dev/null 2>&1 &"
                               % (rate, secs))
        time.sleep(1)

    def flood_stop(self):
        for n in ("h3", "h4"):
            try:
                self.net.get(n).cmd("pkill -f iperf")
            except Exception:
                pass

    # ---------- info for the REST API ----------
    def _sample(self):
        last = {}
        while self.running:
            time.sleep(1)
            for a, b in BACKBONE:
                iface = "%s-eth%d" % (a, self.port[(a, b)])
                try:
                    cur = tx_bytes(iface)
                except OSError:
                    continue
                if (a, b) in last:
                    rate = (cur - last[(a, b)]) * 8 / 1e6
                    self.util[(a, b)] = round(min(1.0, rate / BW), 2)
                last[(a, b)] = cur

    def topology(self):
        links = []
        for a, b in BACKBONE:
            links.append({"src": a, "dst": b,
                          "src_port": self.port[(a, b)], "dst_port": self.port[(b, a)],
                          "util": self.util.get((a, b), 0.0)})
        hosts = [{"ip": IP[h], "mac": "00:00:00:00:00:0" + h[1],
                  "dpid": ATTACH[h][0], "port": ATTACH[h][1]}
                 for h in ("h1", "h2", "h3", "h4")]
        return {"switches": [1, 2, 3, 4], "links": links, "hosts": hosts}

    def path_info(self, sip, dip):
        if sip not in NAME or dip not in NAME:
            return {"error": "unknown src or dst"}
        src, dst = NAME[sip], NAME[dip]
        paths = []
        for pid in PATHS:
            sws = switches_for(src, dst, pid)
            up = all(frozenset(("s%d" % x, "s%d" % y)) not in self.down
                     for x, y in zip(sws, sws[1:]))
            paths.append({"id": pid, "switches": sws, "hops": len(sws),
                          "state": "UP" if up else "DOWN", "metrics": None})
        return {"src": sip, "dst": dip, "active_path": self.pair_path.get((src, dst)),
                "pinned": None, "paths": paths}