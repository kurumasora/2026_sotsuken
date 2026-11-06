"""キーマッパー — 正規化ポインタ位置 (px, py) を文字に変換する．

各行の列数が異なる不均一レイアウトに対応している．
行ごとにセル幅が変わるため，列数の多い行は細かく，少ない行は広くなる．
"""

# JIS風レイアウト — 行ごとに列数が異なってもよい
# 中央列（各行の真ん中）を STBY 専用の縦一列として割り当てる
JIS_LAYOUT: list[list[str]] = [
    ["1",   "2",   "3",   "4",   "5",   "STBY", "6",   "7",   "8",   "9",   "0"  ],
    ["q",   "w",   "e",   "r",   "t",   "STBY", "y",   "u",   "i",   "o",   "p"  ],
    ["a",   "s",   "d",   "f",   "g",   "STBY", "h",   "j",   "k",   "l",   ";"  ],
    ["z",   "x",   "c",   "v",   "b",   "STBY", "n",   "m",   ",",   ".",   "/"  ],
    ["TAB", "SPC", "SPC", "SPC", "SPC", "STBY", "SPC", "BS",  "BS",  "ENT", "ENT"],
]

STBY_KEY = "STBY"


class KeyMapper:
    def __init__(self, layout: list[list[str]] | None = None) -> None:
        self._layout = layout if layout is not None else JIS_LAYOUT
        self._rows = len(self._layout)

        # STBYカラムの正規化x範囲を事前計算（縦方向を無制限にするため）
        self._stby_px_range: tuple[float, float] | None = None
        for row in self._layout:
            for c, k in enumerate(row):
                if k == STBY_KEY:
                    n = len(row)
                    self._stby_px_range = (c / n * 2 - 1, (c + 1) / n * 2 - 1)
                    break
            if self._stby_px_range is not None:
                break

    @property
    def layout(self) -> list[list[str]]:
        return self._layout

    @property
    def rows(self) -> int:
        return self._rows

    def get_key(self, px: float, py: float) -> str:
        """px,py ∈ [-1,+1] → レイアウト上の文字を返す．
        STBYはpxの範囲だけで判定し，pyは無関係（縦方向に自由）．
        """
        if self._stby_px_range is not None:
            x0, x1 = self._stby_px_range
            if x0 <= px < x1:
                return STBY_KEY
        row, col = self.get_cell(px, py)
        return self._layout[row][col]

    def get_cell(self, px: float, py: float) -> tuple[int, int]:
        """px,py ∈ [-1,+1] → (row, col) のインデックスを返す．"""
        row = int((py + 1.0) / 2.0 * self._rows)
        row = max(0, min(self._rows - 1, row))
        n_cols = len(self._layout[row])
        col = int((px + 1.0) / 2.0 * n_cols)
        col = max(0, min(n_cols - 1, col))
        return row, col
