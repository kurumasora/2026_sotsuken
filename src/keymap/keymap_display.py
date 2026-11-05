"""キーマップ UI — 文字グリッドを表示し，現在位置のキーをハイライトする."""

import queue

import pygame

from src.keymap.keymap import KeyMapper
from src.noise_filter import Ema
from src.pointer import PointerController

_BG          = (255, 255, 255)
_TEXT        = (0, 0, 0)
_HIGHLIGHT   = (50, 150, 255)
_HIGHLIGHT_T = (255, 255, 255)
_GRID_LINE   = (180, 180, 180)
_GREEN       = (60, 200, 100)
_ORANGE      = (255, 140, 0)

_INDICATOR_POS    = (20, 20)
_INDICATOR_RADIUS = 10

# グリッド描画領域
_GRID_LEFT   = 80
_GRID_TOP    = 80
_GRID_RIGHT  = 720
_GRID_BOTTOM = 520


def run(
    data_queue: "queue.Queue",
    ema_enabled: bool = True,
    beta: float = 0.1,
    layout: list[list[str]] | None = None,
) -> None:
    pointer = PointerController(sample_rate=30.0, beta=beta)
    ema     = Ema(alpha=0.2)
    mapper  = KeyMapper(layout=layout)
    px, py  = 0.0, 0.0
    connected   = False
    prev_key: str | None = None

    rows = mapper.rows
    cols = mapper.cols
    cell_w = (_GRID_RIGHT - _GRID_LEFT) / cols
    cell_h = (_GRID_BOTTOM - _GRID_TOP) / rows

    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    pygame.display.set_caption("AccelPointer - Keymap")
    clock      = pygame.font.SysFont(None, 20)
    font_key   = pygame.font.SysFont(None, int(min(cell_w, cell_h) * 0.6))
    font_small = pygame.font.SysFont(None, 18)
    tick       = pygame.time.Clock()

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

        # キーが変わったらターミナルに出力
        if cur_key != prev_key:
            print(f"[RasPi] key: {cur_key}")
            prev_key = cur_key

        screen.fill(_BG)

        # グリッド描画
        for r in range(rows):
            for c in range(cols):
                x = int(_GRID_LEFT + c * cell_w)
                y = int(_GRID_TOP  + r * cell_h)
                w = int(cell_w)
                h = int(cell_h)
                is_active = (r == cur_row and c == cur_col)

                rect = pygame.Rect(x, y, w, h)
                pygame.draw.rect(screen, _HIGHLIGHT if is_active else _BG, rect)
                pygame.draw.rect(screen, _GRID_LINE, rect, 1)

                label = mapper.layout[r][c]
                color = _HIGHLIGHT_T if is_active else _TEXT
                surf  = font_key.render(label, True, color)
                screen.blit(surf, surf.get_rect(center=(x + w // 2, y + h // 2)))

        # BLE インジケータ
        pygame.draw.circle(
            screen,
            _GREEN if connected else _ORANGE,
            _INDICATOR_POS,
            _INDICATOR_RADIUS,
        )

        # EMA / β 表示
        info = font_small.render(
            f"EMA: {'ON' if ema_enabled else 'OFF'}  β={beta}", True, _TEXT)
        screen.blit(info, (800 - info.get_width() - 8, 8))

        # 現在キー表示
        key_surf = font_small.render(f"key: {cur_key}", True, _TEXT)
        screen.blit(key_surf, (10, 560))

        pygame.display.flip()
        tick.tick(60)

    pygame.quit()
