"""キーマップ UI — STBYセルドウェルでモード切替，通常セルドウェルでキー確定．

動作フロー:
  起動 → 待機モード（グリッドがグレー，STBYセルがオレンジ）
  STBYセルに dwell_stby_ms ホールド → 入力モード切替
  傾けてキー選択 → dwell_ms 保持で確定
  再び STBYセルに dwell_stby_ms ホールド → 待機モードに戻る
"""

import queue
import time
from collections.abc import Callable

import pygame

from src.keymap.keymap import STBY_KEY, KeyMapper
from src.noise_filter import Ema
from src.pointer import PointerController

# ---- 色定数 ---------------------------------------------------------------
_BG              = (255, 255, 255)
_TEXT            = (0,   0,   0  )
_HIGHLIGHT       = (50,  150, 255)
_HIGHLIGHT_T     = (255, 255, 255)
_DWELL_BAR       = (0,   100, 220)
_GRID_LINE       = (180, 180, 180)
_STANDBY_CELL    = (230, 230, 230)   # 待機中の通常セル背景
_STANDBY_TEXT    = (160, 160, 160)   # 待機中の文字
_STBY_BTN_IDLE   = (255, 190, 60 )   # STBYセル（待機中）: 目立つオレンジ
_STBY_BTN_ACT    = (200, 200, 200)   # STBYセル（入力中）: 控えめグレー
_STBY_BTN_TEXT   = (80,  80,  80 )   # STBYセルの文字
_STBY_DWELL_BAR  = (220, 120, 0  )   # STBYドウェルバー（待機→入力）
_STBY_DWELL_BAR2 = (120, 120, 120)   # STBYドウェルバー（入力→待機）
_GREEN           = (60,  200, 100)
_ORANGE          = (255, 140, 0  )

# ---- レイアウト定数 --------------------------------------------------------
_INDICATOR_POS    = (20, 20)
_INDICATOR_RADIUS = 10

_SCREEN_W    = 1000
_SCREEN_H    = 600
_GRID_LEFT   = 20
_GRID_TOP    = 60
_GRID_RIGHT  = 980
_GRID_BOTTOM = 540

_DWELL_BAR_H = 5


def run(
    data_queue: "queue.Queue",
    ema_enabled: bool = True,
    beta: float = 0.1,
    layout: list[list[str]] | None = None,
    on_confirm: Callable[[str], None] | None = None,
    dwell_ms: int = 500,         # 通常キー確定に必要な保持時間 [ms]
    dwell_stby_ms: int = 1500,   # STBYセルでモード切替に必要な保持時間 [ms]
) -> None:
    pointer = PointerController(sample_rate=30.0, beta=beta)
    ema     = Ema(alpha=0.2)
    mapper  = KeyMapper(layout=layout)
    px, py  = 0.0, 0.0
    connected = False

    rows   = mapper.rows
    cell_h = (_GRID_BOTTOM - _GRID_TOP) / rows

    # --- 状態変数 ---
    is_active: bool                = False
    stby_dwell_start: float | None = None   # STBYセル用ドウェルタイマー
    dwell_start: float | None      = None   # 通常キー用ドウェルタイマー
    prev_cell: tuple[int, int] | None = None

    # STBYキーの結合矩形を事前計算（最初にSTBYが現れる行の列幅で統一）
    _stby_col: int | None = None
    _stby_ncols: int | None = None
    for _r, _row in enumerate(mapper.layout):
        for _c, _k in enumerate(_row):
            if _k == STBY_KEY:
                _stby_col   = _c
                _stby_ncols = len(_row)
                break
        if _stby_col is not None:
            break
    if _stby_col is not None and _stby_ncols is not None:
        _scw = (_GRID_RIGHT - _GRID_LEFT) / _stby_ncols
        stby_rect = pygame.Rect(
            int(_GRID_LEFT + _stby_col * _scw),
            _GRID_TOP,
            int(_scw),
            _GRID_BOTTOM - _GRID_TOP,
        )
    else:
        stby_rect = None

    pygame.init()
    screen      = pygame.display.set_mode((_SCREEN_W, _SCREEN_H))
    pygame.display.set_caption("AccelPointer - Keymap")
    font_key    = pygame.font.SysFont(None, int(cell_h * 0.50))
    font_stby   = pygame.font.SysFont(None, int(cell_h * 0.40))
    font_small  = pygame.font.SysFont(None, 18)
    font_status = pygame.font.SysFont(None, 22)
    tick        = pygame.time.Clock()

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        latest = None
        while True:
            try:
                latest = data_queue.get_nowait()
            except queue.Empty:
                break

        if latest is not None:
            connected = True
            ax, ay, az, gx, gy, gz = latest
            raw_px, raw_py = pointer.update(ax, ay, az, gx, gy, gz)
            px, py = ema.filter(raw_px, raw_py) if ema_enabled else (raw_px, raw_py)

        cur_row, cur_col = mapper.get_cell(px, py)
        cur_key = mapper.get_key(px, py)
        is_stby_cell = cur_key == STBY_KEY

        # --- STBYセルのドウェル: モード切替 ---
        stby_ratio = 0.0
        if is_stby_cell:
            if stby_dwell_start is None:
                stby_dwell_start = time.monotonic()
            stby_ratio = min(
                1.0, (time.monotonic() - stby_dwell_start) * 1000 / dwell_stby_ms
            )
            if stby_ratio >= 1.0:
                is_active        = not is_active
                stby_dwell_start = None
                dwell_start      = None   # モード切替時にキードウェルをリセット
                prev_cell        = None
        else:
            stby_dwell_start = None

        # --- 通常キーのドウェル: キー確定（入力モード時のみ）---
        dwell_ratio = 0.0
        if is_active and not is_stby_cell:
            if (cur_row, cur_col) != prev_cell:
                dwell_start = time.monotonic()
                prev_cell   = (cur_row, cur_col)
            if dwell_start is not None:
                elapsed_ms  = (time.monotonic() - dwell_start) * 1000
                dwell_ratio = min(1.0, elapsed_ms / dwell_ms)
                if dwell_ratio >= 1.0:
                    if on_confirm is not None:
                        on_confirm(cur_key)
                    dwell_start = None
        else:
            if not is_stby_cell:
                dwell_start = None
                prev_cell   = None

        # --- 描画 ---
        screen.fill(_BG)

        for r in range(rows):
            n_cols = len(mapper.layout[r])
            cell_w = (_GRID_RIGHT - _GRID_LEFT) / n_cols
            for c in range(n_cols):
                label = mapper.layout[r][c]
                if label == STBY_KEY:
                    continue  # STBYは後でまとめて描画

                x = int(_GRID_LEFT + c * cell_w)
                y = int(_GRID_TOP  + r * cell_h)
                w = int(cell_w)
                h = int(cell_h)
                is_sel   = is_active and (r == cur_row and c == cur_col)

                bg = _HIGHLIGHT if is_sel else (_BG if is_active else _STANDBY_CELL)
                rect = pygame.Rect(x, y, w, h)
                pygame.draw.rect(screen, bg, rect)
                pygame.draw.rect(screen, _GRID_LINE, rect, 1)

                color = _HIGHLIGHT_T if is_sel else (_TEXT if is_active else _STANDBY_TEXT)
                surf  = font_key.render(label, True, color)
                screen.blit(surf, surf.get_rect(center=(x + w // 2, y + h // 2)))

                # 通常キーのドウェル進捗バー
                if is_sel and dwell_ratio > 0:
                    bar_w = int(w * dwell_ratio)
                    pygame.draw.rect(
                        screen, _DWELL_BAR,
                        (x, y + h - _DWELL_BAR_H, bar_w, _DWELL_BAR_H),
                    )

        # STBY キーを縦一本の結合キーとして描画
        if stby_rect is not None:
            stby_bg = _STBY_BTN_ACT if is_active else _STBY_BTN_IDLE
            pygame.draw.rect(screen, stby_bg, stby_rect)
            pygame.draw.rect(screen, _GRID_LINE, stby_rect, 1)
            surf1 = font_stby.render("STBY", True, _STBY_BTN_TEXT)
            screen.blit(surf1, surf1.get_rect(center=stby_rect.center))
            if is_stby_cell and stby_ratio > 0:
                prog_color = _STBY_DWELL_BAR2 if is_active else _STBY_DWELL_BAR
                bar_h = int(stby_rect.height * stby_ratio)
                pygame.draw.rect(
                    screen, prog_color,
                    (stby_rect.x, stby_rect.bottom - bar_h, stby_rect.width, bar_h),
                )

        # BLE インジケータ
        pygame.draw.circle(
            screen,
            _GREEN if connected else _ORANGE,
            _INDICATOR_POS,
            _INDICATOR_RADIUS,
        )

        # モード表示
        mode_surf = font_status.render(
            "Active" if is_active else "Standby", True, _TEXT
        )
        screen.blit(mode_surf, (40, 8))

        # EMA / β 表示
        info = font_small.render(
            f"EMA: {'ON' if ema_enabled else 'OFF'}  β={beta}  dwell={dwell_ms}ms",
            True, _TEXT,
        )
        screen.blit(info, (_SCREEN_W - info.get_width() - 8, 8))

        pygame.display.flip()
        tick.tick(60)

    pygame.quit()
