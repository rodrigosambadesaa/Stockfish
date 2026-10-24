#!/usr/bin/env python3
"""Synthesize selective qsearch TT policies in historical/current Stockfish clones.

Validation-only script; nothing in these branches is proposed upstream.
"""
import argparse, pathlib

ORIGINAL = """    // At non-PV nodes we check for an early TT cutoff
    if (!PvNode && ttData.depth >= DEPTH_QS && is_valid(ttData.value)
        && (ttData.bound & (ttData.value >= beta ? BOUND_LOWER : BOUND_UPPER)))
        return ttData.value;
"""

GUARDS = {
    "full": "true",
    "shallow8": "ss->ply <= 8",
    "shallow16": "ss->ply <= 16",
    "deep8": "ss->ply > 8",
    "pvhit": "pvHit",
    "nonpvhit": "!pvHit",
    "lower": "ttData.value >= beta",
    "upper": "ttData.value < beta",
}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("file")
    p.add_argument("policy",choices=GUARDS)
    args=p.parse_args()
    file=pathlib.Path(args.file)
    contents=file.read_text()
    assert contents.count(ORIGINAL)==1, "Expected one unchanged qsearch TT block."
    condition=GUARDS[args.policy]
    replacement="""    // Non-PV quiescence TT cutoff. Only apply the experimental safeguard
    // to selected decisive scores; preserve normal TT hits unchanged.
    if (!PvNode && ttData.depth >= DEPTH_QS && is_valid(ttData.value)
        && (ttData.bound & (ttData.value >= beta ? BOUND_LOWER : BOUND_UPPER)))
    {
        if (!is_decisive(ttData.value) || !("""+condition+"""))
            return ttData.value;

        const Value boundedValue =
          std::clamp(ttData.value, VALUE_TB_LOSS_IN_MAX_PLY + 1, VALUE_TB_WIN_IN_MAX_PLY - 1);

        // Return a weakened bound only if it still yields the same cutoff.
        if ((ttData.value >= beta && boundedValue >= beta)
            || (ttData.value < beta && boundedValue < beta))
            return boundedValue;
    }
"""
    file.write_text(contents.replace(ORIGINAL,replacement))
    print("POLICY",args.policy,"GUARD",condition,flush=True)

if __name__ == "__main__":
    main()
