#!/usr/bin/env python3
"""Check the native multiplier's integer/bit-shift algorithm against exact BF16.

This mirrors the algorithm in verilog/bf16_mul_native.v without using its RTL.
It catches arithmetic design mistakes but does NOT replace HDL simulation.
"""

import argparse
import random
from bf16_reference import bf16_op, category


def native_mul_model(a, b, rmode):
    fa, fb = a & 0x7F, b & 0x7F
    expa, expb = (a >> 7) & 0xFF, (b >> 7) & 0xFF
    sign = ((a ^ b) >> 15) & 1
    ca, cb = category(a), category(b)
    if ca == "nan" or cb == "nan" or (ca == "inf" and cb == "zero") or (cb == "inf" and ca == "zero"):
        return 0x7FC0
    if ca == "inf" or cb == "inf":
        return (sign << 15) | 0x7F80
    if ca == "zero" or cb == "zero":
        return sign << 15

    sig_a = (0 if expa == 0 else 128) | fa
    sig_b = (0 if expb == 0 else 128) | fb
    product = sig_a * sig_b
    ea = -126 if expa == 0 else expa - 127
    eb = -126 if expb == 0 else expb - 127
    highest = product.bit_length() - 1
    e = ea + eb - 14 + highest
    tiny = e < -126

    if tiny:
        shift = -(ea + eb + 119)
        expfield = 0
    else:
        shift = highest - 7
        expfield = e + 127
    if shift < 0:
        base, guard, sticky = product << -shift, False, False
    elif shift == 0:
        base, guard, sticky = product, False, False
    elif shift > 16:
        base, guard, sticky = 0, False, bool(product)
    else:
        base = product >> shift
        guard = bool((product >> (shift - 1)) & 1)
        sticky = bool(product & ((1 << (shift - 1)) - 1))

    inexact = guard or sticky
    increment = ((guard and (sticky or (base & 1))) if rmode == 0 else
                False if rmode == 1 else
                (not sign and inexact) if rmode == 2 else
                (bool(sign) and inexact))
    rounded = base + int(increment)
    beyond_max = e > 127 or (e == 127 and base == 255 and inexact)
    to_inf = rmode == 0 or (rmode == 2 and not sign) or (rmode == 3 and sign)

    if beyond_max:
        return (sign << 15) | (0x7F80 if to_inf else 0x7F7F)
    if tiny:
        if rounded >= 128:
            return (sign << 15) | 0x0080
        return (sign << 15) | rounded
    if rounded >= 256:
        rounded >>= 1
        expfield += 1
    if expfield >= 255:
        return (sign << 15) | (0x7F80 if to_inf else 0x7F7F)
    return (sign << 15) | (expfield << 7) | (rounded & 0x7F)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--random-per-mode", type=int, default=30000)
    args = parser.parse_args()

    rng = random.Random(220)
    boundary = [0x0000, 0x8000, 0x0001, 0x8001, 0x007F, 0x0080,
                0x3F80, 0x3F81, 0xBF80, 0x7F7E, 0x7F7F, 0xFF7F,
                0x7F80, 0xFF80, 0x7FC0, 0x7F81]
    tested, failures = 0, 0
    for mode in range(4):
        cases = [(a, b) for a in boundary for b in boundary]
        cases += [(rng.randrange(0x10000), rng.randrange(0x10000))
                for _ in range(args.random_per_mode)]
        for a, b in cases:
            tested += 1
            got = native_mul_model(a, b, mode)
            expected = bf16_op(a, b, 2, mode)
            if got != expected:
                failures += 1
                if failures <= 12:
                    print(f"MISMATCH rm={mode} a={a:04x} b={b:04x} expected={expected:04x} got={got:04x}")
    print(f"Native BF16 multiplier algorithm: {tested} cases, {failures} mismatches")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
