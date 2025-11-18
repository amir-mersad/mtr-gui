import time
import subprocess
import re
import sys
from scapy.all import IP, ICMP, srp, conf, Ether, get_if_list


class MTRTracer:
    def __init__(self, target_host, max_hops=30, method="tracert"):
        """method: 'tracert' (default on Windows) or 'scapy'"""
        self.target_host = target_host
        self.max_hops = max_hops
        self.method = method

    def _tracert_trace(self):
        """Use Windows 'tracert -d' to gather hops and RTTs."""
        hops = []
        try:
            # -d disables name resolution (IP only), set timeout higher if needed
            proc = subprocess.run(["tracert", "-d", "-w", "200", self.target_host], capture_output=True, text=True, timeout=60)
            out = proc.stdout.splitlines()
        except Exception as e:
            print(f"tracert failed: {e}")
            return hops

        ip_re = re.compile(r"(\d+\.\d+\.\d+\.\d+)")
        rtt_re = re.compile(r"<?(\d+)\s*ms")

        for line in out:
            line = line.strip()
            if not line:
                continue
            if line.startswith("Tracing route") or line.lower().startswith("over a maximum"):
                continue
            # Lines start with hop number
            parts = line.split()
            if not parts:
                continue
            if not parts[0].isdigit():
                continue
            hop_num = int(parts[0])

            # Find IP in the line (last token usually)
            ip_match = ip_re.search(line)
            ip_addr = ip_match.group(1) if ip_match else "*"

            # Find all RTTs in the line and average them
            rtts = [int(m) for m in rtt_re.findall(line)]
            if rtts:
                latency = sum(rtts) / len(rtts)
            else:
                latency = -1

            hops.append({"hop": hop_num, "ip": ip_addr, "latency": latency})
            if ip_addr == self.target_host:
                break

        return hops

    def _scapy_trace(self):
        """Fallback scapy-based TTL probing (may require elevated privileges)."""
        hops = []
        # Try to find a working interface
        interfaces = get_if_list()
        if interfaces:
            conf.iface = interfaces[0]

        for ttl in range(1, self.max_hops + 1):
            start_time = time.time()
            pkt = IP(dst=self.target_host, ttl=ttl) / ICMP()
            ans, unans = srp(Ether() / pkt, verbose=0, timeout=2)
            latency = (time.time() - start_time) * 1000

            if not ans:
                hops.append({"hop": ttl, "ip": "*", "latency": -1})
            else:
                _, reply = ans[0]
                ip_addr = reply[IP].src if reply.haslayer(IP) else reply.src
                hops.append({"hop": ttl, "ip": ip_addr, "latency": latency})
                if ip_addr == self.target_host:
                    break

        return hops

    def trace(self):
        # Default on Windows: use tracert for correctness and permissions
        if self.method == "tracert" and sys.platform.startswith("win"):
            hops = self._tracert_trace()
            if hops:
                return hops
            # fallback to scapy if tracert failed
            return self._scapy_trace()

        if self.method == "scapy":
            return self._scapy_trace()

        # generic fallback
        return self._tracert_trace()