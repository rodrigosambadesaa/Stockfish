#!/usr/bin/env python3
"""Interleaved local bench time comparison; not an Elo or reproducible NPS benchmark."""
import json
import re
import statistics
import subprocess
from pathlib import Path

PATTERNS = {
    "nodes": re.compile(r"Nodes searched\s*:\s*(\d+)"),
    "elapsed_ms": re.compile(r"Total time \(ms\)\s*:\s*(\d+)"),
    "nps": re.compile(r"Nodes/second\s*:\s*(\d+)"),
}

def bench(path):
    r = subprocess.run([str(Path(path).resolve()), "bench"], capture_output=True,
                       text=True, timeout=180, check=True)
    output = r.stdout + "\n" + r.stderr
    values = {}
    for key, p in PATTERNS.items():
        m = p.search(output)
        if not m:
            raise AssertionError(f"Missing {key} in benchmark: {output[-3000:]}")
        values[key] = int(m.group(1))
    if values["nodes"] < 100000 or values["elapsed_ms"] <= 0:
        raise AssertionError(f"Invalid benchmark {values}")
    return values

def main():
    paths = {"base": "baseline/src/stockfish",
             "candidate": "candidate/src/stockfish"}
    bench(paths["base"])
    bench(paths["candidate"])
    data={"base":[],"candidate":[]}
    for i in range(5):
        order = ["base","candidate"] if i % 2 == 0 else ["candidate","base"]
        for which in order:
            value=bench(paths[which])
            data[which].append(value)
            print(f"TRIAL {i + 1} {which} {json.dumps(value)}",flush=True)
    medians={name:{x: statistics.median(v[x] for v in values)
                     for x in PATTERNS} for name,values in data.items()}
    report={"medians":medians, "runs":data,
            "ratio_elapsed_candidate_over_base":
              medians["candidate"]["elapsed_ms"]/medians["base"]["elapsed_ms"],
            "ratio_nodes_candidate_over_base":
              medians["candidate"]["nodes"]/medians["base"]["nodes"],
            "ratio_nps_candidate_over_base":
              medians["candidate"]["nps"]/medians["base"]["nps"]}
    Path("qsearch-bench-cost.json").write_text(json.dumps(report,indent=2)+"\n")
    print("SUMMARY",json.dumps(report["medians"]|{k:v for k,v in report.items() if k.startswith("ratio_")}),flush=True)

if __name__=="__main__":
    main()
