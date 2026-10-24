#!/usr/bin/env python3
"""Record bench cost and the historical issue #7221 mate report for one policy."""
import json, pathlib, re, statistics, subprocess
import chess, chess.engine

fen="1k5n/1P3p2/1Kp1p1rr/1pp3p1/P7/1p6/1P1PPPPp/3b3R w - - 0 1"

def bench():
    p=subprocess.run(["./current/src/stockfish","bench"],capture_output=True,text=True,timeout=120,check=True)
    out=p.stdout+"\n"+p.stderr
    result={}
    for key,expr in (("nodes",r"Nodes searched\s*:\s*(\d+)"),("milliseconds",r"Total time \(ms\)\s*:\s*(\d+)"),("nps",r"Nodes/second\s*:\s*(\d+)")):
        m=re.search(expr,out)
        if not m: raise RuntimeError(f"Missing {key}: {out[-2500:]}")
        result[key]=int(m.group(1))
    return result

def historical():
    engine=chess.engine.SimpleEngine.popen_uci(str(pathlib.Path("historical/src/stockfish").resolve()),timeout=240)
    try:
        engine.configure({"Hash":16,"Threads":1})
        info=engine.analyse(chess.Board(fen),chess.engine.Limit(mate=5,depth=128,nodes=10_000_000))
        moves=info.get("pv",[])
        return {"mate":info["score"].pov(chess.WHITE).mate(),
                "nodes":info.get("nodes"),"depth":info.get("depth"),
                "pv":" ".join(m.uci() for m in moves)}
    finally: engine.quit()

values=[bench() for _ in range(3)]
h=historical()
data={"bench_nodes":values[0]["nodes"],"median_bench_ms":statistics.median(x["milliseconds"] for x in values),
      "median_nps":statistics.median(x["nps"] for x in values),"historical":h,"all_benches":values}
print("RESULT",json.dumps(data),flush=True)
pathlib.Path("selective-result.json").write_text(json.dumps(data,indent=2)+"\n")
