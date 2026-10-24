#!/usr/bin/env python3
"""Backport the *exact* current candidate qsearch block and check #7221."""
import json
import sys
from pathlib import Path

import chess
import chess.engine

START="    // At non-PV nodes we check for an early TT cutoff"
END="    // Step 4. Static evaluation of the position"
FEN="1k5n/1P3p2/1Kp1p1rr/1pp3p1/P7/1p6/1P1PPPPp/3b3R w - - 0 1"

def patch():
    current=Path("candidate/src/search.cpp").read_text()
    hist=Path("historical-patched/src/search.cpp")
    old=hist.read_text()
    assert current.count(START)==1 and old.count(START)==1
    assert current.count(END)==1 and old.count(END)==1
    cblock=current[current.index(START):current.index(END)]
    hblock=old[old.index(START):old.index(END)]
    hist.write_text(old.replace(hblock,cblock))
    assert "An upper bound must never become stronger." in hist.read_text()
    print("Backported exact current candidate qsearch block",flush=True)

def run(path,hash_mb):
    with chess.engine.SimpleEngine.popen_uci(str(Path(path).resolve()),timeout=240) as eng:
        eng.configure({"Hash":hash_mb,"Threads":1})
        res=eng.analyse(chess.Board(FEN),chess.engine.Limit(mate=5,depth=128,nodes=10_000_000))
        pv=res.get("pv",[])
        return {"mate":res["score"].pov(chess.WHITE).mate(),
                "nodes":res.get("nodes"),"depth":res.get("depth"),
                "pv":" ".join(m.uci() for m in pv)}

def check():
    pairs=[]
    for h in [1,16,64]:
        base=run("historical/src/stockfish",h)
        test=run("historical-patched/src/stockfish",h)
        pairs.append({"hash":h,"base":base,"candidate":test})
        print("COMPARE",json.dumps(pairs[-1]),flush=True)
    Path("upper-historical.json").write_text(json.dumps(pairs,indent=2)+"\n")
    actual=[x for x in pairs if x["base"]["mate"]==5]
    if not actual:
        raise AssertionError("Historical M5 did not reproduce: validation inconclusive")
    if any(x["candidate"]["mate"]==5 for x in actual):
        raise AssertionError("Candidate still reports false M5 on a reproduced case")
    print("SUCCESS: invalid M5 suppressed in",len(actual),"reproduced cases",flush=True)

if __name__=="__main__":
    if sys.argv[1:] == ["--patch"]: patch()
    else: check()
