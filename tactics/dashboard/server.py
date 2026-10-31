#!/usr/bin/env python3
"""RLCS tactics progress dashboard. Stdlib only (Python 3.6+). Binds 127.0.0.1."""
import json, os, glob, subprocess, sys, html, time
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # tactics/
PORT = int(os.environ.get("DASH_PORT", sys.argv[1] if len(sys.argv) > 1 else 18765))

def rd(p, limit=None):
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            s = f.read()
        return s[-limit:] if limit else s
    except Exception:
        return None

def phases():
    s = rd(os.path.join(ROOT, "status", "phases.json"))
    try: return json.loads(s)
    except Exception: return {"error": "phases.json missing/invalid"}

def squeue():
    try:
        out = subprocess.check_output(["squeue", "-u", os.environ.get("USER", ""), "-o",
              "%.12i %.10P %.30j %.8T %.10M %.12l %.5D %R"], stderr=subprocess.STDOUT, timeout=15)
        return out.decode("utf-8", "replace")
    except Exception as e:
        return "squeue error: %s" % e

def runs():
    res = {}
    for d in sorted(glob.glob(os.path.join(ROOT, "runs", "*"))):
        m = os.path.join(d, "metrics.jsonl")
        if not os.path.isfile(m): continue
        rows = []
        for line in (rd(m) or "").splitlines():
            try: rows.append(json.loads(line))
            except Exception: pass
        if len(rows) > 2000:  # downsample
            k = len(rows) // 2000 + 1; rows = rows[::k] + rows[-1:]
        meta = rd(os.path.join(d, "meta.json"))
        try: meta = json.loads(meta) if meta else {}
        except Exception: meta = {}
        res[os.path.basename(d)] = {"meta": meta, "rows": rows}
    return res

def logs():
    out = {}
    for p in sorted(glob.glob(os.path.join(ROOT, "logs", "*.log")), key=os.path.getmtime, reverse=True)[:30]:
        out[os.path.basename(p)] = {"mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(p))),
                                    "tail": rd(p, 20000)}
    return out

def results():
    out = {}
    for p in sorted(glob.glob(os.path.join(ROOT, "results", "*.json"))):
        try: out[os.path.basename(p)[:-5]] = json.loads(rd(p))
        except Exception: pass
    return out

API = {"/api/phases": phases, "/api/squeue": squeue, "/api/runs": runs, "/api/logs": logs,
       "/api/results": results, "/api/progress": lambda: rd(os.path.join(ROOT, "PROGRESS.md")) or "",
       "/api/host": lambda: {"host": os.uname()[1], "port": PORT, "time": time.strftime("%Y-%m-%d %H:%M:%S %Z")}}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, body, ctype):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self.send(200, rd(os.path.join(HERE, "index.html")) or "missing index", "text/html; charset=utf-8")
        if path == "/healthz": return self.send(200, "ok", "text/plain")
        f = API.get(path)
        if f:
            try: return self.send(200, json.dumps(f()), "application/json")
            except Exception as e: return self.send(500, json.dumps({"error": str(e)}), "application/json")
        self.send(404, "not found", "text/plain")

class S(ThreadingMixIn, HTTPServer):
    daemon_threads = True; allow_reuse_address = True

if __name__ == "__main__":
    print("dashboard on %s 127.0.0.1:%d" % (os.uname()[1], PORT), flush=True)
    S(("127.0.0.1", PORT), H).serve_forever()
