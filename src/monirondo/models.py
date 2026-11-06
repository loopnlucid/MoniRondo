from dataclasses import dataclass, field
from enum import StrEnum


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def center(self) -> tuple[float, float]:
        return (self.left + self.right) / 2, (self.top + self.bottom) / 2

    def translate(self, x: int, y: int) -> "Rect":
        return Rect(self.left + x, self.top + y, self.right + x, self.bottom + y)

    def intersection_area(self, other: "Rect") -> int:
        return max(0, min(self.right, other.right) - max(self.left, other.left)) * max(
            0, min(self.bottom, other.bottom) - max(self.top, other.top)
        )

    def near(self, other: "Rect", tolerance: int = 3) -> bool:
        return all(abs(a - b) <= tolerance for a, b in zip(self.tuple(), other.tuple(), strict=True))

    def tuple(self) -> tuple[int, int, int, int]:
        return self.left, self.top, self.right, self.bottom


@dataclass(frozen=True)
class MonitorInfo:
    id: str
    device: str
    name: str
    bounds: Rect
    work: Rect
    primary: bool = False
    dpi: int | None = None
    stable: bool = True


class WindowState(StrEnum):
    NORMAL = "normal"
    MAXIMIZED = "maximized"
    MINIMIZED = "minimized"


@dataclass(frozen=True)
class Placement:
    normal: Rect
    show_cmd: int = 1
    flags: int = 0
    min_position: tuple[int, int] = (-1, -1)
    max_position: tuple[int, int] = (-1, -1)


@dataclass(frozen=True)
class WindowSnapshot:
    hwnd: int
    pid: int
    thread_id: int
    process_start: int
    class_name: str
    monitor_id: str
    rect: Rect
    normal_screen: Rect
    placement: Placement
    state: WindowState = WindowState.NORMAL
    topmost: bool = False
    tool_window: bool = False
    owner: int = 0
    root_owner: int = 0
    z_index: int = 0
    visible_rect: Rect | None = None

    @property
    def movement_rect(self) -> Rect:
        # Snapped normal windows can retain an unrelated pre-snap restore RECT.
        # Only iconic/zoomed windows need the latent restoration geometry.
        return self.rect if self.state == WindowState.NORMAL else self.normal_screen

    @property
    def identity(self) -> tuple[int, int, int, int, str]:
        return self.hwnd, self.pid, self.thread_id, self.process_start, self.class_name


@dataclass(frozen=True)
class Hotkey:
    modifiers: tuple[str, ...]
    key: str

    @property
    def canonical(self) -> tuple[tuple[str, ...], str]:
        return tuple(sorted(set(self.modifiers))), self.key.upper()


@dataclass
class SwapAction:
    id: str
    name: str
    type: str
    enabled: bool = True
    hotkey: Hotkey | None = None
    direction: str = "forward"
    monitor_order: str = "dynamic_spatial"
    monitor_ids: list[str] = field(default_factory=list)
    monitor_a_id: str = ""
    monitor_b_id: str = ""


@dataclass(frozen=True)
class Move:
    before: WindowSnapshot
    target: MonitorInfo
    # Target outer screen RECT; visible normal bounds, or a latent restore RECT
    # for iconic/zoomed windows. Never pass raw DWM/workspace bounds to SetWindowPos.
    normal_screen: Rect
    target_visible: Rect | None = None


@dataclass(frozen=True)
class MovePlan:
    moves: tuple[Move, ...]
    layout: tuple[MonitorInfo, ...]
    foreground: int


@dataclass(frozen=True)
class UndoEntry:
    before: WindowSnapshot
    after: WindowSnapshot


@dataclass
class SwapResult:
    moved: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    entries: list[UndoEntry] = field(default_factory=list)
