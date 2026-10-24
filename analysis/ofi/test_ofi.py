"""Hand-checked cases for the CKS event OFI formula used in ofi.py."""
import numpy as np
def e(bp, bs, ap, as_):
    bp, bs, ap, as_ = map(np.asarray, (bp, bs, ap, as_)); o = np.zeros(len(bp))
    o[1:] = (bp[1:] >= bp[:-1]) * bs[1:] - (bp[1:] <= bp[:-1]) * bs[:-1] - (ap[1:] <= ap[:-1]) * as_[1:] + (ap[1:] >= ap[:-1]) * as_[:-1]
    return o
# states: (bid px, bid sz, ask px, ask sz)
S = [(100, 5, 101, 4),   # start
     (100, 7, 101, 4),   # bid size +2 at same price           -> +2
     (100, 7, 101, 1),   # ask size -3 (trade/cancel at ask)  -> +3
     (100.5, 2, 101, 1), # new better bid of 2                 -> +2
     (100, 6, 101, 1),   # best bid removed, old level 6       -> -2
     (100, 6, 100.5, 3), # new better ask of 3                 -> -3
     (100, 6, 101, 9)]   # better ask removed, level of 9      -> +3
x = e(*zip(*S))
assert x.tolist() == [0, 2, 3, 2, -2, -3, 3], x
print("OFI formula: all hand-checked cases pass", x.tolist())
