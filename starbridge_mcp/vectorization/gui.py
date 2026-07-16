from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import (
    QCloseEvent,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from . import engine
from .app_model import (
    MODE_CARDS,
    AppInputError,
    AppParameters,
    build_run_config,
    parameters_for_mode,
    result_metrics,
    validated_input_path,
)
from .engine import RunConfig, VectorizationError, run_vectorization

APP_STYLE = """
QWidget {
    background: #0b1020;
    color: #e8ecf7;
    font-family: "Microsoft YaHei UI";
    font-size: 13px;
}
QMainWindow { background: #0b1020; }
QScrollArea { border: none; }
QFrame#panel, QFrame#previewCard, QFrame#modeCard, QFrame#metricCard {
    background: #121a2d;
    border: 1px solid #24304a;
    border-radius: 14px;
}
QFrame#modeCard[checked="true"] {
    background: #17233b;
    border: 1px solid #5b8cff;
}
QLabel#eyebrow { color: #7ca4ff; font-size: 12px; font-weight: 700; }
QLabel#title { color: #f7f9ff; font-size: 25px; font-weight: 750; }
QLabel#subtitle, QLabel#muted { color: #91a0bc; }
QLabel#sectionTitle { color: #f4f7ff; font-size: 15px; font-weight: 700; }
QLabel#modeTitle { color: #f4f7ff; font-size: 14px; font-weight: 700; }
QLabel#modeTag { color: #7ca4ff; font-size: 12px; }
QLabel#dropPreview {
    background: #0d1425;
    border: 1px dashed #344563;
    border-radius: 11px;
    color: #71809c;
    padding: 10px;
}
QLabel#metricValue { color: #ffffff; font-size: 18px; font-weight: 750; }
QLabel#metricLabel { color: #8190aa; font-size: 11px; }
QPushButton {
    min-height: 38px;
    border-radius: 9px;
    padding: 0 16px;
    background: #1a2741;
    border: 1px solid #30405f;
    color: #eaf0ff;
    font-weight: 650;
}
QPushButton:hover { background: #223252; border-color: #47628f; }
QPushButton#primaryButton {
    min-height: 44px;
    background: #5b7cfa;
    border-color: #6d8cff;
    color: white;
}
QPushButton#primaryButton:hover { background: #6a89ff; }
QPushButton:disabled { background: #172036; color: #596680; border-color: #27324a; }
QSpinBox, QDoubleSpinBox {
    min-height: 32px;
    background: #0e1628;
    border: 1px solid #2b3854;
    border-radius: 7px;
    padding: 0 8px;
    color: #edf2ff;
}
QRadioButton { spacing: 8px; }
QProgressBar {
    min-height: 6px;
    max-height: 6px;
    border: none;
    border-radius: 3px;
    background: #1b2740;
    text-align: center;
}
QProgressBar::chunk { background: #5b7cfa; border-radius: 3px; }
"""


class DropPreview(QLabel):
    image_dropped = Signal(str)

    def __init__(self, instruction: str, *, accepts_drop: bool = False) -> None:
        super().__init__(instruction)
        self._instruction = instruction
        self._source_pixmap: QPixmap | None = None
        self.setObjectName("dropPreview")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(300, 300)
        self.setWordWrap(True)
        self.setAcceptDrops(accepts_drop)

    def set_image(self, path: Path) -> bool:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.clear_image("无法预览该文件")
            return False
        self._source_pixmap = pixmap
        self._refresh_pixmap()
        return True

    def clear_image(self, message: str | None = None) -> None:
        self._source_pixmap = None
        self.setPixmap(QPixmap())
        self.setText(message or self._instruction)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._refresh_pixmap()

    def _refresh_pixmap(self) -> None:
        if self._source_pixmap is None:
            return
        available = self.size()
        scaled = self._source_pixmap.scaled(
            max(1, available.width() - 24),
            max(1, available.height() - 24),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setText("")
        self.setPixmap(scaled)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile():
            suffix = Path(urls[0].toLocalFile()).suffix.lower()
            if suffix in {".png", ".jpg", ".jpeg"}:
                event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            self.image_dropped.emit(urls[0].toLocalFile())
            event.acceptProposedAction()


class ModeOption(QFrame):
    selected = Signal(str)

    def __init__(self, key: str, title: str, tagline: str, detail: str) -> None:
        super().__init__()
        self.key = key
        self.setObjectName("modeCard")
        self.setProperty("checked", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 11, 13, 11)
        layout.setSpacing(3)
        top = QHBoxLayout()
        self.radio = QRadioButton()
        title_label = QLabel(title)
        title_label.setObjectName("modeTitle")
        top.addWidget(self.radio)
        top.addWidget(title_label)
        top.addStretch()
        layout.addLayout(top)
        tag_label = QLabel(tagline)
        tag_label.setObjectName("modeTag")
        detail_label = QLabel(detail)
        detail_label.setObjectName("muted")
        detail_label.setWordWrap(True)
        layout.addWidget(tag_label)
        layout.addWidget(detail_label)
        self.radio.toggled.connect(self._on_toggled)

    @Slot(bool)
    def _on_toggled(self, checked: bool) -> None:
        self.setProperty("checked", checked)
        self.style().unpolish(self)
        self.style().polish(self)
        if checked:
            self.selected.emit(self.key)

    def mousePressEvent(self, event: Any) -> None:
        self.radio.setChecked(True)
        super().mousePressEvent(event)


class VectorWorker(QObject):
    succeeded = Signal(dict)
    failed = Signal(str, str)
    finished = Signal()

    def __init__(self, config: RunConfig) -> None:
        super().__init__()
        self.config = config

    @Slot()
    def run(self) -> None:
        try:
            self.succeeded.emit(run_vectorization(self.config))
        except VectorizationError as exc:
            self.failed.emit(exc.code, str(exc))
        except Exception:
            self.failed.emit("vectorization_failed", "转换失败，未发布未经验证的输出文件。")
        finally:
            self.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("VectorFlow Studio · StarBridge")
        self.resize(1320, 860)
        self.setMinimumSize(1080, 720)
        self._input_path: Path | None = None
        self._output_path: Path | None = None
        self._thread: QThread | None = None
        self._worker: VectorWorker | None = None
        self._mode_options: dict[str, ModeOption] = {}
        self._metric_labels: list[tuple[QLabel, QLabel]] = []
        self._build_ui()
        self._select_mode("smart")

    @property
    def selected_mode(self) -> str:
        for key, option in self._mode_options.items():
            if option.radio.isChecked():
                return key
        return "smart"

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(24, 20, 24, 22)
        root_layout.setSpacing(16)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        eyebrow = QLabel("STARBRIDGE / LOCAL VECTOR ENGINE")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("VectorFlow Studio")
        title.setObjectName("title")
        subtitle = QLabel("本地图片矢量化 · 无嵌入位图 · 可验证输出")
        subtitle.setObjectName("subtitle")
        heading.addWidget(eyebrow)
        heading.addWidget(title)
        heading.addWidget(subtitle)
        header.addLayout(heading)
        header.addStretch()
        privacy = QLabel("● LOCAL ONLY   素材不上传")
        privacy.setObjectName("eyebrow")
        header.addWidget(privacy)
        root_layout.addLayout(header)

        content = QHBoxLayout()
        content.setSpacing(16)
        content.addWidget(self._build_control_panel(), 0)
        content.addWidget(self._build_workspace(), 1)
        root_layout.addLayout(content, 1)

    def _build_control_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(350)
        body = QFrame()
        body.setObjectName("panel")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        section = QLabel("01  选择矢量模式")
        section.setObjectName("sectionTitle")
        layout.addWidget(section)
        group = QButtonGroup(self)
        group.setExclusive(True)
        for card in MODE_CARDS:
            option = ModeOption(card.key, card.title, card.tagline, card.detail)
            option.selected.connect(self._select_mode)
            group.addButton(option.radio)
            self._mode_options[card.key] = option
            layout.addWidget(option)

        parameters_title = QLabel("02  调整参数")
        parameters_title.setObjectName("sectionTitle")
        layout.addWidget(parameters_title)
        form = QFormLayout()
        form.setSpacing(9)
        self.colors_input = QSpinBox()
        self.colors_input.setRange(2, 256)
        self.dimension_input = QSpinBox()
        self.dimension_input.setRange(16, 4096)
        self.dimension_input.setSuffix(" px")
        self.simplify_input = QDoubleSpinBox()
        self.simplify_input.setRange(0.0, 0.1)
        self.simplify_input.setDecimals(3)
        self.simplify_input.setSingleStep(0.001)
        self.region_input = QSpinBox()
        self.region_input.setRange(0, 100_000)
        self.region_input.setSuffix(" px")
        self.alpha_input = QSpinBox()
        self.alpha_input.setRange(0, 255)
        form.addRow("颜色数量", self.colors_input)
        form.addRow("最大尺寸", self.dimension_input)
        form.addRow("路径平滑", self.simplify_input)
        form.addRow("碎片清理", self.region_input)
        form.addRow("透明阈值", self.alpha_input)
        layout.addLayout(form)

        self.exact_note = QLabel("精确模式固定使用源 RGBA 像素，不应用设计简化参数。")
        self.exact_note.setObjectName("muted")
        self.exact_note.setWordWrap(True)
        layout.addWidget(self.exact_note)
        layout.addStretch()

        choose_button = QPushButton("选择图片")
        choose_button.clicked.connect(self.choose_input)
        layout.addWidget(choose_button)
        self.start_button = QPushButton("开始矢量化")
        self.start_button.setObjectName("primaryButton")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_conversion)
        layout.addWidget(self.start_button)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.status_label = QLabel("拖入或选择一张图片开始")
        self.status_label.setObjectName("muted")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        scroll.setWidget(body)
        return scroll

    def _build_workspace(self) -> QWidget:
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        previews = QHBoxLayout()
        previews.setSpacing(14)
        source_card, self.source_preview = self._preview_card(
            "原图", "拖放 PNG / JPEG 到这里\n或使用左侧“选择图片”", True
        )
        result_card, self.result_preview = self._preview_card(
            "矢量预览", "完成转换后显示本地 PNG 预览", False
        )
        self.source_preview.image_dropped.connect(self.set_source)
        previews.addWidget(source_card, 1)
        previews.addWidget(result_card, 1)
        layout.addLayout(previews, 1)

        metrics_panel = QFrame()
        metrics_panel.setObjectName("panel")
        metrics_layout = QVBoxLayout(metrics_panel)
        metrics_layout.setContentsMargins(15, 13, 15, 13)
        metrics_layout.setSpacing(10)
        metrics_header = QHBoxLayout()
        result_title = QLabel("结果指标")
        result_title.setObjectName("sectionTitle")
        metrics_header.addWidget(result_title)
        metrics_header.addStretch()
        self.open_output_button = QPushButton("打开输出目录")
        self.open_output_button.setEnabled(False)
        self.open_output_button.clicked.connect(self.open_output_dir)
        metrics_header.addWidget(self.open_output_button)
        metrics_layout.addLayout(metrics_header)
        cards = QHBoxLayout()
        cards.setSpacing(9)
        for _ in range(6):
            card = QFrame()
            card.setObjectName("metricCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 8, 12, 8)
            value = QLabel("—")
            value.setObjectName("metricValue")
            label = QLabel("等待结果")
            label.setObjectName("metricLabel")
            card_layout.addWidget(value)
            card_layout.addWidget(label)
            self._metric_labels.append((value, label))
            cards.addWidget(card, 1)
        metrics_layout.addLayout(cards)
        layout.addWidget(metrics_panel)
        return workspace

    def _preview_card(
        self, title: str, instruction: str, accepts_drop: bool
    ) -> tuple[QFrame, DropPreview]:
        card = QFrame()
        card.setObjectName("previewCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(13, 12, 13, 13)
        heading = QLabel(title)
        heading.setObjectName("sectionTitle")
        preview = DropPreview(instruction, accepts_drop=accepts_drop)
        layout.addWidget(heading)
        layout.addWidget(preview, 1)
        return card, preview

    @Slot()
    def choose_input(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "选择图片", "", "图片 (*.png *.jpg *.jpeg)")
        if filename:
            self.set_source(filename)

    @Slot(str)
    def set_source(self, value: str) -> None:
        try:
            path = validated_input_path(value)
        except AppInputError as exc:
            self.status_label.setText(str(exc))
            return
        self._input_path = path
        self._output_path = None
        self.source_preview.set_image(path)
        self.result_preview.clear_image()
        self.open_output_button.setEnabled(False)
        self.start_button.setEnabled(True)
        self.status_label.setText(f"已载入：{path.name}")
        self._clear_metrics()

    @Slot(str)
    def _select_mode(self, mode: str) -> None:
        option = self._mode_options.get(mode)
        if option is not None and not option.radio.isChecked():
            option.radio.setChecked(True)
        parameters = parameters_for_mode(mode)
        is_exact = parameters.mode == "exact"
        if not is_exact:
            assert parameters.colors is not None
            assert parameters.max_dimension is not None
            assert parameters.simplify_ratio is not None
            assert parameters.min_region_area is not None
            assert parameters.alpha_threshold is not None
            self.colors_input.setValue(parameters.colors)
            self.dimension_input.setValue(parameters.max_dimension)
            self.simplify_input.setValue(parameters.simplify_ratio)
            self.region_input.setValue(parameters.min_region_area)
            self.alpha_input.setValue(parameters.alpha_threshold)
        for control in (
            self.colors_input,
            self.dimension_input,
            self.simplify_input,
            self.region_input,
            self.alpha_input,
        ):
            control.setEnabled(not is_exact)
        self.exact_note.setVisible(is_exact)

    def _current_parameters(self) -> AppParameters:
        mode = self.selected_mode
        if mode == "exact":
            return AppParameters(mode="exact")
        return AppParameters(
            mode=mode,
            colors=self.colors_input.value(),
            max_dimension=self.dimension_input.value(),
            simplify_ratio=self.simplify_input.value(),
            min_region_area=self.region_input.value(),
            alpha_threshold=self.alpha_input.value(),
        )

    @Slot()
    def start_conversion(self) -> None:
        if self._input_path is None or self._thread is not None:
            return
        try:
            config = build_run_config(self._input_path, self._current_parameters())
        except AppInputError as exc:
            self.status_label.setText(str(exc))
            return
        self._set_busy(True)
        self.status_label.setText("正在本地分析颜色、区域和轮廓……")
        thread = QThread(self)
        worker = VectorWorker(config)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._conversion_succeeded)
        worker.failed.connect(self._conversion_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        thread.start()

    @Slot(dict)
    def _conversion_succeeded(self, result: dict[str, Any]) -> None:
        output_value = result.get("output_dir", "")
        output_path = Path(output_value)
        if not output_path.is_absolute():
            output_path = engine.REPO_ROOT / output_path
        self._output_path = output_path.resolve()
        preview = next(
            (
                item
                for item in result.get("artifacts", [])
                if item.get("role") == "processed_preview"
            ),
            None,
        )
        if preview:
            preview_path = Path(preview["path"])
            if not preview_path.is_absolute():
                preview_path = engine.REPO_ROOT / preview_path
            self.result_preview.set_image(preview_path)
        self._show_metrics(result)
        self.open_output_button.setEnabled(True)
        structure = result.get("artisan_structure")
        structure_note = f" · {structure['structure_ref']}" if structure else ""
        self.status_label.setText(
            f"完成 · {result['mode']['label_zh']} · SVG 已验证{structure_note}"
        )

    @Slot(str, str)
    def _conversion_failed(self, code: str, message: str) -> None:
        self.status_label.setText(f"未完成 [{code}]：{message}")

    @Slot()
    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self.start_button.setEnabled(not busy and self._input_path is not None)
        if busy:
            self.start_button.setText("处理中…")
            self.progress.setRange(0, 0)
        else:
            self.start_button.setText("开始矢量化")
            self.progress.setRange(0, 1)
            self.progress.setValue(1 if self._output_path else 0)

    def _show_metrics(self, result: dict[str, Any]) -> None:
        metrics = result_metrics(result)
        for index, (value_label, name_label) in enumerate(self._metric_labels):
            if index < len(metrics):
                name, value = metrics[index]
                value_label.setText(value)
                name_label.setText(name)
            else:
                value_label.setText("—")
                name_label.setText("等待结果")

    def _clear_metrics(self) -> None:
        for value_label, name_label in self._metric_labels:
            value_label.setText("—")
            name_label.setText("等待结果")

    @Slot()
    def open_output_dir(self) -> None:
        if self._output_path is not None and self._output_path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._output_path)))

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._thread is not None and self._thread.isRunning():
            QMessageBox.information(self, "任务正在运行", "请等待当前本地转换完成后再关闭。")
            event.ignore()
            return
        event.accept()


def run() -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("VectorFlow Studio")
    app.setOrganizationName("StarBridge")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(APP_STYLE)
    window = MainWindow()
    window.show()
    return app.exec()
