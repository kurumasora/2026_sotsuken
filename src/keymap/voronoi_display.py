"""ボロノイキーマップ UI．

動作フロー:
  起動 → 待機モード（グレー，STBYセルがオレンジ）
  STBYセルに dwell_stby_ms ホールド → 入力モード切替
  傾けてキー選択 → dwell_ms 保持で確定
  再び STBYセルに dwell_stby_ms ホールド → 待機モードに戻る
"""

import queue
import time
from collections.abc import Callable

import pygame

from src.keymap.voronoi import STBY_KEY, VoronoiMapper
from src.noise_filter import Ema
from src.pointer import PointerController

# ---- 色定数 ------------------------------------------------------------------
_TEXT           = (0,   0,   0  )
_GREEN          = (60,  200, 100)
_ORANGE_IND     = (255, 140, 0  )
_DWELL_BAR      = (0,   100, 220)
_STBY_DWELL_BAR = (220, 120, 0  )
_STBY_DWELL_B2  = (120, 120, 120)

# ---- レイアウト定数 -----------------------------------------------------------
_SCREEN_W        = 1000
_SCREEN_H        = 600
_INDICATOR_POS   = (20, 20)
_INDICATOR_R     = 10
_DWELL_BAR_H     = 7
_LABEL_FONT_SIZE = 18
_INFO_FONT_SIZE  = 18
_STATUS_FONT_SIZE = 22


def run(
    data_queue: "queue.Queue",
    ema_enabled: bool = True,
    beta: float = 0.1,
    positions: dict[str, tuple[float, float]] | None = None,
    on_confirm: Callable[[str], None] | None = None,
    dwell_ms: int = 500,
    dwell_stby_ms: int = 1500,
) -> None:
    pointer   = PointerController(sample_rate=30.0, beta=beta)
    ema       = Ema(alpha=0.2)
    mapper    = VoronoiMapper(positions=positions, W=_SCREEN_W, H=_SCREEN_H)
    px, py    = 0.0, 0.0
    connected = False

    is_active:        bool          = False
    stby_dwell_start: float | None  = None
    dwell_start:      float | None  = None
    prev_key:         str | None    = None

    pygame.init()
    screen      = pygame.display.set_mode((_SCREEN_W, _SCREEN_H))
    pygame.display.set_caption("AccelPointer - Voronoi Keymap")
    font_label  = pygame.font.SysFont(None, _LABEL_FONT_SIZE)
    font_small  = pygame.font.SysFont(None, _INFO_FONT_SIZE)
    font_status = pygame.font.SysFont(None, _STATUS_FONT_SIZE)
    tick        = pygame.time.Clock()

    voronoi_surf = pygame.Surface((_SCREEN_W, _SCREEN_H), 0, 24)

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

        cur_key = mapper.get_key(px, py)
        is_stby = cur_key == STBY_KEY

        # --- STBYセルのドウェル: モード切替 ---
        stby_ratio = 0.0
        if is_stby:
            if stby_dwell_start is None:
                stby_dwell_start = time.monotonic()
            stby_ratio = min(
                1.0, (time.monotonic() - stby_dwell_start) * 1000 / dwell_stby_ms
            )
            if stby_ratio >= 1.0:
                is_active        = not is_active
                stby_dwell_start = None
                dwell_start      = None
                prev_key         = None
        else:
            stby_dwell_start = None

        # --- 通常キーのドウェル: キー確定（入力モード時のみ）---
        dwell_ratio = 0.0
        if is_active and not is_stby:
            if cur_key != prev_key:
                dwell_start = time.monotonic()
                prev_key    = cur_key
            if dwell_start is not None:
                elapsed_ms  = (time.monotonic() - dwell_start) * 1000
                dwell_ratio = min(1.0, elapsed_ms / dwell_ms)
                if dwell_ratio >= 1.0:
                    if on_confirm is not None:
                        on_confirm(cur_key)
                    dwell_start = None
        else:
            if not is_stby:
                dwell_start = None
                prev_key    = None

        # --- 描画 ---
        arr = mapper.render(cur_key, is_active)
        pygame.surfarray.blit_array(voronoi_surf, arr)
        screen.blit(voronoi_surf, (0, 0))

        # キーラベル
        for key, (sx, sy) in zip(mapper.key_list, mapper.seed_positions):
            is_cur = key == cur_key
            if key == STBY_KEY:
                label = "待機" if not is_active else "■"
                color = (60, 60, 60)
            elif is_cur and is_active:
                label = key
                color = (255, 255, 255)
            else:
                label = key
                color = _TEXT
            surf = font_label.render(label, True, color)
            screen.blit(surf, surf.get_rect(center=(sx, sy)))

        # BLE インジケータ
        pygame.draw.circle(
            screen, _GREEN if connected else _ORANGE_IND,
            _INDICATOR_POS, _INDICATOR_R,
        )

        # モード表示
        mode_surf = font_status.render(
            "入力中" if is_active else "待機中", True, _TEXT
        )
        screen.blit(mode_surf, (40, 8))

        # EMA / β 情報
        info = font_small.render(
            f"EMA: {'ON' if ema_enabled else 'OFF'}  β={beta}  dwell={dwell_ms}ms",
            True, _TEXT,
        )
        screen.blit(info, (_SCREEN_W - info.get_width() - 8, 8))

        # 下部ドウェル進捗バー
        if is_active and not is_stby and dwell_ratio > 0:
            bar_w = int(_SCREEN_W * dwell_ratio)
            pygame.draw.rect(screen, _DWELL_BAR,
                             (0, _SCREEN_H - _DWELL_BAR_H, bar_w, _DWELL_BAR_H))
        elif is_stby and stby_ratio > 0:
            bar_w     = int(_SCREEN_W * stby_ratio)
            bar_color = _STBY_DWELL_B2 if is_active else _STBY_DWELL_BAR
            pygame.draw.rect(screen, bar_color,
                             (0, _SCREEN_H - _DWELL_BAR_H, bar_w, _DWELL_BAR_H))

        pygame.display.flip()
        tick.tick(60)

    pygame.quit()
