#!/usr/bin/env python3
"""Reproducible MultiPV mate-report study, not an Elo or mate-proof test.

Run original and candidate engines against published Stockfish issue #7247
examples with identical nodes, hash, threads and requested MultiPV.
Discriminate complete vs incomplete mate PVs and scores shorter than the
issue author's independently investigated mate lengths.
"""
import argparse
import json
from pathlib import Path
import chess
import chess.engine

CASES = {
    "A": ("8/1pNKp3/1B2P3/1P6/1pNP4/1k6/1P6/1B6 w - - 0 1", "c7a8", 9),
    "B": ("8/2b5/4Q3/3P1p1P/8/5P2/p1p2P2/k3K3 w - - 0 1", "e6e7", 8),
    "C": ("2r5/4N2p/4N2k/1q3pR1/8/B2b3K/7P/3n3B w - - 0 1", "h1g2", 11),
}


def inspect(fen, info, target):
    board = chess.Board(fen)
    pv = info.get("pv") or []
    for move in pv:
        if move not in board.legal_moves:
            raise AssertionError(f"Illegal PV from {fen}: {move.uci()}")
        board.push(move)
    mate = info["score"].pov(chess.Board(fen).turn).mate() if "score" in info else None
    winner_is_origin = (board.turn != chess.Board(fen).turn)
    complete = mate is not None and board.is_checkmate()
    if complete:
        required = 2 * mate - 1 if mate > 0 else -2 * mate
        if len(pv) != required or winner_is_origin != (mate > 0):
            raise AssertionError(f"Inconsistent complete mate PV: mate {mate}, length {len(pv)}")
    return {
        "root": pv[0].uci() if pv else None,
        "mate": mate,
        "score": str(info["score"].pov(chess.Board(fen).turn)) if "score" in info else None,
        "complete": complete,
        "bound": "lower" if info.get("lowerbound") else "upper" if info.get("upperbound") else "unspecified",
        "depth": info.get("depth"),
        "nodes": info.get("nodes"),
        "pv": " ".join(x.uci() for x in pv),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--case", choices=CASES, required=True)
    p.add_argument("--base", required=True)
    p.add_argument("--candidate", required=True)
    args = p.parse_args()

    fen, target, reported_min_mate = CASES[args.case]
    board = chess.Board(fen)
    configs = [(1, 8_000_000), (16, 8_000_000), (16, 30_000_000),
               (64, 8_000_000)]
    records = []
    for hsh, nodes in configs:
        pair = {"case": args.case, "hash_mib": hsh, "node_budget": nodes,
                "move": target, "minimum_mate_length_reported_in_issue": reported_min_mate}
        for name, path in [("base", args.base), ("candidate", args.candidate)]:
            # Separate processes deliberately: reproducible fresh TT per trial.
            with chess.engine.SimpleEngine.popen_uci(str(Path(path).resolve()), timeout=360) as engine:
                engine.configure({"Threads": 1, "Hash": hsh})
                infos = engine.analyse(board, chess.engine.Limit(nodes=nodes),
                                       multipv=board.legal_moves.count(),
                                       info=chess.engine.INFO_ALL)
            matching = [inspect(fen, x, target) for x in infos
                        if x.get("pv") and x["pv"][0].uci() == target]
            if len(matching) != 1:
                raise AssertionError(f"Expected root line {target}, got {len(matching)} ({name})")
            info = matching[0]
            # Diagnostic ONLY: author's claimed minimum has not been independently
            # exhaustively proven by this script.
            info["shorter_than_reported"] = (info["mate"] is not None
                and abs(info["mate"]) < reported_min_mate)
            pair[name] = info
        records.append(pair)
        print("PAIR", json.dumps({
            "case": args.case, "hash": hsh, "nodes": nodes,
            "base_mate": pair["base"]["mate"],
            "candidate_mate": pair["candidate"]["mate"],
            "base_short": pair["base"]["shorter_than_reported"],
            "candidate_short": pair["candidate"]["shorter_than_reported"],
        }), flush=True)

    summary = {
        "case": args.case, "trials": len(records),
        "base_shorter": sum(x["base"]["shorter_than_reported"] for x in records),
        "candidate_shorter": sum(x["candidate"]["shorter_than_reported"] for x in records),
        "candidate_better": sum(x["base"]["shorter_than_reported"]
            and not x["candidate"]["shorter_than_reported"] for x in records),
        "candidate_worse": sum(x["candidate"]["shorter_than_reported"]
            and not x["base"]["shorter_than_reported"] for x in records)
    }
    Path(f"mate-evidence-{args.case}.json").write_text(
        json.dumps({"summary": summary, "records": records}, indent=2) + "\n")
    print("SUMMARY", json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
