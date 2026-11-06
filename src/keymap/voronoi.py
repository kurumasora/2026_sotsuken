"""ボロノイキーマッパー — 任意座標にキーを配置し最近傍で選択する．

起動時にピクセル空間でボロノイ最近傍テーブルを事前計算する．
計算後は get_key() / render() で高速に動作する．
"""

import math

import numpy as np

STBY_KEY = "STBY"

_SCREEN_W = 1000
_SCREEN_H = 600


def _circle(
    keys: list[str], r_px: float, start_deg: float = 0.0,
    W: int = _SCREEN_W, H: int = _SCREEN_H,
) -> dict[str, tuple[float, float]]:
    """ピクセル空間で半径 r_px の円周上に均等配置し，正規化座標で返す."""
    cx, cy = W / 2, H / 2
    n = len(keys)
    result: dict[str, tuple[float, float]] = {}
    for i, k in enumerate(keys):
        angle = math.radians(start_deg + 360 * i / n)
        result[k] = (
            round(r_px * math.cos(angle) / cx, 4),
            round(r_px * math.sin(angle) / cy, 4),
        )
    return result


# 英字頻度順に中心近くに配置．画面が 1000×600 なので
# r_px をピクセルで指定すると画面上で真円になる．
VORONOI_KEYS: dict[str, tuple[float, float]] = {
    STBY_KEY: (0.0, 0.0),
    # 内リング (r=90px): 高頻度 8 文字
    **_circle(["e", "t", "a", "o", "i", "n", "s", "h"], r_px=90, start_deg=0),
    # 中リング (r=175px): 次の 12 文字
    **_circle(["r", "d", "l", "c", "u", "m", "f", "w", "g", "y", "p", "b"], r_px=175, start_deg=15),
    # 外リング (r=250px): 残り 6 文字 + 特殊キー
    **_circle(["v", "k", "j", "SPC", "x", "q", "z", "BS", "ENT", "TAB"], r_px=250, start_deg=0),
}

# ---- 描画色 ------------------------------------------------------------------
_COL_WHITE       = (255, 255, 255)
_COL_LIGHT_GRAY  = (230, 230, 230)
_COL_BORDER      = (100, 100, 100)
_COL_HIGHLIGHT   = (50,  150, 255)
_COL_STBY_IDLE   = (255, 190, 60 )   # 待機中: STBYセル オレンジ
_COL_STBY_ACT    = (200, 200, 200)   # 入力中: STBYセル グレー


class VoronoiMapper:
    """ボロノイ配置のキーマッパー．

    __init__ で1回だけ最近傍テーブルを計算し，
    以降 get_key() / render() を高速に呼べる．
    """

    def __init__(
        self,
        positions: dict[str, tuple[float, float]] | None = None,
        W: int = _SCREEN_W,
        H: int = _SCREEN_H,
    ) -> None:
        self._W = W
        self._H = H
        pos = positions if positions is not None else VORONOI_KEYS
        self._key_list: list[str] = list(pos.keys())
        self._N = len(self._key_list)
        self._stby_idx = self._key_list.index(STBY_KEY)

        # 正規化座標 → ピクセル座標のシード点
        cx, cy = W / 2, H / 2
        self._seeds: list[tuple[int, int]] = [
            (int(x * cx + cx), int(y * cy + cy))
            for x, y in pos.values()
        ]

        print("[RasPi] ボロノイ計算中...", flush=True)
        pts = np.array(self._seeds, dtype=np.float32)  # (N, 2)

        xs = np.arange(W, dtype=np.float32)
        ys = np.arange(H, dtype=np.float32)
        XX, YY = np.meshgrid(xs, ys)  # (H, W)

        min_d2 = np.full((H, W), np.inf, dtype=np.float32)
        nearest = np.zeros((H, W), dtype=np.int32)
        for i, (kx, ky) in enumerate(pts):
            d2 = (XX - kx) ** 2 + (YY - ky) ** 2
            mask = d2 < min_d2
            min_d2[mask] = d2[mask]
            nearest[mask] = i

        # 境界マスク (H, W)
        bdr = np.zeros((H, W), dtype=bool)
        bdr[:-1, :] |= nearest[:-1, :] != nearest[1:, :]
        bdr[1:,  :] |= nearest[:-1, :] != nearest[1:, :]
        bdr[:, :-1] |= nearest[:, :-1] != nearest[:, 1:]
        bdr[:, 1:]  |= nearest[:, :-1] != nearest[:, 1:]

        # surfarray は (W, H) 軸順なので転置して保持
        self._nearest_T: np.ndarray = np.ascontiguousarray(nearest.T)  # (W, H)
        self._border_T:  np.ndarray = np.ascontiguousarray(bdr.T)      # (W, H)
        self._masks_T: list[np.ndarray] = [
            np.ascontiguousarray((nearest == i).T) for i in range(self._N)
        ]

        # ベース配列を事前計算（コピー元として使う）
        self._base_active  = self._build_base(active=True)
        self._base_standby = self._build_base(active=False)
        self._last_key: str | None = None
        self._last_active: bool | None = None
        self._last_arr: np.ndarray | None = None

        print("[RasPi] ボロノイ計算完了", flush=True)

    @property
    def key_list(self) -> list[str]:
        return self._key_list

    @property
    def seed_positions(self) -> list[tuple[int, int]]:
        return self._seeds

    def get_key(self, px: float, py: float) -> str:
        """正規化座標 (px, py) → 最近傍キー名."""
        cx, cy = self._W / 2, self._H / 2
        xi = max(0, min(self._W - 1, int(px * cx + cx)))
        yi = max(0, min(self._H - 1, int(py * cy + cy)))
        return self._key_list[self._nearest_T[xi, yi]]

    def render(self, cur_key: str, is_active: bool) -> np.ndarray:
        """(W, H, 3) uint8 配列を返す（pygame.surfarray.blit_array 用）．

        cur_key と is_active が前回と同じならキャッシュを返す．
        """
        if cur_key == self._last_key and is_active == self._last_active:
            return self._last_arr  # type: ignore[return-value]

        base = self._base_active if is_active else self._base_standby
        arr = base.copy()

        if is_active and cur_key != STBY_KEY:
            try:
                idx = self._key_list.index(cur_key)
                arr[self._masks_T[idx]] = _COL_HIGHLIGHT
                arr[self._border_T]     = _COL_BORDER
            except ValueError:
                pass

        self._last_key    = cur_key
        self._last_active = is_active
        self._last_arr    = arr
        return arr

    # ---- 内部ユーティリティ ---------------------------------------------------

    def _build_base(self, active: bool) -> np.ndarray:
        """ベース (W, H, 3) 配列を構築する（境界線・STBYセル色を含む）."""
        arr = np.full((self._W, self._H, 3),
                      _COL_WHITE if active else _COL_LIGHT_GRAY, dtype=np.uint8)
        stby_color = _COL_STBY_ACT if active else _COL_STBY_IDLE
        arr[self._masks_T[self._stby_idx]] = stby_color
        arr[self._border_T] = _COL_BORDER
        return np.ascontiguousarray(arr)
