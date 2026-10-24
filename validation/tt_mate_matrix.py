#!/usr/bin/env python3
"""Differential UCI analysis for the experimental Stockfish TT qsearch change.

Not a proof of optimal play or Elo gain: compare many scenarios and validate
mate-PV consistency, rather than asserting equality of the engine's move choices.
"""
import argparse
import json
import random
from pathlib import Path

import chess
import chess.engine

ISSUES = [
    ("multipv_7247_a", "8/1pNKp3/1B2P3/1P6/1pNP4/1k6/1P6/1B6 w - - 0 1"),
    ("multipv_7247_b", "8/2b5/4Q3/3P1p1P/8/5P2/p1p2P2/k3K3 w - - 0 1"),
    ("multipv_7247_c", "2r5/4N2p/4N2k/1q3pR1/8/B2b3K/7P/3n3B w - - 0 1"),
]
KNOWN_MATES = [
    ("KQK_white_mate1", "7k/8/5KQ1/8/8/8/8/8 w - - 0 1"),
    ("KQK_black_mate1", "8/8/8/8/8/5kq1/8/7K b - - 0 1"),
]
SEED = 7247


def positions():
    rng = random.Random(SEED)
    boards = list(ISSUES) + list(KNOWN_MATES)
    for index in range(36):
        board = chess.Board()
        target = 4 + (index % 9) * 9
        for _ in range(target):
            if board.is_game_over():
                break
            moves = sorted(board.legal_moves, key=lambda m: m.uci())
            board.push(moves[rng.randrange(len(moves))])
        if not board.is_game_over() and board.is_valid():
            boards.append((f"random_{index:02d}", board.fen()))
    return boards


def inspect_line(fen, info):
    board = chess.Board(fen)
    origin = board.turn
    pv = info.get("pv", [])
    mistakes = []
    for move in pv:
        if move not in board.legal_moves:
            mistakes.append(f"illegal PV move {move.uci()}")
            break
        board.push(move)
    mate = None
    if "score" in info:
        mate = info["score"].pov(origin).mate()
    if mate is not None and board.is_checkmate():
        required = 2 * mate - 1 if mate > 0 else -2 * mate
        if len(pv) != required:
            mistakes.append(
                f"announced mate {mate}, actual PV length {len(pv)} != {required}"
            )
    # Some PVs are inexact/incomplete, so their failure to end in mate is not
    # proof of a false mate; record it as a diagnostic, not a hard failure.
    incomplete = mate is not None and not board.is_checkmate()
    if mate is not None and not incomplete and (board.turn == origin) == (mate > 0):
        mistakes.append(f"mate {mate} winner disagrees with PV terminal board")
    return {
        "score_cp": info.get("score").pov(origin).score(mate_score=100000)
                    if info.get("score") else None,
        "mate": mate,
        "pv": " ".join(m.uci() for m in pv),
        "pv_len": len(pv),
        "pv_checkmate": board.is_checkmate(),
        "incomplete_mate_pv": incomplete,
        "errors": mistakes,
    }


def run_engine(path, configs):
    output = {}
    with chess.engine.SimpleEngine.popen_uci(str(Path(path).resolve()), timeout=240) as eng:
        for key, fen, hsh, threads, mpv, nodes in configs:
            board = chess.Board(fen)
            eng.configure({"Hash": hsh, "Threads": threads})
            eng.configure({"MultiPV": min(mpv, board.legal_moves.count())})
            # New game resets TT / histories, keeping runs comparable.
            eng.protocol._ucinewgame = None
            result = eng.analyse(board, chess.engine.Limit(nodes=nodes),
                                 multipv=min(mpv, board.legal_moves.count()),
                                 game=object(), info=chess.engine.INFO_ALL)
            if isinstance(result, dict):
                result = [result]
            lines = [inspect_line(fen, i) for i in result]
            output[key] = lines
            print(f"{path} | {key} | depth={max((i.get('depth', 0) for i in result),default=0)}"
                  f" lines={len(lines)} mates={sum(x['mate'] is not None for x in lines)}"
                  f" errors={sum(len(x['errors']) for x in lines)}", flush=True)
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base")
    parser.add_argument("candidate")
    parser.add_argument("--suite", choices=["small", "large", "diverse"], required=True)
    args = parser.parse_args()
    fixtures = positions()
    if args.suite == "small":
        configs = [(f"{label}:hash{h}:mpv64", fen, h, 1, 64, 2000000)
                   for label, fen in ISSUES for h in (1, 16)]
    elif args.suite == "large":
        configs = [(f"{label}:hash{h}:mpv256", fen, h, 1, 256, 8000000)
                   for label, fen in ISSUES for h in (16, 128)]
    else:
        configs = [(f"{label}:hash{h}:threads{t}:mpv{m}", fen, h, t, m, 80000)
                   for label, fen in fixtures[3:]
                   for h, t, m in ((1, 1, 1), (16, 1, 4), (128, 2, 4))]
    print(f"Running {len(configs)} scenarios, seed {SEED}", flush=True)
    a = run_engine(args.base, configs)
    b = run_engine(args.candidate, configs)
    failures = []
    deltas = []
    for key, *_ in configs:
        v1, v2 = a[key], b[key]
        for label, vv in (("base", v1), ("candidate", v2)):
            for item in vv:
                if item["errors"]:
                    failures.append({"scenario": key, "engine": label, "errors": item["errors"]})
        for i in range(min(len(v1), len(v2))):
            if v1[i]["score_cp"] != v2[i]["score_cp"] or v1[i]["pv"] != v2[i]["pv"]:
                deltas.append({"scenario": key, "rank": i + 1,
                               "base_mate": v1[i]["mate"], "test_mate": v2[i]["mate"],
                               "base_cp": v1[i]["score_cp"], "test_cp": v2[i]["score_cp"]})
    result = {
        "suite": args.suite, "seed": SEED, "scenarios": len(configs),
        "differences": len(deltas), "first_differences": deltas[:60],
        "errors": failures,
        "incomplete_base": sum(x["incomplete_mate_pv"] for v in a.values() for x in v),
        "incomplete_candidate": sum(x["incomplete_mate_pv"] for v in b.values() for x in v),
    }
    Path(f"mate-matrix-{args.suite}.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print("SUMMARY", json.dumps({k: v for k, v in result.items()
                                 if k not in ("first_differences", "errors")}), flush=True)
    for diff in deltas[:12]:
        print("DIFFERENCE", json.dumps(diff), flush=True)
    for err in failures[:12]:
        print("ERROR", json.dumps(err), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
