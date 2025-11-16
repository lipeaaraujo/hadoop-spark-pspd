#!/usr/bin/env python3
"""Automate WordCount fault-tolerance experiments on the local Docker Hadoop cluster."""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parents[1]
SHARED_DIR = BASE_DIR / "shared"
REPORTS_DIR = SHARED_DIR / "reports"
HADOOP_BIN = "/usr/local/hadoop/bin/hadoop"
HDFS_BIN = "/usr/local/hadoop/bin/hdfs"
YARN_BIN = "/usr/local/hadoop/bin/yarn"
MAPRED_BIN = "/usr/local/hadoop/bin/mapred"
HADOOP_SBIN = "/usr/local/hadoop/sbin"
HADOOP_JAR = "/usr/local/hadoop/share/hadoop/mapreduce/hadoop-mapreduce-examples-2.7.4.jar"
WORDCOUNT_CMD = (
    f"{HADOOP_BIN} jar {HADOOP_JAR} wordcount "
    "-D mapreduce.input.fileinputformat.input.dir.recursive=true "
    "/datasets/wordcount /results/wordcount-run"
)
CONTAINERS = ["hadoop-master", "hadoop-slave1", "hadoop-slave2"]
APP_ID_RE = re.compile(r"application_\d+_\d+")
PROGRESS_RE = re.compile(r"Progress\s*:\s*([0-9.]+)%")
STATE_RE = re.compile(r"State\s*:\s*(\w+)")
FINAL_STATE_RE = re.compile(r"Final-State\s*:\s*(\w+)")
AM_HOST_RE = re.compile(r"AM Host\s*:\s*([\w-]+)")
START_RE = re.compile(r"Start-Time\s*:\s*(\d+)")
FINISH_RE = re.compile(r"Finish-Time\s*:\s*(\d+)")
AGG_RE = re.compile(r"Aggregate Resource Allocation\s*:\s*([0-9 ]+\w+-seconds, [0-9 ]+vcore-seconds)")
NODE_LINE_RE = re.compile(r"^(\S+):\d+\s+(\w+)")


def run(cmd: List[str], *, check: bool = True, capture: bool = True, text: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, capture_output=capture, text=text)


def docker_exec(container: str, command: str, *, check: bool = True) -> subprocess.CompletedProcess:
    full_cmd = ["docker", "exec", "-i", container, "bash", "-lc", command]
    return run(full_cmd, check=check, capture=True)


def docker_run(cmd: List[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return run(cmd, check=check, capture=True)


def is_container_running(name: str) -> bool:
    result = run(["docker", "inspect", "-f", "{{.State.Running}}", name], check=False)
    return result.returncode == 0 and result.stdout.strip() == "true"


def ensure_container(name: str) -> None:
    if not is_container_running(name):
        print(f"[orchestrator] starting container {name}")
        docker_run(["docker", "start", name])
    wait_for_container(name)


def wait_for_container(name: str, timeout: int = 60) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = run(["docker", "exec", name, "true"], check=False)
        if result.returncode == 0:
            return
        time.sleep(2)
    raise RuntimeError(f"container {name} not reachable after {timeout}s")


def ensure_master_services() -> None:
    print("[orchestrator] ensuring HDFS/YARN services on master")
    docker_exec(
        "hadoop-master",
        f"{HADOOP_SBIN}/start-dfs.sh >/dev/null 2>&1 || true; "
        f"{HADOOP_SBIN}/start-yarn.sh >/dev/null 2>&1 || true; "
        f"{HADOOP_SBIN}/mr-jobhistory-daemon.sh start historyserver >/dev/null 2>&1 || true",
    )


def ensure_slave_services(slave: str) -> None:
    print(f"[orchestrator] ensuring DataNode/NodeManager on {slave}")
    docker_exec(slave, f"{HADOOP_SBIN}/hadoop-daemon.sh start datanode >/dev/null 2>&1 || true")
    docker_exec(slave, f"{HADOOP_SBIN}/yarn-daemon.sh start nodemanager >/dev/null 2>&1 || true")


def wait_for_hdfs(timeout: int = 120, interval: int = 5) -> None:
    """Block until the NameNode answers DFS commands."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = docker_exec("hadoop-master", f"{HDFS_BIN} dfs -ls / >/dev/null 2>&1", check=False)
        if result.returncode == 0:
            return
        time.sleep(interval)
    raise RuntimeError(f"HDFS unavailable after {timeout}s; check NameNode logs")


def prep_dataset(force: bool) -> None:
    if force:
        docker_exec("hadoop-master", "bash /shared/generate_wordcount_data.sh")
        docker_exec("hadoop-master", "bash /shared/download_gutenberg_corpus.sh")
    docker_exec(
        "hadoop-master",
        f"{HDFS_BIN} dfs -test -d /datasets/wordcount || "
        f"({HDFS_BIN} dfs -mkdir -p /datasets/wordcount && {HDFS_BIN} dfs -put -f /shared/wordcount-data/* /datasets/wordcount/)",
    )


def launch_job(log_path_container: str) -> None:
    quoted_log = shlex.quote(log_path_container)
    command = (
        f"LOG={quoted_log}; mkdir -p $(dirname $LOG); rm -f $LOG; "
        f"nohup bash -lc \"{HDFS_BIN} dfs -rm -r -f /results/wordcount-run >/dev/null 2>&1; "
        f"{WORDCOUNT_CMD}\" >> $LOG 2>&1 & echo $!"
    )
    result = docker_exec("hadoop-master", command)
    pid = result.stdout.strip()
    print(f"[orchestrator] launched WordCount (PID {pid}) logging to {log_path_container}")


def wait_for_application_id(log_file: Path, timeout: int = 120) -> str:
    print("[orchestrator] waiting for application ID in log")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if log_file.exists():
            text = log_file.read_text(errors="ignore")
            match = APP_ID_RE.search(text)
            if match:
                app_id = match.group(0)
                print(f"[orchestrator] detected application {app_id}")
                return app_id
        time.sleep(2)
    raise RuntimeError("application ID not found in log within timeout")


def get_application_report(app_id: str) -> Optional[Dict[str, object]]:
    try:
        result = docker_exec("hadoop-master", f"{YARN_BIN} application -status {app_id}")
    except subprocess.CalledProcessError:
        return None
    payload = result.stdout
    report: Dict[str, object] = {"raw": payload}
    if m := PROGRESS_RE.search(payload):
        report["progress"] = float(m.group(1))
    if m := STATE_RE.search(payload):
        report["state"] = m.group(1)
    if m := FINAL_STATE_RE.search(payload):
        report["final_state"] = m.group(1)
    if m := AM_HOST_RE.search(payload):
        report["am_host"] = m.group(1)
    if m := START_RE.search(payload):
        report["start_time_ms"] = int(m.group(1))
    if m := FINISH_RE.search(payload):
        report["finish_time_ms"] = int(m.group(1))
    if m := AGG_RE.search(payload):
        report["aggregate"] = m.group(1).strip()
    return report


def get_node_summary() -> Optional[Dict[str, object]]:
    try:
        result = docker_exec("hadoop-master", f"{YARN_BIN} node -list")
    except subprocess.CalledProcessError:
        return None
    running = 0
    states: Dict[str, str] = {}
    for line in result.stdout.splitlines():
        match = NODE_LINE_RE.search(line.strip())
        if match:
            node, state = match.group(1), match.group(2)
            states[node] = state
            if state == "RUNNING":
                running += 1
    return {"running": running, "states": states}


def get_job_status(job_id: str) -> str:
    for attempt in range(6):
        try:
            result = docker_exec("hadoop-master", f"{MAPRED_BIN} job -status {job_id}")
            return result.stdout
        except subprocess.CalledProcessError as exc:
            last_error = exc
            time.sleep(5)
    raise last_error  # type: ignore[misc]


def perform_event(event: Dict[str, object], log_file, elapsed: Optional[float]) -> None:
    target = event["target"]
    downtime = int(event["downtime"])
    now = datetime.now(timezone.utc).isoformat()
    print(f"[event] stopping {target} for {downtime}s")
    docker_run(["docker", "stop", target])
    log_file.write(json.dumps({
        "type": "event",
        "timestamp": now,
        "event": "stop",
        "target": target,
        "downtime_s": downtime,
        "elapsed_s": elapsed,
    }) + "\n")
    log_file.flush()
    time.sleep(downtime)
    print(f"[event] starting {target}")
    docker_run(["docker", "start", target])
    wait_for_container(target)
    if target == "hadoop-master":
        ensure_master_services()
        wait_for_hdfs()
    else:
        ensure_slave_services(target)
    log_file.write(json.dumps({
        "type": "event",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": "start",
        "target": target,
        "elapsed_s": elapsed,
    }) + "\n")
    log_file.flush()


def monitor(app_id: str, jsonl_path: Path, events: List[Dict[str, object]], poll: int) -> Dict[str, object]:
    events_sorted = sorted(events, key=lambda e: e["offset"])
    next_event_idx = 0
    triggered: List[Dict[str, object]] = []
    start_epoch = None

    with jsonl_path.open("w", encoding="utf-8") as log_file:
        last_progress = 0.0
        while True:
            report = get_application_report(app_id)
            now = datetime.now(timezone.utc)
            if report and "start_time_ms" in report and start_epoch is None:
                start_epoch = report["start_time_ms"] / 1000.0
            elapsed = None
            if start_epoch:
                elapsed = time.time() - start_epoch
            if report:
                progress = float(report.get("progress", last_progress))
                last_progress = progress
                state = str(report.get("state", "UNKNOWN"))
                node_info = get_node_summary()
                entry = {
                    "type": "sample",
                    "timestamp": now.isoformat(),
                    "elapsed_s": elapsed,
                    "progress": progress,
                    "state": state,
                    "final_state": report.get("final_state"),
                    "am_host": report.get("am_host"),
                    "live_nodes": node_info.get("running") if node_info else None,
                    "node_states": node_info.get("states") if node_info else None,
                }
                log_file.write(json.dumps(entry) + "\n")
                log_file.flush()
                if state in {"FINISHED", "FAILED", "KILLED"}:
                    return {
                        "report": report,
                        "events": triggered,
                        "log": str(jsonl_path),
                        "last_progress": progress,
                    }
            else:
                entry = {
                    "type": "sample",
                    "timestamp": now.isoformat(),
                    "elapsed_s": elapsed,
                    "progress": last_progress,
                    "state": "MASTER_UNAVAILABLE",
                }
                log_file.write(json.dumps(entry) + "\n")
                log_file.flush()

            if (
                next_event_idx < len(events_sorted)
                and elapsed is not None
                and elapsed >= events_sorted[next_event_idx]["offset"]
            ):
                event = events_sorted[next_event_idx]
                perform_event(event, log_file, elapsed)
                event_record = {
                    "target": event["target"],
                    "offset": event["offset"],
                    "downtime": event["downtime"],
                    "executed_at_s": elapsed,
                }
                triggered.append(event_record)
                next_event_idx += 1

            time.sleep(poll)


def parse_event(value: str) -> Dict[str, object]:
    # Format: target:offset:downtime (seconds)
    parts = value.split(":")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("event format must be target:offset:downtime")
    target, offset, downtime = parts
    if target not in CONTAINERS:
        raise argparse.ArgumentTypeError(f"unknown container '{target}'")
    return {
        "target": target,
        "offset": int(offset),
        "downtime": int(downtime),
        "description": f"Stop {target} after {offset}s for {downtime}s",
    }


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automate Hadoop fault-tolerance experiments.")
    parser.add_argument(
        "--prep-data",
        action="store_true",
        help="regenerate synthetic data, download Gutenberg corpus e reenviar ao HDFS",
    )
    parser.add_argument(
        "--poll",
        type=int,
        default=30,
        help="intervalo (s) entre amostras do YARN",
    )
    parser.add_argument(
        "--event",
        action="append",
        type=parse_event,
        help="evento no formato alvo:offset:downtime (em segundos)",
    )
    parser.add_argument(
        "--skip-ensure",
        action="store_true",
        help="não tentar iniciar automaticamente os containers (assume cluster já ativo)",
    )
    return parser.parse_args(argv)


def default_events() -> List[Dict[str, object]]:
    return [
        {"target": "hadoop-slave1", "offset": 120, "downtime": 60},
        {"target": "hadoop-slave2", "offset": 420, "downtime": 60},
        {"target": "hadoop-master", "offset": 840, "downtime": 60},
    ]


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    if not SHARED_DIR.exists():
        raise SystemExit(f"shared directory not found at {SHARED_DIR}")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    if not args.skip_ensure:
        for container in CONTAINERS:
            ensure_container(container)

    ensure_master_services()
    ensure_slave_services("hadoop-slave1")
    ensure_slave_services("hadoop-slave2")
    wait_for_hdfs()

    prep_dataset(args.prep_data)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    prefix = f"fault_test_{timestamp}"
    log_host = REPORTS_DIR / f"{prefix}.job.log"
    jsonl_path = REPORTS_DIR / f"{prefix}.jsonl"
    summary_path = REPORTS_DIR / f"{prefix}.summary.json"

    launch_job(f"/shared/reports/{prefix}.job.log")
    app_id = wait_for_application_id(log_host)

    events = args.event if args.event else default_events()
    for e in events:
        e.setdefault("description", f"Stop {e['target']}")

    monitor_result = monitor(app_id, jsonl_path, events, args.poll)
    report = monitor_result["report"]
    job_id = app_id.replace("application", "job")
    job_status = get_job_status(job_id)

    start_ms = report.get("start_time_ms")
    finish_ms = report.get("finish_time_ms")
    duration = None
    if start_ms and finish_ms:
        duration = (finish_ms - start_ms) / 1000.0

    summary = {
        "app_id": app_id,
        "job_id": job_id,
        "start_time_ms": start_ms,
        "finish_time_ms": finish_ms,
        "duration_seconds": duration,
        "state": report.get("state"),
        "final_state": report.get("final_state"),
        "aggregate": report.get("aggregate"),
        "events": monitor_result["events"],
        "log_jsonl": str(jsonl_path.relative_to(REPORTS_DIR.parent.parent))
        if REPORTS_DIR.parent.parent in jsonl_path.parents
        else str(jsonl_path),
        "job_status_raw": job_status,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n=== Experimento concluído ===")
    print(json.dumps(summary, indent=2))
    print(f"\nArquivos gerados em {REPORTS_DIR}")
    print(f" - Log do WordCount: {log_host.name}")
    print(f" - Série temporal: {jsonl_path.name}")
    print(f" - Resumo: {summary_path.name}")
    print("Use plot_fault_report.py para gerar gráficos.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário.")
        raise
