"""手首の回転角（roll/pitch）を直接画面座標にマッピングするポインタ表示."""

import queue
import sys

import pygame

from src.noise_filter import Ema
from src.pointer import PointerController

_BG     = (255, 255, 255)
_POINTER = (0, 0, 0)
_TEXT    = (0, 0, 0)
_GREEN   = (60, 200, 100)
_ORANGE  = (255, 140, 0)

_INDICATOR_POS    = (20, 20)
_INDICATOR_RADIUS = 10

# px が [-1, +1] → 画面幅/高さにマッピング
_HALF_W = 400  # px=±1 が画面端
_HALF_H = 300


def run(data_queue: "queue.Queue") -> None:
    pointer = PointerController(sample_rate=30.0)
    ema = Ema(alpha=0.2)
    px, py = 0.0, 0.0  # 最初のデータが届くまでは中央に表示

    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    pygame.display.set_caption("AccelPointer")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 24)

    w, h = screen.get_size()
    cx, cy = w / 2.0, h / 2.0
    connected = False

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()

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
            px, py = ema.filter(raw_px, raw_py)

        draw_x = max(0, min(w, int(cx + px * _HALF_W)))
        draw_y = max(0, min(h, int(cy + py * _HALF_H)))

        screen.fill(_BG)
        pygame.draw.circle(screen, _POINTER, (draw_x, draw_y), 20)
        pygame.draw.circle(
            screen,
            _GREEN if connected else _ORANGE,
            _INDICATOR_POS,
            _INDICATOR_RADIUS,
        )

        if connected:
            roll, pitch = pointer.angles
            screen.blit(font.render(
                f"roll:{roll:+.1f}°  pitch:{pitch:+.1f}°", True, _TEXT), (10, h - 26))

        pygame.display.flip()
        clock.tick(60)
