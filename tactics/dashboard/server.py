#!/usr/bin/env python3
"""Read-only research dashboard; Python 3.6+, standard library only."""
import csv
import datetime
import io
import glob
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import unquote, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.expanduser(os.environ.get("DASH_DATA_ROOT", os.path.dirname(HERE))))
# Optional, explicitly selected local reference data for review. Never downloaded.
REFERENCE_ROOT = os.path.abspath(os.path.expanduser(os.environ["DASH_REFERENCE_ROOT"])) if os.environ.get("DASH_REFERENCE_ROOT") else None
PROJECT_ROOT = os.path.normpath(os.path.expanduser(os.environ.get("DASH_PROJECT_ROOT", "~/workspace/rlcs-replays")))
PORT = 18765
LOG_TAIL_BYTES = 20 * 1024
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_POINTS_PER_SPLIT = 2000
SLURM_CACHE_SECONDS = 25
_SLURM_LOCK = threading.Lock()
_SLURM_CACHE = {"at": 0, "data": None}
JOBS_CACHE_SECONDS = 60
_JOBS_LOCK = threading.Lock()
_JOBS_CACHE = {"at": 0, "data": None}
UTC = datetime.timezone.utc
JOB_FIELDS = "JobID,JobName,Partition,State,Elapsed,Timelimit,AllocCPUS,ReqMem,MaxRSS,AllocTRES,NodeList,Start,End,WorkDir"
# Explicit model-name mappings only. Ampere/Pascal are families, not models.
GPU_PARTITION_MODELS = {"a100": "A100", "h100": "H100", "h200": "H200", "a40": "A40", "v100": "V100"}
FAILED_JOB_STATES = {"FAILED", "CANCELLED", "TIMEOUT", "NODE_FAIL", "OUT_OF_MEMORY", "BOOT_FAIL", "DEADLINE", "PREEMPTED", "REVOKED"}


def known(value):
    value = str(value).strip() if value is not None else ""
    return None if value.lower() in ("", "unknown", "none", "n/a", "(null)", "null", "notset") else value


def nonnegative_int(value):
    value = known(value)
    return int(value) if value and re.fullmatch(r"\d+", value) else None


def elapsed_seconds(value):
    """Slurm [days-]hours:minutes:seconds or minutes:seconds, never a guessed duration."""
    value = known(value)
    if not value:
        return None
    match = re.fullmatch(r"(?:(\d+)-)?(?:(\d+):)?(\d{2}):(\d{2})", value)
    if not match:
        return None
    days, hours, minutes, seconds = (int(x or 0) for x in match.groups())
    if minutes >= 60 or seconds >= 60 or (match[1] and not match[2]):
        return None
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def parse_iso(value):
    """Parse YYYY-MM-DD[T or space]HH:MM:SS[.ffffff][Z or +/-HH:MM].

    Also accept compact +/-HHMM offsets. Reject incomplete/invalid timestamps;
    datetime validates calendar and clock fields without a newer ISO parser.
    """
    match = re.fullmatch(
        r"([0-9]{4})-([0-9]{2})-([0-9]{2})[T ]([0-9]{2}):([0-9]{2}):([0-9]{2})"
        r"(?:\.([0-9]{1,6}))?(Z|[+-][0-9]{2}:?[0-9]{2})?", value)
    if not match:
        raise ValueError("invalid ISO timestamp")
    parts = match.groups()
    parsed = datetime.datetime(*[int(part) for part in parts[:6]],
                               microsecond=int((parts[6] or "0").ljust(6, "0")))
    offset = parts[7]
    if offset:
        minutes = 0
        if offset != "Z":
            digits = offset[1:].replace(":", "")
            hours, minutes = int(digits[:2]), int(digits[2:])
            if hours > 23 or minutes > 59:
                raise ValueError("invalid ISO offset")
            minutes = (hours * 60 + minutes) * (-1 if offset[0] == "-" else 1)
        parsed = parsed.replace(tzinfo=datetime.timezone(datetime.timedelta(minutes=minutes)))
    return parsed


def sunday(year, month, day):
    """Sunday on or after the given day (used for current EU/US DST rules)."""
    date = datetime.datetime(year, month, day)
    return date + datetime.timedelta(days=(6 - date.weekday()) % 7)


def chicago_to_utc(local):
    """Current US rules: second March Sunday / first November Sunday, 02:00.

    These fixed rules intentionally do not implement historical IANA changes.
    """
    start = sunday(local.year, 3, 8).replace(hour=2)
    end = sunday(local.year, 11, 1).replace(hour=2)
    hour = datetime.timedelta(hours=1)
    if start <= local < start + hour or end - hour <= local < end:
        raise ValueError("nonexistent or ambiguous Chicago time")
    offset = -5 if start <= local < end else -6
    return (local - datetime.timedelta(hours=offset)).replace(tzinfo=UTC)


def job_time(value, source_timezone="America/Chicago"):
    """UTC sacct or Chicago fallback -> fixed CET (UTC+1).

    Ambiguous/nonexistent Chicago wall times have no unique instant: return null.
    Explicit offsets can disambiguate repeated hours.
    """
    value = known(value)
    if not value:
        return None
    try:
        parsed = parse_iso(value)
        if parsed.tzinfo is None:
            if source_timezone == "UTC":
                parsed = parsed.replace(tzinfo=UTC)
            elif source_timezone == "America/Chicago":
                parsed = chicago_to_utc(parsed)
            else:
                return None
        return parsed.astimezone(datetime.timezone(datetime.timedelta(hours=1))).isoformat()
    except (ValueError, OverflowError):
        return None


def gpu_allocation(tres, partition):
    """The aggregate gres/gpu count takes precedence; never double count typed TRES."""
    tres = known(tres)
    if tres is None:
        return None, None, None
    values = dict(part.split("=", 1) for part in tres.split(",") if "=" in part)
    gpu = {k.strip(): nonnegative_int(v) for k, v in values.items() if k.strip() == "gres/gpu" or k.strip().startswith("gres/gpu:")}
    if not gpu:
        # Valid CPU allocations establish CPU-only; arbitrary/invalid TRES do not.
        return (0, None, None) if nonnegative_int(values.get("cpu")) is not None else (None, None, None)
    typed = {k[len("gres/gpu:"):]: v for k, v in gpu.items() if k.startswith("gres/gpu:")}
    count = gpu.get("gres/gpu") if "gres/gpu" in gpu else (sum(typed.values()) if all(v is not None for v in typed.values()) else None)
    models = [name for name, n in typed.items() if n and known(name)]
    model = ", ".join(models) or None
    source = "AllocTRES" if model else None
    # A partial set of typed counts does not establish the model of every GPU.
    if model and "gres/gpu" in gpu and (any(v is None for v in typed.values()) or sum(typed.values()) != count):
        model = source = None
    if not model and count:
        matches = [model for token, model in GPU_PARTITION_MODELS.items() if token in (partition or "").lower()]
        if len(matches) == 1:
            model, source = matches[0], "partition"
    return count, model, source


def node_gpu_evidence():
    """Per-node GPU model verified by nvidia-smi in earlier probe jobs (status/gpu_models.json)."""
    try:
        with open(data_path("status", "gpu_models.json"), encoding="utf-8") as handle:
            data = json.load(handle)
        return data.get("nodes", {}) if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def parse_jobs(raw, source_timezone="America/Chicago"):
    lines = [line for line in raw.splitlines() if line.strip()]
    if not lines:
        return []
    reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter="|")
    if not reader.fieldnames or "JobID" not in reader.fieldnames:
        raise ValueError("sacct header must include JobID")
    output = {}
    for row in reader:
        jobid = known(row.get("JobID"))
        if not jobid or "." in jobid:  # Ignore .batch/.extern/steps in fallback exports.
            continue
        item = {key: known(row.get(field)) for key, field in {
            "jobid": "JobID", "name": "JobName", "partition": "Partition", "state": "State",
            "elapsed": "Elapsed", "timelimit": "Timelimit", "req_mem": "ReqMem", "max_rss": "MaxRSS",
            "alloc_tres": "AllocTRES", "nodes": "NodeList", "workdir": "WorkDir"}.items()}
        gpu_count, model, model_source = gpu_allocation(item["alloc_tres"], item["partition"])
        if gpu_count and not model and item.get("nodes"):
            evidence = node_gpu_evidence().get(item["nodes"])
            if evidence and evidence.get("model"):
                model, model_source = evidence["model"], "node probe: " + str(evidence.get("source", "unknown"))
        cpus = nonnegative_int(row.get("AllocCPUS"))
        item.update(alloc_cpus=cpus, gpu_count=gpu_count, gpu_model=model, gpu_model_source=model_source,
                    resource_type="GPU" if gpu_count and gpu_count > 0 else "CPU" if gpu_count == 0 else None,
                    elapsed_seconds=elapsed_seconds(item["elapsed"]),
                    start=job_time(row.get("Start"), source_timezone), end=job_time(row.get("End"), source_timezone))
        item["state_code"] = item["state"].split()[0].rstrip("+").upper() if item["state"] else None
        output[jobid] = item
    return list(output.values())


def job_summary(rows, available=True):
    counts = {key: 0 if available else None for key in ("running", "completed", "failed", "other")}
    cpu_hours, gpu_hours, cpu_missing, gpu_missing = 0, 0, 0, 0
    for row in rows:
        state = row["state_code"]
        key = "running" if state in ("RUNNING", "COMPLETING") else "completed" if state == "COMPLETED" else "failed" if state in FAILED_JOB_STATES else "other"
        counts[key] += 1
        elapsed = row["elapsed_seconds"]
        for resource in ("cpu", "gpu"):
            count = row["alloc_cpus" if resource == "cpu" else "gpu_count"]
            if count == 0:
                continue
            if elapsed is None or count is None:
                if resource == "cpu": cpu_missing += 1
                else: gpu_missing += 1
            elif resource == "cpu": cpu_hours += elapsed * count / 3600
            else: gpu_hours += elapsed * count / 3600
    return dict(counts, cpu_hours=cpu_hours if available and (not rows or cpu_missing < len(rows)) else None,
                gpu_hours=gpu_hours if available and (not rows or gpu_missing < len(rows)) else None,
                cpu_missing_jobs=cpu_missing if available else None,
                gpu_missing_jobs=gpu_missing if available else None, total=len(rows) if available else None)


def project_job(workdir):
    """Remote WorkDir is lexical evidence; never resolve it against local symlinks."""
    if not known(workdir):
        return False
    if workdir == "~" or workdir.startswith("~/"):
        workdir = os.path.expanduser(workdir)
    if not os.path.isabs(workdir):
        return False
    try:
        return os.path.commonpath([PROJECT_ROOT, os.path.normpath(workdir)]) == PROJECT_ROOT
    except ValueError:
        return False


def jobs():
    with _JOBS_LOCK:
        if _JOBS_CACHE["data"] is not None and time.monotonic() - _JOBS_CACHE["at"] < JOBS_CACHE_SECONDS:
            return _JOBS_CACHE["data"]
        user = os.environ.get("USER", "").strip()
        since = (datetime.datetime.now(UTC) - datetime.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S")
        error = error_en = None
        rows, source, cache_file_updated = [], None, None
        source_timezone = None
        try:
            if os.environ.get("DASH_OFFLINE", "1") != "0":
                raise OSError("DASH_OFFLINE=1")
            if not user:
                raise OSError("USER is not set")
            env = dict(os.environ, TZ="UTC", SLURM_TIME_FORMAT="standard")
            raw = subprocess.check_output(["sacct", "-u", user, "-S", since, "-X", "-P", "-o", JOB_FIELDS],
                                          stderr=subprocess.PIPE, timeout=10, env=env)
            rows, source = parse_jobs(raw.decode("utf-8", "replace"), "UTC"), "sacct"
            source_timezone = "UTC"
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            detail = "timeout (10s)" if isinstance(exc, subprocess.TimeoutExpired) else str(exc)[:300]
            error, error_en = "sacct 暂不可用：" + detail, "sacct unavailable: " + detail
            try:
                path = data_path("status", "jobs_cache.psv")
                with open(path, encoding="utf-8") as handle:
                    rows = parse_jobs(handle.read(), "America/Chicago")
                    cache_file_updated = timestamp(os.fstat(handle.fileno()).st_mtime)
                source = "status/jobs_cache.psv"
                source_timezone = "America/Chicago"
            except (OSError, ValueError, UnicodeError) as fallback:
                error += "；本地作业缓存不可用"
                error_en += "; local job cache unavailable: " + str(fallback)[:200]
        excluded = len(rows)
        rows = [row for row in rows if project_job(row.get("workdir"))]
        excluded -= len(rows)
        data = {"excluded_jobs": excluded if source is not None else None, "project_root": PROJECT_ROOT, "jobs": rows, "summary": job_summary(rows, source is not None), "source": source,
                "error": error, "error_zh": error, "error_en": error_en, "updated": timestamp(),
                "since": since, "source_timezone": source_timezone, "timezone": "CET",
                "cache_seconds": JOBS_CACHE_SECONDS, "cache_file_updated": cache_file_updated}
        _JOBS_CACHE.update(at=time.monotonic(), data=data)
        return data


def timestamp(epoch=None):
    """Always include an offset; the browser displays fixed CET (UTC+1)."""
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


def read_json(path, root=None):
    if not inside(path, root or ROOT):
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
        result["error_zh"] = result["error"]
        result["error_en"] = "status/{}.json unavailable; check file existence and JSON format".format(name)
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


def metrics(path, root=None):
    """Stream JSONL, retaining each split's first/last and a bounded sample."""
    if not inside(path, root or ROOT):
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
    directories = []
    roots = [ROOT] + ([REFERENCE_ROOT] if REFERENCE_ROOT and REFERENCE_ROOT != ROOT else [])
    for root in roots:
        for pattern in ("runs/*/metrics.jsonl", "robust/*/runs/*/metrics.jsonl", "artifacts/*/runs/*/metrics.jsonl"):
            for path in sorted(glob.glob(os.path.join(root, pattern))):
                if inside(path, root):
                    directories.append((root, os.path.dirname(path)))
    for root, directory in directories:
        metric_path = os.path.join(directory, "metrics.jsonl")
        if not os.path.isfile(metric_path) or not inside(metric_path, root):
            continue
        run = {"meta": {}, "rows": [], "warnings": []}
        meta_path = os.path.join(directory, "meta.json")
        if os.path.exists(meta_path):
            try:
                meta = read_json(meta_path, root)
                if not isinstance(meta, dict):
                    raise ValueError("meta.json 顶层必须是对象")
                run["meta"] = meta
            except (OSError, ValueError, UnicodeError) as exc:
                run["warnings"].append("meta.json 暂不可用：{}".format(exc))
        try:
            rows, total, skipped = metrics(metric_path, root)
            run.update(rows=rows, total_rows=total, sampled=len(rows) < total, skipped_lines=skipped)
            if skipped:
                run["warnings"].append("已跳过 {} 行不完整或无效指标".format(skipped))
            if run["sampled"]:
                run["warnings"].append("曲线已按 split 抽样；保留起点和最新点")
        except (OSError, ValueError) as exc:
            run["warnings"].append("metrics.jsonl 暂不可用：{}".format(exc))
        key = os.path.relpath(directory, root)
        # Preserve legacy IDs for runs/*, qualify nested runs to avoid collisions.
        if key.startswith("runs" + os.sep):
            key = os.path.basename(directory)
        if root != ROOT:
            key = "reference/" + key
        run["source"] = os.path.relpath(metric_path, root)
        run["reference"] = root != ROOT
        output[key] = run
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


def literature():
    rows = []
    try:
        with open(data_path("refs/literature.jsonl"), "r", encoding="utf-8", errors="replace") as source:
            for line in source:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if isinstance(item, dict):
                    rows.append(item)
    except (OSError, ValueError):
        pass
    return {"items": rows}


def command(args):
    if os.environ.get("DASH_OFFLINE", "1") != "0":
        return "", "DASH_OFFLINE=1: Slurm disabled / 已禁用 Slurm"
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
        parsed = parse_iso(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).isoformat()
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
    """Legacy routes share the exact same WorkDir-filtered evidence as /api/jobs."""
    data = jobs()
    return {"queue": [dict(row, time=row["elapsed"], limit=row["timelimit"], reason=None)
                      for row in data["jobs"] if row["state_code"] in ("RUNNING", "PENDING", "COMPLETING")],
            "history": data["jobs"], "queue_error": data["error"], "history_error": data["error"],
            "updated": data["updated"], "source": data["source"]}


def paper_root():
    if os.path.isdir(data_path("paper")) or not REFERENCE_ROOT:
        return ROOT
    return REFERENCE_ROOT


def paper_pdf_path():
    root = paper_root()
    path = os.path.join(root, "paper", "main.pdf")
    if not inside(path, os.path.join(root, "paper")):
        raise ValueError("PDF outside paper directory")
    return path


def paper():
    try:
        from .paper_stats import scan
    except ImportError:
        from paper_stats import scan
    result = status_file("paper", {})
    result.pop("error", None)
    result.pop("error_zh", None)
    result.pop("error_en", None)
    root = paper_root()
    result.update(scan(root))
    result["reference"] = root != ROOT
    result["source"] = "paper/main.tex"
    return result


def host():
    return {"host": os.uname()[1], "port": PORT, "time": timestamp()}


API = {
    "/api/host": host,
    "/api/phases": lambda: status_file("phases", {"updated": None, "phases": []}),
    "/api/dataset": lambda: status_file("dataset", {}),
    "/api/ideas": lambda: status_file("ideas", {"updated": None, "ideas": []}),
    "/api/jobs": jobs,
    "/api/highlights": lambda: status_file("highlights", {"cards": []}),
    "/api/paper": paper,
    "/api/job_purposes": lambda: status_file("job_purposes", {"purposes": {}}),
    "/api/results": results,
    "/api/runs": runs,
    "/api/logs": logs,
    "/api/progress": progress,
    "/api/literature": literature,
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
        if content_type == "application/pdf":
            self.send_header("Content-Disposition", 'inline; filename="main.pdf"')
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
        if path == "/paper.pdf":
            try:
                filename = paper_pdf_path()
                with open(filename, "rb") as source:
                    if source.read(5) != b"%PDF-":
                        raise ValueError("invalid PDF")
                    source.seek(0)
                    return self.send(200, source.read(), "application/pdf")
            except (OSError, ValueError):
                return self.send(404, "论文 PDF 暂不可用 / Paper PDF unavailable", "text/plain; charset=utf-8")
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
