import numpy as np
import pandas as pd

from part_a.data import time_chunks
from part_a.stage2a import total_cost


def test_total_cost_formula():
    y = np.array([1, 1, 0, 0]); amt = np.array([100.0, 50.0, 10.0, 10.0]); flag = np.array([True, False, True, False])
    # 2 flagged * c=5 = 10, plus missed fraud Amount 50 = 60
    assert total_cost(y, amt, flag, 5.0) == 60.0


def test_time_chunks_strictly_ordered_and_complete():
    df = pd.DataFrame({"Time": [t for t in range(100) for _ in range(3)], "Class": 0})
    ch = time_chunks(df, 5)
    assert sum(len(c) for c in ch) == len(df)
    for a, b in zip(ch[:-1], ch[1:]):
        assert a.Time.max() < b.Time.max() and a.Time.max() < b.Time.min()
