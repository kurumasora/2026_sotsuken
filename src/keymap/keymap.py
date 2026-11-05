"""キーマッパー — 正規化ポインタ位置 (px, py) を文字に変換する."""

# JIS風レイアウト: 10列×5行（英数字＋基本記号）
# 特殊キーは複数セルに割り当てて確定しやすくする
JIS_LAYOUT: list[list[str]] = [
    ["1",   "2",   "3",   "4",   "5",   "6",   "7",   "8",   "9",   "0"  ],
    ["q",   "w",   "e",   "r",   "t",   "y",   "u",   "i",   "o",   "p"  ],
    ["a",   "s",   "d",   "f",   "g",   "h",   "j",   "k",   "l",   ";"  ],
    ["z",   "x",   "c",   "v",   "b",   "n",   "m",   ",",   ".",   "/"  ],
    ["TAB", "SPC", "SPC", "SPC", "SPC", "BS",  "BS",  "BS",  "ENT", "ENT"],
]


class KeyMapper:
    def __init__(self, layout: list[list[str]] | None = None) -> None:
        self._layout = layout if layout is not None else JIS_LAYOUT
        self._rows = len(self._layout)
        self._cols = len(self._layout[0])

    @property
    def layout(self) -> list[list[str]]:
        return self._layout

    @property
    def rows(self) -> int:
        return self._rows

    @property
    def cols(self) -> int:
        return self._cols

    def get_key(self, px: float, py: float) -> str:
        """px,py ∈ [-1,+1] → レイアウト上の文字を返す."""
        col = int((px + 1.0) / 2.0 * self._cols)
        row = int((py + 1.0) / 2.0 * self._rows)
        col = max(0, min(self._cols - 1, col))
        row = max(0, min(self._rows - 1, row))
        return self._layout[row][col]

    def get_cell(self, px: float, py: float) -> tuple[int, int]:
        """px,py ∈ [-1,+1] → (row, col) のインデックスを返す."""
        col = int((px + 1.0) / 2.0 * self._cols)
        row = int((py + 1.0) / 2.0 * self._rows)
        col = max(0, min(self._cols - 1, col))
        row = max(0, min(self._rows - 1, row))
        return row, col
