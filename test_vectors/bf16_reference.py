#!/usr/bin/env python3
"""Bit-exact BF16 arithmetic reference and quantization accuracy experiment.

BF16 has sign:1, exponent:8 (bias 127), stored fraction:7.
The oracle evaluates finite operations with exact rational arithmetic, then
rounds once to BF16 in the requested IEEE-754 rounding direction.

Supported arithmetic opcodes match OpenCores: 0 add, 1 sub, 2 mul, 3 div.
Rounding modes match OpenCores: 0 nearest/even, 1 toward zero, 2 toward +inf,
3 toward -inf. NaNs are canonicalized to quiet NaN 0x7fc0.

This is a research reference, not a replacement for SoftFloat for complete
IEEE-754 flag validation or every signaling-NaN payload convention.
"""

import argparse
import bisect
from fractions import Fraction
import math
import random
import struct

MAX_FINITE = 0x7F7F
POS_INF = 0x7F80
QNAN = 0x7FC0
OPS = {0: "add", 1: "sub", 2: "mul", 3: "div"}


def scaled_power_two(exp):
    return Fraction(1 << exp, 1) if exp >= 0 else Fraction(1, 1 << -exp)


def bf16_fraction(bits):
    """Convert a finite BF16 bit-pattern to an exact signed Fraction."""
    exp = (bits >> 7) & 0xFF
    frac = bits & 0x7F
    if exp == 0xFF:
        raise ValueError("NaN/infinity is not a finite fraction")
    if exp == 0:
        value = Fraction(frac, 128) * scaled_power_two(-126)
    else:
        value = Fraction(128 + frac, 128) * scaled_power_two(exp - 127)
    return -value if bits & 0x8000 else value


# IEEE BF16 nonnegative finite encodings are numerically increasing.
POSITIVE_VALUES = tuple(bf16_fraction(bits) for bits in range(MAX_FINITE + 1))
OVERFLOW_THRESHOLD = POSITIVE_VALUES[-1] + (
    POSITIVE_VALUES[-1] - POSITIVE_VALUES[-2]
) / 2


def round_fraction(value, mode, negative_zero=False):
    """Round an exact finite result directly to BF16; return 16-bit encoding."""
    assert mode in (0, 1, 2, 3)
    sign = int(value < 0 or (value == 0 and negative_zero))
    mag = -value if value < 0 else value
    if mag == 0:
        return sign << 15

    floor = bisect.bisect_right(POSITIVE_VALUES, mag) - 1
    floor = max(floor, 0)
    if mag == POSITIVE_VALUES[floor]:
        chosen = floor
    elif mag > POSITIVE_VALUES[-1]:
        if mode == 0:
            chosen = POS_INF if mag >= OVERFLOW_THRESHOLD else MAX_FINITE
        elif (mode == 2 and not sign) or (mode == 3 and sign):
            chosen = POS_INF
        else:
            chosen = MAX_FINITE
    elif mode == 0:
        low_error = mag - POSITIVE_VALUES[floor]
        high_error = POSITIVE_VALUES[floor + 1] - mag
        if high_error < low_error:
            chosen = floor + 1
        elif high_error > low_error:
            chosen = floor
        else:  # exact tie: last retained significand bit must be even
            chosen = floor + (floor & 1)
    elif (mode == 2 and not sign) or (mode == 3 and sign):
        chosen = floor + 1
    else:
        chosen = floor
    return (sign << 15) | chosen


def category(bits):
    exp = (bits >> 7) & 0xFF
    frac = bits & 0x7F
    if exp == 0xFF:
        return "nan" if frac else "inf"
    return "zero" if exp == 0 and frac == 0 else "finite"


def bf16_op(a, b, op, mode):
    """One exactly rounded BF16 arithmetic operation, including key specials."""
    if op not in OPS or mode not in (0, 1, 2, 3):
        raise ValueError("Only arithmetic opcodes 0..3 and rounding 0..3")
    ca, cb = category(a), category(b)
    sign_a, sign_b = (a >> 15) & 1, (b >> 15) & 1
    if ca == "nan" or cb == "nan":
        return QNAN

    if op in (0, 1):
        sign_b ^= int(op == 1)
        if ca == "inf" or cb == "inf":
            if ca == "inf" and cb == "inf" and sign_a != sign_b:
                return QNAN
            return ((sign_a if ca == "inf" else sign_b) << 15) | POS_INF
        if ca == "zero" and cb == "zero":
            # IEEE-754 cancellation: -0 only under round-toward-negative,
            # except when both effective operands are already -0.
            sign = sign_a if sign_a == sign_b else int(mode == 3)
            return sign << 15
        fb = -bf16_fraction(b) if op == 1 else bf16_fraction(b)
        exact = bf16_fraction(a) + fb
        return round_fraction(exact, mode, negative_zero=(mode == 3))

    sign = sign_a ^ sign_b
    if op == 2:
        if (ca == "zero" and cb == "inf") or (ca == "inf" and cb == "zero"):
            return QNAN
        if ca == "inf" or cb == "inf":
            return (sign << 15) | POS_INF
        if ca == "zero" or cb == "zero":
            return sign << 15
        return round_fraction(bf16_fraction(a) * bf16_fraction(b), mode)

    # Division
    if (ca == "zero" and cb == "zero") or (ca == "inf" and cb == "inf"):
        return QNAN
    if cb == "zero" or ca == "inf":
        return (sign << 15) | POS_INF
    if ca == "zero" or cb == "inf":
        return sign << 15
    return round_fraction(bf16_fraction(a) / bf16_fraction(b), mode)


def f32_bits(value):
    return struct.unpack(">I", struct.pack(">f", float(value)))[0]


def bits_to_f32(bits):
    return struct.unpack(">f", struct.pack(">I", bits))[0]


def f32_to_bf16(value, mode=0):
    """Round an FP32 *bit pattern* to BF16, matching the RTL adapter."""
    raw = f32_bits(value)
    hi, discarded = raw >> 16, raw & 0xFFFF
    if (raw & 0x7F800000) == 0x7F800000:
        return ((hi & 0x8000) | QNAN) if (raw & 0x7FFFFF) else hi
    inc = (discarded > 0x8000 or (discarded == 0x8000 and (hi & 1))) if mode == 0 else (
        False if mode == 1 else
        (not (hi & 0x8000) and bool(discarded)) if mode == 2 else
        (bool(hi & 0x8000) and bool(discarded))
    )
    return (hi + int(inc)) & 0xFFFF


def bf16_to_f32(bits):
    return bits_to_f32(bits << 16)


def proto_op(a, b, op, mode):
    """Software emulation of the FP32-core-then-BF16-rounding prototype."""
    import numpy as np

    x, y = np.float32(bf16_to_f32(a)), np.float32(bf16_to_f32(b))
    with np.errstate(over="ignore", under="ignore", divide="ignore", invalid="ignore"):
        z = (x + y, x - y, x * y, x / y)[op]
    return f32_to_bf16(z, mode)


def randomized_vectors(count_per_op_mode, seed):
    rng = random.Random(seed)
    specials = [0x0000, 0x8000, 0x0001, 0x007F, 0x0080, 0x3F80,
                0xBF80, 0x4000, 0x7F7F, 0xFF7F, 0x7F80, 0xFF80,
                0x7FC0, 0x7F81, 0x3B80, 0x3BC0]
    for op in OPS:
        for mode in range(4):
            for a in specials:
                for b in specials:
                    yield a, b, op, mode, bf16_op(a, b, op, mode)
            for _ in range(count_per_op_mode):
                a, b = rng.randrange(0x10000), rng.randrange(0x10000)
                yield a, b, op, mode, bf16_op(a, b, op, mode)


def evaluate_accuracy(count, seed):
    """Compare rounded BF16 operation to FP32 on unquantized inputs."""
    import numpy as np

    rng = np.random.default_rng(seed)
    print("Accuracy vs FP32 on original inputs (BF16 quantizes inputs and output)")
    print("op     n     MAE            RMSE           mean_rel       p95_rel        max_rel       double_round")
    for op, name in OPS.items():
        vals_a = 10 ** rng.uniform(-5, 5, size=count) * rng.uniform(0.5, 2, size=count)
        vals_b = 10 ** rng.uniform(-5, 5, size=count) * rng.uniform(0.5, 2, size=count)
        vals_a *= rng.choice([-1, 1], size=count)
        vals_b *= rng.choice([-1, 1], size=count)
        ref_values = []
        test_values = []
        double_rounds = 0
        for x64, y64 in zip(vals_a, vals_b):
            x, y = np.float32(x64), np.float32(y64)
            with np.errstate(over="ignore", under="ignore", divide="ignore", invalid="ignore"):
                full = (x + y, x - y, x * y, x / y)[op]
            a, b = f32_to_bf16(x), f32_to_bf16(y)
            expected = bf16_op(a, b, op, 0)
            emulated = proto_op(a, b, op, 0)
            if expected != emulated:
                double_rounds += 1
            actual = bf16_to_f32(expected)
            if math.isfinite(float(full)) and math.isfinite(actual):
                ref_values.append(float(full))
                test_values.append(actual)
        refs, tests = np.array(ref_values), np.array(test_values)
        errors = np.abs(tests - refs)
        # Relative error is only well-behaved when the true result is nonzero.
        relative = errors[np.abs(refs) > 1e-30] / np.abs(refs[np.abs(refs) > 1e-30])
        print(f"{name:4s} {len(refs):5d} {np.mean(errors):13.6g} {np.sqrt(np.mean(errors ** 2)):13.6g} "
            f"{np.mean(relative):13.6g} {np.percentile(relative, 95):13.6g} "
            f"{np.max(relative):13.6g} {double_rounds:7d}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--accuracy", action="store_true", help="print numerical accuracy table")
    parser.add_argument("--samples", type=int, default=2000, help="samples per operation")
    parser.add_argument("--vectors-out", help="write exact BF16 reference vectors")
    parser.add_argument("--random-vectors", type=int, default=100, help="per op and mode")
    parser.add_argument("--seed", type=int, default=220)
    args = parser.parse_args()

    if args.vectors_out:
        with open(args.vectors_out, "w", encoding="ascii") as out:
            for a, b, op, mode, result in randomized_vectors(args.random_vectors, args.seed):
                out.write(f"{a:04x} {b:04x} {op} {mode} {result:04x}\n")
        print(f"Wrote BF16 exact-reference vectors: {args.vectors_out}")
    if args.accuracy:
        evaluate_accuracy(args.samples, args.seed)
    if not args.accuracy and not args.vectors_out:
        parser.print_help()


if __name__ == "__main__":
    main()
