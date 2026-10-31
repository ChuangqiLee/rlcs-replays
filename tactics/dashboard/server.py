#!/usr/bin/env python3
"""Read-only research dashboard; Python 3.6+, standard library only."""
import datetime
import json
import math
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import unquote, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # Install as tactics/dashboard/server.py.
PORT = 18765
LOG_TAIL_BYTES = 20 * 1024
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_POINTS_PER_SPLIT = 2000
SLURM_CACHE_SECONDS = 25
_SLURM_LOCK = threading.Lock()
_SLURM_CACHE = {"at": 0, "data": None}


def timestamp(epoch=None):
    """Always include an offset; the browser converts to Europe/Amsterdam."""
    epoch = time.time() if epoch is None else epoch
    return datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).isoformat()


def inside(path, root):
    """Reject both directory traversal and symlinks escaping the data root."""
    try:
        root = os.path.realpath(root)
        return os.path.commonpath([root, os.path.realpath(path)]) == root
    except (ValueError, OSError):
        return False


def data_path(*parts):
    path = os.path.join(ROOT, *parts)
    if not inside(path, ROOT):
        raise ValueError("路径超出数据目录")
    return path


def read_json(path):
    if not inside(path, ROOT):
        raise ValueError("路径超出数据目录")
    with open(path, "rb") as source:
        raw = source.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("JSON 文件超过 16 MiB")
    # Training writers sometimes emit non-standard NaN/Infinity: expose null.
    return json.loads(raw.decode("utf-8"), parse_constant=lambda value: None)


def status_file(name, default):
    try:
        result = read_json(data_path("status", name + ".json"))
        if not isinstance(result, dict):
            raise ValueError("顶层必须是 JSON 对象")
        return result
    except (OSError, ValueError, UnicodeError) as exc:
        result = dict(default)
        result["error"] = "status/{}.json 暂不可用：{}".format(name, exc)
        return result


def entries(folder, suffix=None, directories=False):
    """Only direct children; reject directory and file symlink escapes."""
    try:
        parent = data_path(folder)
        with os.scandir(parent) as items:
            result = []
            for entry in items:
                if not inside(entry.path, ROOT):
                    continue
                if directories:
                    match = entry.is_dir()
                else:
                    match = entry.is_file() and (not suffix or entry.name.endswith(suffix))
                if match:
                    result.append(entry.path)
            return sorted(result)
    except (OSError, ValueError):
        return []


def results():
    output = {}
    for path in entries("results", ".json"):
        try:
            item = read_json(path)
            if isinstance(item, (dict, list)):
                output[os.path.basename(path)[:-5]] = item
        except (OSError, ValueError, UnicodeError):
            continue
    return output


def metrics(path):
    """Stream JSONL, retaining each split's first/last and a bounded sample."""
    if not inside(path, ROOT):
        raise ValueError("路径超出数据目录")
    groups = {}
    skipped = 0
    total = 0
    with open(path, "r", encoding="utf-8", errors="replace") as source:
        for sequence, line in enumerate(source):
            if not line.strip():
                continue
            try:
                row = json.loads(line, parse_constant=lambda value: None)
                if not isinstance(row, dict):
                    raise ValueError("指标行必须是对象")
            except ValueError:
                skipped += 1
                continue
            total += 1
            split = str(row.get("split", "unspecified"))
            group = groups.setdefault(split, {"rows": [], "stride": 1, "count": 0, "last": None})
            point = (sequence, row)
            group["last"] = point
            if group["count"] % group["stride"] == 0:
                group["rows"].append(point)
            group["count"] += 1
            if len(group["rows"]) >= MAX_POINTS_PER_SPLIT:
                group["rows"] = group["rows"][::2]
                group["stride"] *= 2
    sampled = []
    for group in groups.values():
        sampled.extend(group["rows"])
        if group["last"] and (not group["rows"] or group["rows"][-1][0] != group["last"][0]):
            sampled.append(group["last"])
    sampled.sort(key=lambda item: item[0])
    return [item[1] for item in sampled], total, skipped


def runs():
    output = {}
    for directory in entries("runs", directories=True):
        metric_path = os.path.join(directory, "metrics.jsonl")
        if not os.path.isfile(metric_path) or not inside(metric_path, ROOT):
            continue
        run = {"meta": {}, "rows": [], "warnings": []}
        meta_path = os.path.join(directory, "meta.json")
        if os.path.exists(meta_path):
            try:
                meta = read_json(meta_path)
                if not isinstance(meta, dict):
                    raise ValueError("meta.json 顶层必须是对象")
                run["meta"] = meta
            except (OSError, ValueError, UnicodeError) as exc:
                run["warnings"].append("meta.json 暂不可用：{}".format(exc))
        try:
            rows, total, skipped = metrics(metric_path)
            run.update(rows=rows, total_rows=total, sampled=len(rows) < total, skipped_lines=skipped)
            if skipped:
                run["warnings"].append("已跳过 {} 行不完整或无效指标".format(skipped))
            if run["sampled"]:
                run["warnings"].append("曲线已按 split 抽样；保留起点和最新点")
        except (OSError, ValueError) as exc:
            run["warnings"].append("metrics.jsonl 暂不可用：{}".format(exc))
        output[os.path.basename(directory)] = run
    return output


def logs():
    candidates = []
    for path in entries("logs", ".log"):
        try:
            candidates.append((os.path.getmtime(path), path))
        except OSError:
            continue
    output = {}
    for modified, path in sorted(candidates, reverse=True)[:30]:
        try:
            if not inside(path, ROOT):
                continue
            with open(path, "rb") as source:
                source.seek(0, os.SEEK_END)
                size = source.tell()
                source.seek(max(0, size - LOG_TAIL_BYTES))
                tail = source.read(LOG_TAIL_BYTES).decode("utf-8", "replace")
            output[os.path.basename(path)] = {
                "mtime": timestamp(modified), "tail": tail, "truncated": size > LOG_TAIL_BYTES
            }
        except OSError:
            continue
    return output


def progress():
    try:
        with open(data_path("PROGRESS.md"), "r", encoding="utf-8", errors="replace") as source:
            return source.read()
    except (OSError, ValueError):
        return ""


def command(args):
    try:
        env = dict(os.environ)
        env["TZ"] = "UTC"
        env["SLURM_TIME_FORMAT"] = "standard"
        raw = subprocess.check_output(args, stderr=subprocess.PIPE, timeout=15, env=env)
        return raw.decode("utf-8", "replace"), None
    except subprocess.TimeoutExpired:
        return "", "{} 超时（15 秒）".format(args[0])
    except FileNotFoundError:
        return "", "未安装 {}，或命令不在 PATH 中".format(args[0])
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", "replace").strip()
        return "", "{} 失败：{}".format(args[0], detail[:500] or exc.returncode)
    except OSError as exc:
        return "", "{} 暂不可用：{}".format(args[0], exc)


def parse_queue(raw):
    output = []
    fields = ["jobid", "partition", "name", "state", "time", "limit", "nodes", "reason"]
    for line in raw.splitlines():
        parts = [value.strip() for value in line.split("|", 7)]
        if len(parts) == len(fields) and parts[0].upper() != "JOBID":
            output.append(dict(zip(fields, parts)))
    return output


def slurm_end(value):
    if not value or value in ("Unknown", "None", "N/A"):
        return value
    try:
        # The subprocess uses TZ=UTC and the standard SLURM time format.
        parsed = datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
        return parsed.replace(tzinfo=datetime.timezone.utc).isoformat()
    except (ValueError, OverflowError):
        return value


def parse_history(raw):
    output = []
    fields = ["jobid", "name", "state", "elapsed", "end"]
    for line in raw.splitlines():
        parts = [value.strip() for value in line.split("|")]
        if len(parts) == 6 and not parts[-1]:
            parts.pop()
        if len(parts) != len(fields):
            continue
        row = dict(zip(fields, parts))
        row["end"] = slurm_end(row["end"])
        output.append(row)
    return output


def slurm():
    # Coalesce overlapping browser requests and keep the command rate bounded.
    with _SLURM_LOCK:
        now = time.monotonic()
        if _SLURM_CACHE["data"] is not None and now - _SLURM_CACHE["at"] < SLURM_CACHE_SECONDS:
            return _SLURM_CACHE["data"]
        user = os.environ.get("USER", "").strip()
        queue_raw = history_raw = ""
        queue_error = history_error = "USER 环境变量未设置" if not user else None
        if user:
            queue_args = ["squeue", "-u", user, "-h", "-o", "%i|%P|%j|%T|%M|%l|%D|%R"]
            history_args = ["sacct", "-u", user, "-S", (datetime.datetime.now() - datetime.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S"),
                            "--format=JobID,JobName%30,State,Elapsed,End", "-P", "-n"]
            with ThreadPoolExecutor(max_workers=2) as executor:
                queue_future = executor.submit(command, queue_args)
                history_future = executor.submit(command, history_args)
                queue_raw, queue_error = queue_future.result()
                history_raw, history_error = history_future.result()
        data = {
            "queue": parse_queue(queue_raw), "history": parse_history(history_raw),
            "queue_error": queue_error, "history_error": history_error, "updated": timestamp()
        }
        _SLURM_CACHE.update(at=time.monotonic(), data=data)
        return data


def host():
    return {"host": os.uname()[1], "port": PORT, "time": timestamp()}


API = {
    "/api/host": host,
    "/api/phases": lambda: status_file("phases", {"updated": None, "phases": []}),
    "/api/dataset": lambda: status_file("dataset", {}),
    "/api/ideas": lambda: status_file("ideas", {"updated": None, "ideas": []}),
    "/api/paper": lambda: status_file("paper", {"updated": None, "sections": [], "figures": []}),
    "/api/results": results,
    "/api/runs": runs,
    "/api/logs": logs,
    "/api/progress": progress,
    "/api/slurm": slurm,
    "/api/squeue": slurm,
}
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
}


def json_safe(value):
    """Convert numeric overflow and non-finite metrics into valid JSON null."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


class Handler(BaseHTTPRequestHandler):
    server_version = "ResearchDashboard/1.0"

    def log_message(self, *args):
        pass

    def send(self, code, body, content_type):
        payload = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        try:
            path = unquote(urlsplit(self.path).path, errors="strict")
        except (ValueError, UnicodeError):
            return self.send(400, "bad path", "text/plain; charset=utf-8")
        if "\x00" in path or "\\" in path or any(part in (".", "..") for part in path.split("/")):
            return self.send(400, "bad path", "text/plain; charset=utf-8")
        if path == "/healthz":
            return self.send(200, "ok", "text/plain; charset=utf-8")
        if path in API:
            try:
                body = json.dumps(json_safe(API[path]()), ensure_ascii=False, allow_nan=False)
                return self.send(200, body, "application/json; charset=utf-8")
            except Exception:
                return self.send(500, '{"error":"数据暂不可用，请稍后重试"}', "application/json; charset=utf-8")
        if path in STATIC:
            filename, content_type = STATIC[path]
            filename = os.path.join(HERE, filename)
            if not inside(filename, HERE):
                return self.send(403, "forbidden", "text/plain; charset=utf-8")
            try:
                with open(filename, "rb") as source:
                    return self.send(200, source.read(), content_type)
            except OSError:
                pass
        return self.send(404, "not found", "text/plain; charset=utf-8")


class Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    global PORT
    try:
        PORT = int(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DASH_PORT", "18765"))
        if not 1 <= PORT <= 65535:
            raise ValueError("port outside 1..65535")
    except ValueError as exc:
        raise SystemExit("端口无效：{}".format(exc))
    server = Server(("127.0.0.1", PORT), Handler)
    print("Dashboard: http://127.0.0.1:{} / data: {}".format(PORT, ROOT), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
