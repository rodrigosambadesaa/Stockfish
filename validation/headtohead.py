#!/usr/bin/env python3
"""Small paired-color local screening match; NOT statistically sufficient for Elo."""
import json
import random
import chess
import chess.engine

SEED = 7247
NODES = 10000
NUM_OPENINGS = 16
MAX_PLIES = 160


def openings():
    rng = random.Random(SEED)
    out = []
    for i in range(NUM_OPENINGS):
        b = chess.Board()
        for _ in range(6 + 2 * (i % 5)):
            moves = sorted(b.legal_moves, key=lambda m: m.uci())
            if not moves:
                break
            b.push(moves[rng.randrange(len(moves))])
        if b.is_game_over():
            raise RuntimeError(f"Unexpected ended opening {i}")
        out.append(b)
    return out


def main():
    base = chess.engine.SimpleEngine.popen_uci("baseline/src/stockfish", timeout=120)
    test = chess.engine.SimpleEngine.popen_uci("candidate/src/stockfish", timeout=120)
    try:
        base.configure({"Hash": 16, "Threads": 1})
        test.configure({"Hash": 16, "Threads": 1})
        summary = {"candidate_wins": 0, "base_wins": 0, "draws": 0, "games": []}
        for index, opening in enumerate(openings()):
            for swapped in (False, True):
                board = opening.copy(stack=False)
                # Paired opening: each engine plays White once and Black once.
                white = test if swapped else base
                black = base if swapped else test
                token = object()
                plies = 0
                while plies < MAX_PLIES and not board.is_game_over(claim_draw=True):
                    engine = white if board.turn else black
                    result = engine.play(board, chess.engine.Limit(nodes=NODES), game=token)
                    if result.move not in board.legal_moves:
                        raise RuntimeError(f"Illegal move in game {index}/{swapped}")
                    board.push(result.move)
                    plies += 1
                outcome = board.outcome(claim_draw=True)
                winner = outcome.winner if outcome is not None else None
                name = "draws"
                if winner is not None:
                    name = "candidate_wins" if (winner == chess.WHITE and white is test) or (winner == chess.BLACK and black is test) else "base_wins"
                summary[name] += 1
                summary["games"].append({
                    "opening": index, "candidate_white": swapped, "plies": plies,
                    "result": board.result(claim_draw=True) if outcome else "1/2-1/2",
                    "winner": name, "termination": str(outcome.termination) if outcome else "ply_limit",
                })
                print(f"Opening {index}, candidate white={swapped}, plies={plies}, {name}", flush=True)
        with open("headtohead.json", "w") as f:
            json.dump(summary, f, indent=2)
        print("RESULTS", json.dumps({k: v for k, v in summary.items() if k != "games"}), flush=True)
        print("NOTE: A few dozen very short games cannot establish Elo gain.", flush=True)
    finally:
        base.quit()
        test.quit()


if __name__ == "__main__":
    main()
