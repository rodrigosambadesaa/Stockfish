#!/usr/bin/env python3
"""Paired opening strength screen. NOT an Elo confirmation; no adjudicated draws."""
import argparse
import json
import random
from pathlib import Path
import chess
import chess.engine

SEED = 724719
MAX_PLIES = 180
OPENINGS = 24

def openings():
    rng = random.Random(SEED)
    for i in range(OPENINGS):
        board = chess.Board()
        for _ in range(8 + 2 * (i % 7)):
            choices = sorted(board.legal_moves, key=lambda m:m.uci())
            if board.is_game_over() or not choices:
                break
            board.push(rng.choice(choices))
        if not board.is_game_over(claim_draw=True):
            yield i, board

def run_game(board, white, black, candidate_white, nodes, token):
    plies = 0
    while plies < MAX_PLIES and not board.is_game_over(claim_draw=True):
        player = white if board.turn else black
        response = player.play(board, chess.engine.Limit(nodes=nodes), game=token)
        if response.move not in board.legal_moves:
            raise AssertionError(f"Illegal move {response.move} at {board.fen()}")
        board.push(response.move)
        plies += 1
    result=board.outcome(claim_draw=True)
    if result is None:
        winner="unfinished"
    elif result.winner is None:
        winner="draw"
    elif result.winner == candidate_white:
        winner="candidate"
    else:
        winner="baseline"
    return {
        "winner":winner,
        "plies":plies,
        "termination":result.termination.name if result else "PLY_LIMIT",
        "final_fen":board.fen(),
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--nodes", type=int, required=True)
    args=parser.parse_args()
    base=chess.engine.SimpleEngine.popen_uci(str(Path("baseline/src/stockfish").resolve()), timeout=120)
    test=chess.engine.SimpleEngine.popen_uci(str(Path("candidate/src/stockfish").resolve()), timeout=120)
    try:
        base.configure({"Hash":16, "Threads":1})
        test.configure({"Hash":16, "Threads":1})
        games=[]
        for number, opening in openings():
            for candidate_white in (False,True):
                white=test if candidate_white else base
                black=base if candidate_white else test
                rec=run_game(opening.copy(stack=True), white, black, candidate_white, args.nodes, object())
                rec["opening_id"]=number
                rec["candidate_white"]=candidate_white
                games.append(rec)
                print(f"GAME opening={number} candidate_white={candidate_white}: {rec['winner']}, plies={rec['plies']} ({rec['termination']})",flush=True)
        totals={key:sum(x["winner"]==key for x in games) for key in ("candidate","baseline","draw","unfinished")}
        decisive=totals["candidate"]+totals["baseline"]+totals["draw"]
        score=(totals["candidate"]+0.5*totals["draw"])/decisive if decisive else None
        result={"seed":SEED,"nodes_per_move":args.nodes,"opening_pairs":len(games)//2,
                "totals":totals,"completed_games":decisive,"observed_score":score,"games":games}
        Path(f"paired-screen-{args.nodes}.json").write_text(json.dumps(result,indent=2)+"\n")
        print("SUMMARY",json.dumps({k:v for k,v in result.items() if k!="games"}),flush=True)
        # Search changes require statistical Fishtest verification. This tiny match
        # is intended to find egregious regressions, not pass a strength test.
    finally:
        base.quit()
        test.quit()

if __name__=="__main__":
    main()
