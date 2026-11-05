class Ema:
    def __init__(self, alpha: float = 0.2):
        self._alpha = alpha
        self._px = 0.0
        self._py = 0.0

    def filter(self, raw_px: float, raw_py: float) -> tuple[float, float]:
        self._px = self._px * (1 - self._alpha) + raw_px * self._alpha
        self._py = self._py * (1 - self._alpha) + raw_py * self._alpha
        return self._px, self._py
