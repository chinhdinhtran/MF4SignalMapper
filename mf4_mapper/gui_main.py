from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QStyle,
)

from .channel_mapper import ChannelAutoMapper
from .config import load_config
from .mf4_inspector import Mf4Inspector
from .pipeline import ConversionPipeline

LOGGER = logging.getLogger(__name__)


class ConversionWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(int, str)

    def __init__(self, raw_mf4: str, dbc: str, output_mf4: str, config: str):
        super().__init__()
        self.raw_mf4 = raw_mf4
        self.dbc = dbc
        self.output_mf4 = output_mf4
        self.config = config

    @Slot()
    def run(self) -> None:
        try:
            self.progress.emit(5, "Opening raw MF4...")
            pipeline = ConversionPipeline(self.config)
            self.progress.emit(10, "Inspecting CAN channels...")
            report = pipeline.convert(
                self.raw_mf4,
                self.dbc,
                self.output_mf4,
                progress_callback=self._on_pipeline_progress,
            )
            self.progress.emit(100, "Export completed")
            self.finished.emit(report)
        except Exception as exc:
            LOGGER.exception("Conversion failed")
            self.failed.emit(str(exc))

    def _on_pipeline_progress(self, percent: int, message: str) -> None:
        self.progress.emit(max(0, min(100, int(percent))), message)


class ChannelMapWidget(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(self)
        title = QLabel("Detected CAN channel mapping")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Channel", "Network", "Status", "Marker ID(s)", "Frames"]
        )
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        layout.addWidget(self.table)

    def clear(self) -> None:
        self.table.setRowCount(0)

    def set_assignments(self, profiles, assignments) -> None:
        self.table.setRowCount(0)
        for assignment in assignments:
            row = self.table.rowCount()
            self.table.insertRow(row)
            profile = profiles.get(assignment.channel)
            marker_ids = ", ".join(f"0x{x:X}" for x in assignment.matched_ids) or "-"
            network = assignment.logical_name or f"CAN{assignment.channel}"
            frames = str(profile.frame_count if profile else 0)

            values = [
                f"CAN{assignment.channel}",
                network,
                assignment.status.upper(),
                marker_ids,
                frames,
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 2:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)


class MainWindow(QMainWindow):
    APP_TITLE = "MF4 Signal Mapper"

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(self.APP_TITLE)
        self.resize(980, 720)
        self.setMinimumSize(820, 600)

        self._config_path = Path(__file__).resolve().parents[1] / "mapping.json"
        self._worker_thread: QThread | None = None
        self._worker: ConversionWorker | None = None
        self._build_ui()
        self._build_menu()
        self._apply_style()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(14)

        title = QLabel(self.APP_TITLE)
        title.setObjectName("appTitle")
        root.addWidget(title)

        subtitle = QLabel(
            "Map raw CAN frames in an MF4 with one common DBC and export a new MF4 "
            "containing decoded signal channels."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        root.addWidget(self._build_file_row(
            "Raw MF4 log", "raw_mf4_edit", "Browse...", self._select_raw_mf4, self._clear_raw_mf4
        ))
        root.addWidget(self._build_file_row(
            "CAN DBC", "dbc_edit", "Browse...", self._select_dbc, self._clear_dbc
        ))
        root.addWidget(self._build_file_row(
            "Output MF4", "output_edit", "Save As...", self._select_output, self._clear_output
        ))

        self.mapping_widget = ChannelMapWidget()
        root.addWidget(self.mapping_widget, 1)

        self.status_label = QLabel("Select a raw MF4 log and a DBC to begin.")
        self.status_label.setObjectName("statusLabel")
        root.addWidget(self.status_label)

        progress_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        progress_row.addWidget(self.progress, 1)
        self.export_button = QPushButton("Export mapped MF4")
        self.export_button.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.export_button.clicked.connect(self._start_export)
        self.export_button.setEnabled(False)
        progress_row.addWidget(self.export_button)
        root.addLayout(progress_row)

        note = QLabel(
            "Remove only clears the selected file from this tool; it does not delete the file from disk."
        )
        note.setObjectName("note")
        root.addWidget(note)

        self.raw_mf4_edit = self.findChild(QLineEdit, "raw_mf4_edit")
        self.dbc_edit = self.findChild(QLineEdit, "dbc_edit")
        self.output_edit = self.findChild(QLineEdit, "output_edit")

    def _build_file_row(
        self,
        label_text: str,
        object_name: str,
        browse_text: str,
        browse_slot: Callable[[], None],
        clear_slot: Callable[[], None],
    ) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label = QLabel(label_text)
        label.setFixedWidth(105)
        layout.addWidget(label)

        edit = QLineEdit()
        edit.setObjectName(object_name)
        edit.setReadOnly(True)
        edit.setPlaceholderText(f"Select {label_text.lower()}...")
        layout.addWidget(edit, 1)

        browse = QPushButton(browse_text)
        browse.clicked.connect(browse_slot)
        layout.addWidget(browse)

        clear = QPushButton("Remove")
        clear.setToolTip("Remove the selected file from the current session")
        clear.clicked.connect(clear_slot)
        layout.addWidget(clear)

        return container

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")

        action_open_raw = QAction("Import raw MF4...", self)
        action_open_raw.triggered.connect(self._select_raw_mf4)
        file_menu.addAction(action_open_raw)

        action_open_dbc = QAction("Import DBC...", self)
        action_open_dbc.triggered.connect(self._select_dbc)
        file_menu.addAction(action_open_dbc)

        file_menu.addSeparator()
        action_export = QAction("Export mapped MF4...", self)
        action_export.triggered.connect(self._start_export)
        file_menu.addAction(action_export)

        file_menu.addSeparator()
        action_exit = QAction("Exit", self)
        action_exit.triggered.connect(self.close)
        file_menu.addAction(action_exit)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background: #f5f7fa; }
            QLabel#appTitle { font-size: 24px; font-weight: 700; color: #202124; }
            QLabel#subtitle { color: #5f6368; font-size: 13px; }
            QLabel#sectionTitle { font-size: 15px; font-weight: 600; color: #202124; }
            QLabel#statusLabel { color: #3c4043; }
            QLabel#note { color: #6b7280; font-size: 11px; }
            QFrame { background: white; border: 1px solid #d9dee7; border-radius: 8px; }
            QLineEdit { background: white; border: 1px solid #cfd5df; border-radius: 5px; padding: 7px; }
            QPushButton { padding: 7px 12px; border: 1px solid #c7ccd5; border-radius: 5px; background: #ffffff; }
            QPushButton:hover { background: #f0f3f7; }
            QPushButton:disabled { color: #9aa0a6; background: #eef1f4; }
            QTableWidget { border: none; gridline-color: #e4e7eb; }
            QHeaderView::section { background: #eef1f4; padding: 6px; border: none; font-weight: 600; }
            QProgressBar { border: 1px solid #cfd5df; border-radius: 5px; background: white; height: 18px; }
            QProgressBar::chunk { background: #5b7cff; border-radius: 4px; }
            """
        )

    def _update_export_enabled(self) -> None:
        ready = bool(self.raw_mf4_edit.text().strip() and self.dbc_edit.text().strip())
        self.export_button.setEnabled(ready and self._worker_thread is None)

    def _select_raw_mf4(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select raw MF4 log",
            "",
            "MDF4 files (*.mf4 *.MDF4);;All files (*.*)",
        )
        if not path:
            return
        self.raw_mf4_edit.setText(path)
        self._set_default_output(path)
        self._inspect_raw(path)
        self._update_export_enabled()

    def _select_dbc(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select CAN DBC",
            "",
            "DBC files (*.dbc *.DBC);;All files (*.*)",
        )
        if not path:
            return
        self.dbc_edit.setText(path)
        self.status_label.setText("DBC selected. Raw channel mapping is ready for export.")
        self._update_export_enabled()

    def _select_output(self) -> None:
        default = self.output_edit.text().strip() or "mapped.mf4"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export mapped MF4",
            default,
            "MDF4 files (*.mf4 *.MDF4);;All files (*.*)",
        )
        if not path:
            return
        if not path.lower().endswith(".mf4"):
            path += ".mf4"
        self.output_edit.setText(path)
        self._update_export_enabled()

    def _clear_raw_mf4(self) -> None:
        self.raw_mf4_edit.clear()
        self.mapping_widget.clear()
        self.status_label.setText("Raw MF4 removed from the current session.")
        self._update_export_enabled()

    def _clear_dbc(self) -> None:
        self.dbc_edit.clear()
        self.status_label.setText("DBC removed from the current session.")
        self._update_export_enabled()

    def _clear_output(self) -> None:
        self.output_edit.clear()
        self._update_export_enabled()

    def _set_default_output(self, raw_path: str) -> None:
        source = Path(raw_path)
        self.output_edit.setText(str(source.with_name(source.stem + "_mapped.mf4")))

    def _inspect_raw(self, path: str) -> None:
        self.status_label.setText("Inspecting raw CAN channels...")
        QApplication.processEvents()
        try:
            config = load_config(self._config_path)
            from asammdf import MDF

            mdf = MDF(path)
            try:
                profiles = Mf4Inspector().inspect(mdf)
                assignments = ChannelAutoMapper(config.marker_rules).classify_all(profiles)
            finally:
                mdf.close()

            self.mapping_widget.set_assignments(profiles, assignments)
            if assignments:
                mapped = sum(1 for item in assignments if item.status == "mapped")
                ambiguous = sum(1 for item in assignments if item.status == "ambiguous")
                unknown = sum(1 for item in assignments if item.status == "unknown")
                self.status_label.setText(
                    f"Detected {len(assignments)} CAN channel(s): "
                    f"{mapped} mapped, {ambiguous} ambiguous, {unknown} unknown."
                )
            else:
                self.status_label.setText("No raw CAN_DataFrame channels were detected.")
        except Exception as exc:
            self.mapping_widget.clear()
            self.status_label.setText("Unable to inspect MF4.")
            QMessageBox.warning(
                self,
                "MF4 inspection failed",
                f"Could not inspect the selected MF4:\n\n{exc}",
            )

    def _start_export(self) -> None:
        raw = self.raw_mf4_edit.text().strip()
        dbc = self.dbc_edit.text().strip()
        output = self.output_edit.text().strip()

        if not raw or not dbc:
            QMessageBox.warning(self, "Missing input", "Select both the raw MF4 and the DBC.")
            return

        if not output:
            self._set_default_output(raw)
            output = self.output_edit.text().strip()

        if Path(raw).resolve() == Path(output).resolve():
            QMessageBox.warning(self, "Invalid output", "Output MF4 must be different from the raw MF4.")
            return

        if Path(output).exists():
            answer = QMessageBox.question(
                self,
                "Overwrite output?",
                f"The output file already exists:\n\n{output}\n\nOverwrite it?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        self._set_busy(True)
        self.progress.setValue(0)
        self.status_label.setText("Starting export...")

        self._worker_thread = QThread(self)
        self._worker = ConversionWorker(raw, dbc, output, str(self._config_path))
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._worker_thread.quit)
        self._worker.failed.connect(self._worker_thread.quit)
        self._worker_thread.finished.connect(self._cleanup_worker)
        self._worker_thread.start()

    def _on_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(percent)
        self.status_label.setText(message)

    def _on_finished(self, report) -> None:
        self.progress.setValue(100)
        self.status_label.setText(f"Export completed: {report.output_file}")
        QMessageBox.information(
            self,
            "Export completed",
            "Mapped MF4 created successfully.\n\n"
            f"Output: {report.output_file}\n"
            f"Decoded groups: {report.decoded_groups}\n"
            f"Decoded signals: {report.decoded_signals}",
        )

    def _on_failed(self, message: str) -> None:
        self.status_label.setText("Export failed.")
        self.progress.setValue(0)
        QMessageBox.critical(self, "Export failed", message)

    def _set_busy(self, busy: bool) -> None:
        self.export_button.setEnabled(not busy)
        self._update_export_enabled() if not busy else None

    @Slot()
    def _cleanup_worker(self) -> None:
        if self._worker_thread is not None:
            self._worker_thread.deleteLater()
        if self._worker is not None:
            self._worker.deleteLater()
        self._worker_thread = None
        self._worker = None
        self._set_busy(False)

    def closeEvent(self, event) -> None:
        if self._worker_thread is not None and self._worker_thread.isRunning():
            QMessageBox.warning(
                self,
                "Conversion in progress",
                "Please wait for the current export to finish before closing the tool.",
            )
            event.ignore()
            return
        event.accept()


def run_gui() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(MainWindow.APP_TITLE)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run_gui())
