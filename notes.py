import json
import re
import shutil
import sys
import time
from pathlib import Path

import markdown
from PySide6.QtCore import QPoint, QRectF, QTimer, Qt, QUrl
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizeGrip,
    QSizePolicy,
    QStackedWidget,
    QSystemTrayIcon,
    QTextBrowser,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "便签"
SCRIPT_DIR = Path(__file__).resolve().parent

VIDEO_EXTS = {".mp4", ".avi", ".mkv", ".mov", ".webm", ".wmv", ".flv", ".m4v"}

ACCENT = "#4c8dff"
ACCENT_DIM = "#3a6fd8"
TEXT_MAIN = "#f2f6fd"
TEXT_SUB = "rgba(210, 224, 244, 165)"

# 统一暗色主题：菜单、提示、对话框、滚动条、按钮等原生控件跟随面板配色。
APP_STYLESHEET = f"""
QToolTip {{
    background-color: #1b2330;
    color: {TEXT_MAIN};
    border: 1px solid {ACCENT};
    border-radius: 6px;
    padding: 5px 9px;
    font-size: 12px;
}}
QMenu {{
    background-color: #1b2330;
    color: {TEXT_MAIN};
    border: 1px solid rgba(255, 255, 255, 32);
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 24px 7px 14px;
    border-radius: 6px;
    font-size: 12px;
}}
QMenu::item:selected {{
    background-color: {ACCENT_DIM};
    color: #ffffff;
}}
QMenu::item:disabled {{
    color: rgba(210, 224, 244, 90);
}}
QMenu::separator {{
    height: 1px;
    background: rgba(255, 255, 255, 26);
    margin: 5px 8px;
}}
QMenu::right-arrow {{
    width: 10px;
    height: 10px;
    margin-right: 8px;
}}
QDialog {{
    background-color: #151b26;
    color: {TEXT_MAIN};
}}
QDialog QLabel {{
    color: {TEXT_MAIN};
}}
QMessageBox {{
    background-color: #151b26;
}}
QMessageBox QLabel {{
    color: {TEXT_MAIN};
}}
QLineEdit {{
    background-color: rgba(255, 255, 255, 16);
    color: {TEXT_MAIN};
    border: 1px solid rgba(255, 255, 255, 40);
    border-radius: 8px;
    padding: 6px 10px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus {{
    border: 1px solid {ACCENT};
}}
QPushButton {{
    background-color: rgba(255, 255, 255, 18);
    color: {TEXT_MAIN};
    border: 1px solid rgba(255, 255, 255, 42);
    border-radius: 8px;
    padding: 6px 16px;
    font-size: 12px;
}}
QPushButton:hover {{
    background-color: rgba(255, 255, 255, 30);
    border-color: {ACCENT};
}}
QPushButton:pressed {{
    background-color: {ACCENT_DIM};
}}
QListWidget {{
    background-color: #121822;
    color: {TEXT_MAIN};
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 10px;
    padding: 4px;
    outline: none;
}}
QListWidget::item {{
    padding: 7px 8px;
    border-radius: 6px;
}}
QListWidget::item:selected {{
    background-color: {ACCENT_DIM};
    color: #ffffff;
}}
QListWidget::item:hover {{
    background-color: rgba(255, 255, 255, 22);
}}
QScrollBar:vertical {{
    background: transparent;
    width: 9px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: rgba(210, 224, 244, 70);
    border-radius: 4px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{
    background: {ACCENT};
}}
QScrollBar::horizontal {{
    background: transparent;
    height: 9px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: rgba(210, 224, 244, 70);
    border-radius: 4px;
    min-width: 28px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {ACCENT};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0px;
    width: 0px;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}
"""


def data_root_dir() -> Path:
    """返回项目根目录：打包后为 exe 所在目录，源码运行时为脚本目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return SCRIPT_DIR


def color_to_hex(color: QColor) -> str:
    return color.name(QColor.NameFormat.HexArgb)


def hex_to_color(value: str, default: QColor) -> QColor:
    color = QColor(value)
    return color if color.isValid() else default


def render_markdown(text: str) -> tuple[str, list[str]]:
    """将 markdown 转为 HTML，并提取视频引用（按扩展名识别）。

    图片以 markdown 图片语法 ![](path) 保留并由 HTML 渲染；
    视频同样用 ![](path) 语法，但扩展名属于视频时提取为独立播放块。
    """
    video_paths: list[str] = []

    def extract_video(match: re.Match) -> str:
        path = match.group(1).strip()
        if Path(path).suffix.lower() in VIDEO_EXTS:
            video_paths.append(path)
            return ""
        return match.group(0)

    processed = re.sub(r"!\[[^\]]*\]\(([^)]+)\)", extract_video, text)
    html = markdown.markdown(processed, extensions=["extra", "tables", "fenced_code", "sane_lists"])
    return html, video_paths


def fix_image_urls(html: str) -> str:
    """将 HTML 中本地绝对路径的 img src 转为 file:// URL，确保 QTextBrowser 能显示。"""
    def repl(match: re.Match) -> str:
        prefix, src, suffix = match.group(1), match.group(2), match.group(3)
        path = src.strip()
        if Path(path).is_absolute() and not path.startswith(("http:", "https:", "file:")):
            src = QUrl.fromLocalFile(path).toString()
        return f"{prefix}{src}{suffix}"

    return re.sub(r'(<img[^>]*src=")([^"]+)(")', repl, html)


def clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(value, upper))


class NoteStore:
    """便签持久化：内容存为 .md，元数据存为 index.json，媒体复制到 assets。"""

    def __init__(self) -> None:
        self.root = data_root_dir()
        self.file_root = self.root / "file"
        self.config_path = self.file_root / "config.json"
        self.notes_dir = self._resolve_notes_dir()
        self.assets_dir = self.notes_dir / "assets"
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.index: dict = self._load_index()

    def _resolve_notes_dir(self) -> Path:
        notes_dir_value = self._load_config().get("notes_dir", "file/notes")
        path = Path(notes_dir_value)
        if not path.is_absolute():
            path = self.root / path
        return path

    def _load_config(self) -> dict:
        try:
            with open(self.config_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return {}

    def save_config(self, notes_dir_value: str) -> None:
        self.file_root.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump({"notes_dir": notes_dir_value}, handle, ensure_ascii=False, indent=2)

    def config_notes_dir(self) -> str:
        return self._load_config().get("notes_dir", "file/notes")

    def _index_path(self) -> Path:
        return self.notes_dir / "index.json"

    def _load_index(self) -> dict:
        try:
            with open(self._index_path(), "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return {}

    def _save_index(self) -> None:
        with open(self._index_path(), "w", encoding="utf-8") as handle:
            json.dump(self.index, handle, ensure_ascii=False, indent=2)

    def new_id(self) -> str:
        return f"note-{int(time.time() * 1000)}"

    def save_note(self, note_id: str, content: str, meta: dict) -> None:
        with open(self.notes_dir / f"{note_id}.md", "w", encoding="utf-8") as handle:
            handle.write(content)
        self.index[note_id] = meta
        self._save_index()

    def load_note_content(self, note_id: str) -> str:
        try:
            with open(self.notes_dir / f"{note_id}.md", "r", encoding="utf-8") as handle:
                return handle.read()
        except Exception:
            return ""

    def get_meta(self, note_id: str) -> dict:
        return self.index.get(note_id, {})

    def delete_note(self, note_id: str) -> None:
        try:
            (self.notes_dir / f"{note_id}.md").unlink()
        except OSError:
            pass
        shutil.rmtree(self.assets_dir / note_id, ignore_errors=True)
        self.index.pop(note_id, None)
        self._save_index()

    def all_ids(self) -> list[str]:
        return list(self.index.keys())

    def copy_asset(self, note_id: str, src_path: str) -> Path:
        dest_dir = self.assets_dir / note_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        source = Path(src_path)
        dest = dest_dir / source.name
        if dest.exists():
            dest = dest_dir / f"{int(time.time() * 1000)}_{source.name}"
        shutil.copy2(source, dest)
        return dest


class NoteTitleBar(QFrame):
    """便签标题栏，同时作为拖动把手。"""

    def __init__(self, parent_note: "StickyNote") -> None:
        super().__init__(parent_note)
        self.parent_note = parent_note
        self.setObjectName("noteTitleBar")
        self.setFixedHeight(32)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self._drag_offset = QPoint()
        self._dragging = False

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.parent_note.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self.parent_note.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)


class VideoBlock(QFrame):
    """便签预览中内嵌的视频播放块。"""

    def __init__(self, file_path: str, parent=None) -> None:
        super().__init__(parent)
        self.file_path = file_path
        self.setObjectName("videoBlock")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(
            """
            QFrame#videoBlock {
                background-color: rgba(0, 0, 0, 30);
                border: 1px solid rgba(120, 130, 150, 90);
                border-radius: 10px;
            }
            QFrame#videoBlock QPushButton {
                padding: 3px 12px;
                font-size: 11px;
                border-radius: 6px;
            }
            """
        )

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.8)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.video_widget = QVideoWidget(self)
        self.player.setVideoOutput(self.video_widget)
        layout.addWidget(self.video_widget, 1)

        controls = QHBoxLayout()
        controls.setContentsMargins(2, 0, 2, 0)
        controls.setSpacing(6)
        self.name_label = QLabel(Path(file_path).name, self)
        self.name_label.setStyleSheet("color: rgba(120, 132, 150, 230); font-size: 11px;")
        self.play_button = QPushButton("播放", self)
        self.play_button.clicked.connect(self.toggle_playback)
        self.stop_button = QPushButton("停止", self)
        self.stop_button.clicked.connect(self.stop_playback)
        controls.addWidget(self.name_label)
        controls.addStretch(1)
        controls.addWidget(self.play_button)
        controls.addWidget(self.stop_button)
        layout.addLayout(controls)

        self.player.setSource(QUrl.fromLocalFile(file_path))
        self.player.mediaStatusChanged.connect(self._on_media_status)

    def toggle_playback(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.play_button.setText("继续")
        else:
            self.player.play()
            self.play_button.setText("暂停")

    def stop_playback(self) -> None:
        self.player.stop()
        self.play_button.setText("播放")

    def _on_media_status(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.player.stop()
            self.play_button.setText("播放")

    def closeEvent(self, event) -> None:
        self.player.stop()
        super().closeEvent(event)


class StickyNote(QWidget):
    """Markdown 便签窗口：编辑/预览切换，支持图片、视频渲染，实时持久化。"""

    def __init__(self, owner, store: NoteStore, note_id: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self.owner = owner
        self.store = store
        self.note_id = note_id or store.new_id()
        self.pinned = True
        self._mode = "edit"
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setObjectName("stickyRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(240, 180)
        self.resize(340, 300)

        self.bg_color = QColor(252, 248, 227)
        self.border_color = QColor(214, 191, 130)
        self.font_color = QColor(40, 36, 24)
        self.font_size = 14

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(8)

        self.title_bar = NoteTitleBar(self)
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(10, 0, 6, 0)
        title_layout.setSpacing(4)

        self.title_label = QLabel("便签", self.title_bar)
        self.title_label.setObjectName("noteTitle")
        self.view_toggle = QToolButton(self.title_bar)
        self.view_toggle.setText("预览")
        self.view_toggle.setToolTip("编辑 / 预览切换")
        self.view_toggle.clicked.connect(self.toggle_view)
        self.settings_button = QToolButton(self.title_bar)
        self.settings_button.setText("⚙")
        self.settings_button.setToolTip("样式与插入")
        self.settings_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.settings_button.setMenu(self._build_settings_menu())
        self.pin_button = QToolButton(self.title_bar)
        self.pin_button.setText("📌")
        self.pin_button.setCheckable(True)
        self.pin_button.setChecked(True)
        self.pin_button.setToolTip("置顶 / 取消置顶")
        self.pin_button.toggled.connect(self.toggle_pin)
        self.close_button = QToolButton(self.title_bar)
        self.close_button.setText("✕")
        self.close_button.setToolTip("关闭便签")
        self.close_button.setObjectName("noteClose")
        self.close_button.clicked.connect(self.close)

        title_layout.addWidget(self.title_label)
        title_layout.addStretch(1)
        title_layout.addWidget(self.view_toggle)
        title_layout.addWidget(self.settings_button)
        title_layout.addWidget(self.pin_button)
        title_layout.addWidget(self.close_button)
        root.addWidget(self.title_bar)

        self.stack = QStackedWidget(self)
        self.stack.setObjectName("noteStack")
        self.editor = QTextEdit()
        self.editor.setPlaceholderText("在此输入 Markdown 内容…\n例如：# 标题 / **粗体** / ![](图片路径)")
        self.editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.stack.addWidget(self.editor)

        self.preview_scroll = QScrollArea(self)
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.preview_container = QWidget()
        self.preview_layout = QVBoxLayout(self.preview_container)
        self.preview_layout.setContentsMargins(6, 6, 6, 6)
        self.preview_layout.setSpacing(8)
        self.preview_browser = QTextBrowser(self.preview_container)
        self.preview_browser.setOpenExternalLinks(True)
        self.preview_browser.setFrameShape(QFrame.Shape.NoFrame)
        self.preview_browser.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.preview_layout.addWidget(self.preview_browser)
        self.preview_scroll.setWidget(self.preview_container)
        self.stack.addWidget(self.preview_scroll)
        self._video_blocks: list[VideoBlock] = []
        root.addWidget(self.stack, 1)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.addStretch(1)
        grip = QSizeGrip(self)
        grip.setFixedSize(12, 12)
        bottom.addWidget(grip)
        root.addLayout(bottom)

        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(500)
        self.save_timer.timeout.connect(self.save_now)
        self.editor.textChanged.connect(self.schedule_save)

        self._stable_size = self.size()
        self._stable_pos = self.pos()
        self._screen_changing = False
        self._screen_sig_connected = False

        self.apply_style()
        self._restore_state()

    def paintEvent(self, event) -> None:
        """自绘圆角卡片与内层边框，避免依赖图形效果带来的重绘开销。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        radius = 12.0

        border = QColor(self.border_color)
        card = QColor(self.bg_color)

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        top = QColor(card)
        top.setAlpha(252)
        bottom_color = card.darker(106)
        bottom_color.setAlpha(246)
        gradient.setColorAt(0.0, top)
        gradient.setColorAt(1.0, bottom_color)
        painter.fillPath(path, gradient)

        pen = QPen(QColor(border.red(), border.green(), border.blue(), 235), 1.4)
        painter.setPen(pen)
        painter.drawPath(path)
        painter.end()

    def _restore_state(self) -> None:
        meta = self.store.get_meta(self.note_id)
        content = self.store.load_note_content(self.note_id)
        self.editor.setPlainText(content)
        if meta:
            self.bg_color = hex_to_color(meta.get("bg_color", ""), self.bg_color)
            self.border_color = hex_to_color(meta.get("border_color", ""), self.border_color)
            self.font_color = hex_to_color(meta.get("font_color", ""), self.font_color)
            self.font_size = int(meta.get("font_size", self.font_size))
            self.pinned = bool(meta.get("pinned", True))
            self.resize(int(meta.get("width", self.width())), int(meta.get("height", self.height())))
            self.move(int(meta.get("x", self.x())), int(meta.get("y", self.y())))
        self.apply_style()
        for action in getattr(self, "_font_size_actions", []):
            action.setChecked(action.text() == f"{self.font_size} px")
        blocked = self.pin_button.blockSignals(True)
        self.pin_button.setChecked(self.pinned)
        self.pin_button.blockSignals(blocked)
        self._apply_pin_flags()

    def _meta(self) -> dict:
        return {
            "x": self.x(),
            "y": self.y(),
            "width": self.width(),
            "height": self.height(),
            "bg_color": color_to_hex(self.bg_color),
            "border_color": color_to_hex(self.border_color),
            "font_color": color_to_hex(self.font_color),
            "font_size": self.font_size,
            "pinned": self.pinned,
        }

    def schedule_save(self) -> None:
        self.save_timer.start()

    def save_now(self) -> None:
        self.save_timer.stop()
        try:
            self.store.save_note(self.note_id, self.editor.toPlainText(), self._meta())
        except Exception:
            pass

    def toggle_view(self) -> None:
        if self._mode == "edit":
            self.set_preview_mode()
        else:
            self.set_edit_mode()

    def set_edit_mode(self) -> None:
        # 离开预览时释放视频播放器，避免占用内存
        self._clear_video_blocks()
        self.preview_browser.clear()
        self._mode = "edit"
        self.stack.setCurrentWidget(self.editor)
        self.view_toggle.setText("预览")

    def set_preview_mode(self) -> None:
        self._render_preview()
        self._mode = "preview"
        self.stack.setCurrentWidget(self.preview_scroll)
        self.view_toggle.setText("编辑")

    def _render_preview(self) -> None:
        html, video_paths = render_markdown(self.editor.toPlainText())
        html = fix_image_urls(html)
        self.preview_browser.setHtml(self._wrap_html(html))
        self._clear_video_blocks()
        for path in video_paths:
            block = VideoBlock(path, self.preview_container)
            self._video_blocks.append(block)
            self.preview_layout.addWidget(block)

    def _clear_video_blocks(self) -> None:
        for block in self._video_blocks:
            block.close()
            self.preview_layout.removeWidget(block)
            block.deleteLater()
        self._video_blocks.clear()

    def _wrap_html(self, body: str) -> str:
        fg = self.font_color.name()
        border = self.border_color.name()
        style = (
            f"body {{ color:{fg}; font-size:{self.font_size}px; line-height:1.5; margin:0; }}"
            "p { margin:4px 0; }"
            "h1,h2,h3,h4,h5,h6 { margin:10px 0 5px; line-height:1.25; font-weight:700; }"
            "h1 { font-size:1.42em; }"
            "h2 { font-size:1.26em; }"
            "h3 { font-size:1.12em; }"
            f"h1,h2 {{ border-bottom:1px solid {border}; padding-bottom:3px; }}"
            "ul,ol { margin:4px 0; padding-left:24px; }"
            "li { margin:2px 0; }"
            "a { color:#2f6fd0; }"
            "code { background:rgba(120,120,120,40); padding:1px 4px; border-radius:4px; }"
            "pre { margin:6px 0; padding:8px 10px; background:rgba(120,120,120,35);"
            " border-radius:8px; white-space:pre-wrap; }"
            "pre code { background:transparent; padding:0; }"
            f"blockquote {{ margin:6px 0; padding:2px 0 2px 10px;"
            f" border-left:3px solid {border}; opacity:0.9; }}"
            "hr { border:none; border-top:1px solid rgba(140,140,140,120); margin:8px 0; }"
            "table { border-collapse:collapse; margin:6px 0; }"
            "th,td { border:1px solid rgba(140,140,140,120); padding:3px 7px; }"
            "img { max-width:100%; border-radius:6px; }"
        )
        return f"<html><head><style>{style}</style></head><body>{body}</body></html>"

    def _build_settings_menu(self) -> QMenu:
        menu = QMenu(self)
        insert_image = QAction("插入图片", menu)
        insert_image.triggered.connect(self.insert_image)
        insert_video = QAction("插入视频", menu)
        insert_video.triggered.connect(self.insert_video)
        menu.addAction(insert_image)
        menu.addAction(insert_video)
        menu.addSeparator()

        font_size_menu = QMenu("字体大小", menu)
        self._font_size_actions: list[QAction] = []
        for size in (12, 14, 16, 18, 20, 24, 28):
            action = QAction(f"{size} px", font_size_menu)
            action.setCheckable(True)
            action.setChecked(size == self.font_size)
            action.triggered.connect(lambda checked=False, s=size: self.set_font_size(s))
            font_size_menu.addAction(action)
            self._font_size_actions.append(action)
        menu.addMenu(font_size_menu)

        font_color = QAction("字体颜色…", menu)
        font_color.triggered.connect(self.set_font_color)
        bg_color = QAction("背景颜色…", menu)
        bg_color.triggered.connect(self.set_bg_color)
        border_color = QAction("边框颜色…", menu)
        border_color.triggered.connect(self.set_border_color)
        menu.addSeparator()
        menu.addAction(font_color)
        menu.addAction(bg_color)
        menu.addAction(border_color)
        return menu

    def insert_image(self) -> None:
        self.set_edit_mode()
        path, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "", "图片 (*.png *.jpg *.jpeg *.gif *.bmp *.webp)"
        )
        if not path:
            return
        dest = self.store.copy_asset(self.note_id, path)
        self._insert_markdown(f"![]({dest.as_posix()})\n")

    def insert_video(self) -> None:
        self.set_edit_mode()
        path, _ = QFileDialog.getOpenFileName(
            self, "选择视频", "", "视频 (*.mp4 *.avi *.mkv *.mov *.webm *.wmv)"
        )
        if not path:
            return
        dest = self.store.copy_asset(self.note_id, path)
        self._insert_markdown(f"![]({dest.as_posix()})\n")

    def _insert_markdown(self, text: str) -> None:
        cursor = self.editor.textCursor()
        cursor.insertText(text)
        self.editor.setTextCursor(cursor)
        self.schedule_save()

    def apply_style(self) -> None:
        """卡片由 paintEvent 自绘，子控件保持透明以露出卡片底色。"""
        fg = self.font_color.name()
        border = self.border_color.name()
        # 标题栏用边框色的浅色调，形成层次
        tint = QColor(self.border_color)
        tint.setAlpha(120)
        tint_hex = tint.name(QColor.NameFormat.HexArgb)
        self.title_bar.setStyleSheet(
            f"""
            QFrame#noteTitleBar {{
                background-color: {tint_hex};
                border: none;
                border-radius: 8px;
            }}
            QFrame#noteTitleBar QLabel#noteTitle {{
                color: {fg};
                font-weight: 700;
                font-size: 12px;
            }}
            QFrame#noteTitleBar QToolButton {{
                color: {fg};
                background: transparent;
                border: none;
                border-radius: 6px;
                padding: 2px 7px;
                font-size: 12px;
            }}
            QFrame#noteTitleBar QToolButton:hover {{
                background: rgba(255, 255, 255, 120);
            }}
            QFrame#noteTitleBar QToolButton:checked {{
                background: rgba(76, 141, 255, 150);
                color: #ffffff;
            }}
            QFrame#noteTitleBar QToolButton#noteClose:hover {{
                background: rgba(226, 74, 74, 210);
                color: #ffffff;
            }}
            """
        )
        self.editor.setStyleSheet(
            f"""
            QTextEdit {{
                background: transparent;
                color: {fg};
                border: none;
                padding: 4px 6px;
                font-size: {self.font_size}px;
                selection-background-color: {border};
            }}
            """
        )
        self.preview_browser.setStyleSheet(
            f"QTextBrowser {{ background: transparent; color: {fg}; border: none; padding: 4px 6px; }}"
        )
        self.preview_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.preview_container.setStyleSheet("background: transparent;")
        self.preview_container.setAutoFillBackground(False)
        self.stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")
        self.update()

    def _refresh_style_dependents(self) -> None:
        """样式变化后，预览的 HTML 需要重绘才能同步颜色与字号。"""
        self.apply_style()
        if self._mode == "preview":
            self._render_preview()
        self.schedule_save()

    def set_font_size(self, size: int) -> None:
        self.font_size = size
        for action in getattr(self, "_font_size_actions", []):
            action.setChecked(action.text() == f"{size} px")
        self._refresh_style_dependents()

    def set_font_color(self) -> None:
        color = QColorDialog.getColor(self.font_color, self, "选择字体颜色")
        if color.isValid():
            self.font_color = color
            self._refresh_style_dependents()

    def set_bg_color(self) -> None:
        color = QColorDialog.getColor(self.bg_color, self, "选择背景颜色")
        if color.isValid():
            self.bg_color = color
            self._refresh_style_dependents()

    def set_border_color(self) -> None:
        color = QColorDialog.getColor(self.border_color, self, "选择边框颜色")
        if color.isValid():
            self.border_color = color
            self._refresh_style_dependents()

    def _apply_pin_flags(self) -> None:
        flags = self.windowFlags()
        if self.pinned:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def toggle_pin(self, checked: bool) -> None:
        self.pinned = checked
        self._apply_pin_flags()
        self.show()
        self.schedule_save()

    def _update_max_size(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry().size()
            self.setMaximumSize(available)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        handle = self.windowHandle()
        if handle is not None and not self._screen_sig_connected:
            handle.screenChanged.connect(self._on_screen_changed)
            self._screen_sig_connected = True
        self._update_max_size()

    def _on_screen_changed(self) -> None:
        # 跨屏移动时保持窗口逻辑大小不变，并按当前屏限制最大尺寸
        self._screen_changing = True
        self._update_max_size()
        self.resize(self._stable_size)
        self._screen_changing = False

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        if not self._screen_changing:
            self._stable_pos = event.pos()
        self.schedule_save()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._screen_changing:
            self._stable_size = event.size()
        self.schedule_save()

    def closeEvent(self, event) -> None:
        self.save_now()
        self._clear_video_blocks()
        if self.owner is not None:
            self.owner.note_closed(self)
        super().closeEvent(event)


class NoteListDialog(QDialog):
    """便签列表对话框，支持打开与删除已保存便签。"""

    def __init__(self, store: NoteStore, owner, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("便签列表")
        self.store = store
        self.owner = owner
        self.resize(440, 380)
        self.setStyleSheet(APP_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        hint = QLabel("双击条目打开便签", self)
        hint.setStyleSheet("color: " + TEXT_SUB + "; font-size: 11px;")
        layout.addWidget(hint)

        self.list_widget = QListWidget(self)
        self.list_widget.setAlternatingRowColors(False)
        self.list_widget.itemDoubleClicked.connect(self._open_selected)
        layout.addWidget(self.list_widget, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        open_button = QPushButton("打开", self)
        open_button.clicked.connect(self._open_selected)
        delete_button = QPushButton("删除", self)
        delete_button.clicked.connect(self._delete_selected)
        close_button = QPushButton("关闭", self)
        close_button.clicked.connect(self.accept)
        buttons.addWidget(open_button)
        buttons.addWidget(delete_button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self._refresh()

    def _refresh(self) -> None:
        self.list_widget.clear()
        for note_id in self.store.all_ids():
            content = self.store.load_note_content(note_id)
            stripped = content.strip()
            first_line = stripped.splitlines()[0] if stripped else "(空便签)"
            item = QListWidgetItem(f"{first_line[:48]}    [{note_id}]")
            item.setData(Qt.ItemDataRole.UserRole, note_id)
            self.list_widget.addItem(item)

    def _selected_id(self):
        item = self.list_widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _open_selected(self) -> None:
        note_id = self._selected_id()
        if note_id:
            self.owner.open_note(note_id)
            self.accept()

    def _delete_selected(self) -> None:
        note_id = self._selected_id()
        if not note_id:
            return
        confirm = QMessageBox.question(
            self,
            APP_NAME,
            f"确认删除便签 {note_id}？该操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.owner.close_note_if_open(note_id)
            self.store.delete_note(note_id)
            self._refresh()


class NotesApp:
    """便签应用主控：通过系统托盘图标管理便签的创建、列表与配置。"""

    def __init__(self) -> None:
        self.store = NoteStore()
        self.sticky_notes: list[StickyNote] = []
        self.tray = QSystemTrayIcon()
        self.tray.setIcon(self._build_tray_icon())
        self.tray.setToolTip(APP_NAME)
        self.tray.setVisible(True)
        self._build_tray_menu()

        self.tray.activated.connect(self._on_tray_activated)

    def _build_tray_icon(self) -> QIcon:
        """生成一个简易便签形状的托盘图标。"""
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(8, 8, 48, 48)
        path = QPainterPath()
        path.addRoundedRect(rect, 8, 8)
        painter.fillPath(path, QColor(252, 248, 227))
        painter.setPen(QPen(QColor(214, 191, 130), 2))
        painter.drawPath(path)
        # 折角
        fold = QPainterPath()
        fold.moveTo(40, 8)
        fold.lineTo(56, 24)
        fold.lineTo(40, 24)
        fold.closeSubpath()
        painter.fillPath(fold, QColor(214, 191, 130))
        painter.setPen(QColor(40, 36, 24))
        font = QFont("Microsoft YaHei UI", 20, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "便")
        painter.end()
        return QIcon(pixmap)

    def _build_tray_menu(self) -> None:
        menu = QMenu()
        menu.setStyleSheet(APP_STYLESHEET)

        new_note_action = QAction("新建便签", menu)
        new_note_action.triggered.connect(self.create_new_note)
        note_list_action = QAction("便签列表", menu)
        note_list_action.triggered.connect(self.show_note_list)
        note_dir_action = QAction("便签存储位置…", menu)
        note_dir_action.triggered.connect(self.configure_note_dir)
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self.quit_app)

        menu.addAction(new_note_action)
        menu.addAction(note_list_action)
        menu.addSeparator()
        menu.addAction(note_dir_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self._tray_menu = menu  # setContextMenu 不获取所有权，必须保持引用防止被 GC
        self.tray.setContextMenu(menu)

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.create_new_note()

    def current_screen_geometry(self):
        screen = QApplication.primaryScreen()
        return screen.availableGeometry() if screen else None

    def load_saved_notes(self) -> None:
        for note_id in self.store.all_ids():
            self.open_note(note_id, place_default=False)

    def create_new_note(self) -> None:
        self.open_note(None, place_default=True)

    def open_note(self, note_id, place_default: bool = True) -> None:
        if note_id is not None:
            for note in self.sticky_notes:
                if note.note_id == note_id:
                    note.raise_()
                    note.activateWindow()
                    return
        note = StickyNote(self, self.store, note_id)
        note.setParent(None)
        geometry = self.current_screen_geometry()
        meta = self.store.get_meta(note.note_id) if note_id else {}
        if meta and not place_default and geometry is not None:
            x = clamp(int(meta.get("x", note.x())), geometry.left(), geometry.x() + geometry.width() - 60)
            y = clamp(int(meta.get("y", note.y())), geometry.top(), geometry.y() + geometry.height() - 60)
            note.move(x, y)
        elif geometry is not None:
            offset = 24 * len(self.sticky_notes) % 160
            x = clamp(
                geometry.x() + geometry.width() - note.width() - 48,
                geometry.left(),
                geometry.x() + geometry.width() - note.width(),
            )
            y = clamp(geometry.y() + 72 + offset, geometry.top(), geometry.y() + geometry.height() - note.height())
            note.move(x, y)
        self.sticky_notes.append(note)
        note.show()

    def show_note_list(self) -> None:
        dialog = NoteListDialog(self.store, self, None)
        dialog.exec()
        dialog.deleteLater()

    def configure_note_dir(self) -> None:
        dialog = QDialog(None)
        dialog.setWindowTitle("便签存储位置")
        dialog.setMinimumWidth(420)
        dialog.setStyleSheet(APP_STYLESHEET)
        form = QFormLayout(dialog)
        form.setContentsMargins(18, 18, 18, 18)
        form.setSpacing(10)
        edit = QLineEdit(self.store.config_notes_dir())
        edit.setPlaceholderText("例如 file/notes 或 D:/notes")
        form.addRow("存储路径（相对项目根或绝对路径）：", edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dialog
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        value = edit.text().strip()
        dialog.deleteLater()
        if accepted and value:
            self.store.save_config(value)
            QMessageBox.information(None, APP_NAME, "已保存。将在下次启动时生效。")

    def note_closed(self, note) -> None:
        try:
            self.sticky_notes.remove(note)
        except ValueError:
            pass

    def close_note_if_open(self, note_id: str) -> None:
        for note in list(self.sticky_notes):
            if note.note_id == note_id:
                note.close()

    def quit_app(self) -> None:
        for note in list(self.sticky_notes):
            note.save_now()
            note.close()
        self.tray.hide()
        QApplication.instance().quit()


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)
    app.setQuitOnLastWindowClosed(False)
    notes_app = NotesApp()
    notes_app.load_saved_notes()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
