#!/usr/bin/env python3
"""Exact IEEE-754 single-precision reference model for the FP32 baseline FPU.

Every result is computed with exact rational arithmetic (fractions.Fraction)
and rounded once to binary32 in the requested rounding mode, so the model does
not inherit any host floating-point rounding.

Rounding modes follow the FPU's rmode encoding:
    0 = nearest-even, 1 = toward zero, 2 = toward +inf, 3 = toward -inf
Operations follow fpu_op: 0 add, 1 sub, 2 mul, 3 div, 4 i2f, 5 f2i.

Usage:
    python3 fp32_golden_model.py --out fp32_baseline_vectors.hex          # 12 corner + 16 random (every op x rounding mode)
    python3 fp32_golden_model.py --out fp32_regression.hex --random 2000 --full-range 2000 --no-corner --seed 7
    python3 fp32_golden_model.py --eval 2 0 3fc00000 40000000              # one operation
"""
import argparse
import random
import struct
from fractions import Fraction

EXP_BIAS = 127
FRAC_BITS = 23
MIN_EXP = 1 - EXP_BIAS          # -126
MAX_FINITE = (2 - Fraction(1, 2**FRAC_BITS)) * Fraction(2) ** 127
POS_INF, NEG_INF = 0x7F800000, 0xFF800000
QNAN = 0x7FC00000               # class only: any NaN output is accepted
OPS = {0: "add", 1: "sub", 2: "mul", 3: "div", 4: "i2f", 5: "f2i"}
RMODES = {0: "RNE", 1: "RTZ", 2: "RUP", 3: "RDN"}


def is_nan(b): return (b & 0x7F800000) == 0x7F800000 and (b & 0x7FFFFF) != 0
def is_inf(b): return (b & 0x7FFFFFFF) == 0x7F800000
def is_zero(b): return (b & 0x7FFFFFFF) == 0
def sign(b): return b >> 31


def to_frac(b):
    e = (b >> 23) & 0xFF
    m = b & 0x7FFFFF
    v = Fraction(m, 2**23) * Fraction(2) ** MIN_EXP if e == 0 else \
        (1 + Fraction(m, 2**23)) * Fraction(2) ** (e - EXP_BIAS)
    return -v if sign(b) else v


def _round_int(x, rmode, negative):
    """Round non-negative Fraction x to an integer under rmode (sign given separately)."""
    q, r = divmod(x.numerator, x.denominator)
    if r == 0:
        return q, False
    rem = Fraction(r, x.denominator)
    if rmode == 0:
        up = rem > Fraction(1, 2) or (rem == Fraction(1, 2) and q % 2 == 1)
    elif rmode == 1:
        up = False
    elif rmode == 2:
        up = not negative
    else:
        up = negative
    return q + (1 if up else 0), True


def round_to_fp32(v, rmode, neg_zero=False):
    """Round exact Fraction v to binary32. Returns (bits, inexact, overflow, underflow)."""
    if v == 0:
        return (0x80000000 if neg_zero else 0), False, False, False
    negative = v < 0
    a = -v if negative else v
    # exponent so that 1 <= a / 2^e < 2
    e = a.numerator.bit_length() - a.denominator.bit_length()
    if Fraction(2) ** e > a:
        e -= 1
    e = max(e, MIN_EXP)  # subnormal range uses fixed scale
    scaled = a / Fraction(2) ** e * 2**FRAC_BITS
    m, inexact = _round_int(scaled, rmode, negative)
    if m == 2 ** (FRAC_BITS + 1):    # rounding carried into next binade
        m //= 2
        e += 1
    s = 0x80000000 if negative else 0
    if e > 127:
        towards_inf = rmode == 0 or (rmode == 2 and not negative) or (rmode == 3 and negative)
        bits = s | (0x7F800000 if towards_inf else 0x7F7FFFFF)
        return bits, True, True, False
    if m < 2**FRAC_BITS:              # subnormal (or rounded to zero)
        bits = s | m
        tiny = True
    else:
        bits = s | ((e + EXP_BIAS) << 23) | (m - 2**FRAC_BITS)
        tiny = False
    return bits, inexact, False, tiny and inexact


def fp32_op(op, rmode, a, b):
    """Return dict(out, inf, qnan, zero, div_by_zero, overflow, underflow, ine)."""
    r = dict(out=0, inf=0, qnan=0, zero=0, div_by_zero=0, overflow=0, underflow=0, ine=0)

    def nan():
        r.update(out=QNAN, qnan=1)
        return r

    def setv(bits, inexact=False, ovf=False, unf=False):
        r.update(out=bits, ine=int(inexact), overflow=int(ovf), underflow=int(unf))
        r["inf"] = int(is_inf(bits))
        r["zero"] = int(is_zero(bits))
        return r

    if op == 4:  # i2f: opa is a signed 32-bit integer
        iv = a - 2**32 if a & 0x80000000 else a
        return setv(*round_to_fp32(Fraction(iv), rmode))
    if op == 5:  # f2i: round to signed 32-bit integer
        if is_nan(a) or is_inf(a):
            return nan()
        v = to_frac(a)
        n, inexact = _round_int(abs(v), rmode, v < 0)
        n = -n if v < 0 else n
        n = max(min(n, 2**31 - 1), -2**31)
        r.update(out=n & 0xFFFFFFFF, ine=int(inexact), zero=int(n == 0))
        return r

    if is_nan(a) or is_nan(b):
        return nan()
    sa, sb = sign(a), sign(b)
    if op in (0, 1):
        sb_eff = sb ^ (op == 1)
        if is_inf(a) or is_inf(b):
            if is_inf(a) and is_inf(b) and sa != sb_eff:
                return nan()
            s = sa if is_inf(a) else sb_eff
            return setv(NEG_INF if s else POS_INF)
        va, vb = to_frac(a), (-to_frac(b) if op == 1 else to_frac(b))
        res = va + vb
        if res == 0:
            if is_zero(a) and is_zero(b) and sa == sb_eff:
                negz = bool(sa)
            else:
                negz = rmode == 3
            return setv(0x80000000 if negz else 0)
        return setv(*round_to_fp32(res, rmode))
    s = sa ^ sb
    if op == 2:
        if (is_inf(a) and is_zero(b)) or (is_zero(a) and is_inf(b)):
            return nan()
        if is_inf(a) or is_inf(b):
            return setv(NEG_INF if s else POS_INF)
        res = to_frac(a) * to_frac(b)
        if res == 0:
            return setv(0x80000000 if s else 0)
        return setv(*round_to_fp32(res, rmode))
    if op == 3:
        if (is_inf(a) and is_inf(b)) or (is_zero(a) and is_zero(b)):
            return nan()
        if is_inf(a):
            return setv(NEG_INF if s else POS_INF)
        if is_inf(b):
            return setv(0x80000000 if s else 0)
        if is_zero(b):
            setv(NEG_INF if s else POS_INF)
            r["div_by_zero"] = 1
            return r
        res = to_frac(a) / to_frac(b)
        if res == 0:
            return setv(0x80000000 if s else 0)
        return setv(*round_to_fp32(res, rmode))
    raise ValueError(op)


def f2b(x): return struct.unpack(">I", struct.pack(">f", x))[0]


# ~10 directed corner cases: (name, op, rmode, opa, opb)
CORNER = [
    ("D01 +0 + -0 = +0 (RNE)",                0, 0, 0x00000000, 0x80000000),
    ("D02 +inf - +inf = qNaN (invalid)",      1, 0, POS_INF, POS_INF),
    ("D03 1.0 / +0 = +inf, div_by_zero",      3, 0, f2b(1.0), 0x00000000),
    ("D04 0 / 0 = qNaN (invalid)",            3, 0, 0x00000000, 0x00000000),
    ("D05 MAX * 2 = +inf (RNE overflow)",     2, 0, 0x7F7FFFFF, f2b(2.0)),
    ("D06 MAX * 2 = MAX (RTZ overflow)",      2, 1, 0x7F7FFFFF, f2b(2.0)),
    ("D07 1 + 2^-24 tie -> 1.0 (RNE)",        0, 0, f2b(1.0), 0x33800000),
    ("D08 1 + 2^-24 -> 1+ulp (round up)",     0, 2, f2b(1.0), 0x33800000),
    ("D09 -1 - 2^-24 -> -(1+ulp) (round dn)", 1, 3, f2b(-1.0), 0x33800000),
    ("D10 qNaN propagation through mul",      2, 0, 0x7FC00000, f2b(3.0)),
    ("D11 inf * 0 = qNaN (invalid)",          2, 0, POS_INF, 0x00000000),
    ("D12 x - x = +0, -0 in round-down",      1, 3, f2b(1.5), f2b(1.5)),
]


def random_normal(rng, lo=-30, hi=30):
    e = rng.randint(lo, hi) + EXP_BIAS
    return (rng.getrandbits(1) << 31) | (e << 23) | rng.getrandbits(23)


def random_full_range(n, seed):
    """Full exponent range: 25% subnormal operands, the rest normal with any
    exponent, so results overflow, underflow and go subnormal."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        op, rm = i % 4, (i // 4) % 4
        def operand():
            if rng.random() < 0.25:
                return (rng.getrandbits(1) << 31) | rng.getrandbits(23)
            return random_normal(rng, -126, 127)
        out.append((f"F{i+1:04d} full-range {OPS[op]} {RMODES[rm]}", op, rm, operand(), operand()))
    return out


def random_cases(n, seed):
    """Random-constrained: normal operands, exponents in [-30, 30] so results stay
    in range, every op and rounding mode in rotation."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        op, rm = i % 4, (i // 4) % 4
        a, b = random_normal(rng), random_normal(rng)
        out.append((f"R{i+1:02d} random {OPS[op]} {RMODES[rm]}", op, rm, a, b))
    return out


def emit(cases, path):
    lines = []
    for name, op, rm, a, b in cases:
        r = fp32_op(op, rm, a, b)
        flags = (r["inf"] << 3) | (r["qnan"] << 2) | (r["zero"] << 1) | r["div_by_zero"]
        lines.append(f"{op:01x}{rm:01x} {a:08x} {b:08x} {r['out']:08x} {flags:01x}  // {name}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return lines


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="fp32_baseline_vectors.hex")
    ap.add_argument("--random", type=int, default=16, help="number of random-constrained cases")
    ap.add_argument("--no-corner", action="store_true")
    ap.add_argument("--full-range", type=int, default=0,
                    help="add N full-exponent-range cases (subnormals, overflow, underflow)")
    ap.add_argument("--seed", type=int, default=220)
    ap.add_argument("--eval", nargs=4, metavar=("OP", "RMODE", "OPA", "OPB"))
    a = ap.parse_args()
    if a.eval:
        op, rm, x, y = int(a.eval[0]), int(a.eval[1]), int(a.eval[2], 16), int(a.eval[3], 16)
        print({k: (hex(v) if k == "out" else v) for k, v in fp32_op(op, rm, x, y).items()})
    else:
        cases = ([] if a.no_corner else CORNER) + random_cases(a.random, a.seed) + \
            random_full_range(a.full_range, a.seed + 1)
        lines = emit(cases, a.out)
        print(f"wrote {len(lines)} vectors to {a.out}")
