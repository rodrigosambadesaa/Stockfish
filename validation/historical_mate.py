#!/usr/bin/env python3
"""Retrospective check against the exact Stockfish commit from issue #7221."""
import argparse
import json
from pathlib import Path
import chess
import chess.engine

OLD = """    // At non-PV nodes we check for an early TT cutoff
    if (!PvNode && ttData.depth >= DEPTH_QS && is_valid(ttData.value)
        && (ttData.bound & (ttData.value >= beta ? BOUND_LOWER : BOUND_UPPER)))
        return ttData.value;
"""
NEW = """    // At non-PV nodes we check for an early TT cutoff.
    // Only use conservative TT bounds after reducing decisive scores.
    if (!PvNode && ttData.depth >= DEPTH_QS && is_valid(ttData.value))
    {
        const Value boundedValue =
          std::clamp(ttData.value, VALUE_TB_LOSS_IN_MAX_PLY + 1, VALUE_TB_WIN_IN_MAX_PLY - 1);
        if (((ttData.bound & BOUND_LOWER) && boundedValue >= beta
             && boundedValue <= ttData.value)
            || ((ttData.bound & BOUND_UPPER) && boundedValue < beta
                && boundedValue >= ttData.value))
            return boundedValue;
    }
"""
FEN = "1k5n/1P3p2/1Kp1p1rr/1pp3p1/P7/1p6/1P1PPPPp/3b3R w - - 0 1"

def apply_patch():
    file = Path("historical-candidate/src/search.cpp")
    text=file.read_text()
    if text.count(OLD)!=1:
        raise RuntimeError("Historical source does not match expected qsearch code")
    file.write_text(text.replace(OLD,NEW))
    print("Patched historical qsearch block (one occurrence)",flush=True)

def analyse(path,hash_mib):
    with chess.engine.SimpleEngine.popen_uci(str(Path(path).resolve()), timeout=240) as engine:
        engine.configure({"Hash":hash_mib,"Threads":1})
        info=engine.analyse(chess.Board(FEN),chess.engine.Limit(mate=5,depth=128,nodes=10_000_000))
    pv=info.get("pv",[])
    board=chess.Board(FEN)
    for m in pv:
        if m not in board.legal_moves:
            raise AssertionError(f"Illegal PV: {m.uci()}")
        board.push(m)
    return {"mate": info["score"].pov(chess.WHITE).mate(),
            "depth":info.get("depth"),
            "nodes":info.get("nodes"),
            "pv":" ".join(m.uci() for m in pv),
            "complete":board.is_checkmate()}

def compare():
    out=[]
    for hash_mib in (1,16,64):
        rec={"hash_mib":hash_mib,
             "baseline":analyse("historical-base/src/stockfish",hash_mib),
             "candidate":analyse("historical-candidate/src/stockfish",hash_mib)}
        out.append(rec)
        print("HISTORICAL",json.dumps(rec),flush=True)
    Path("historical-bug-study.json").write_text(json.dumps(out,indent=2)+"\n")
    print("SUMMARY",json.dumps({
        "trials":len(out),
        "baseline_false_mate5":sum(r["baseline"]["mate"]==5 for r in out),
        "candidate_false_mate5":sum(r["candidate"]["mate"]==5 for r in out)
    }),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--apply",action="store_true")
    args=p.parse_args()
    if args.apply: apply_patch()
    else: compare()
