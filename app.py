import sys
import json
import requests
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                                 QHBoxLayout, QTextEdit, QLabel, QPushButton,
                                 QFileDialog, QComboBox, QLineEdit, QMessageBox,
                                 QProgressBar, QDialog, QDialogButtonBox,
                                 QFormLayout, QListWidget, QListWidgetItem)
from PySide6.QtCore import Qt, QThread, Signal, QSettings
from PySide6.QtGui import QIcon  # 导入 QIcon
import qdarktheme
from zhipuai import ZhipuAI
from datetime import datetime
import os


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.settings = QSettings("LyricsTranslatorPro", "Settings")

        self.api_key_input = QLineEdit()
        saved_api_key = self.settings.value("api_key", "")
        self.api_key_input.setText(saved_api_key)
        self.api_key_input.setEchoMode(QLineEdit.Password)

        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.save_settings)
        button_box.rejected.connect(self.reject)

        layout = QFormLayout()
        layout.addRow(QLabel("GLM-4 API Key:"), self.api_key_input)
        layout.addRow(button_box)

        self.setLayout(layout)

    def save_settings(self):
        api_key = self.api_key_input.text().strip()
        self.settings.setValue("api_key", api_key)
        self.accept()


class TranslationWorker(QThread):
    finished = Signal(str, str, str)
    error = Signal(str, str)
    progress = Signal(int)

    def __init__(self, translator, text, target_lang, filename):
        super().__init__()
        self.translator = translator
        self.text = text
        self.target_lang = target_lang
        self.filename = filename

    def run(self):
        try:
            translated_text = self.translator.translate(self.text, self.target_lang)
            self.finished.emit(translated_text, "", self.filename)
        except Exception as e:
            self.error.emit(str(e), self.filename)


class GLMTranslator:
    def __init__(self, api_key):
        self.api_key = api_key
        self.client = ZhipuAI(api_key=api_key)

    def translate(self, text, target_lang):
        try:
            response = self.client.chat.completions.create(
                model="glm-4-flash",
                messages=[
                    {
                        "role": "user",
                        "content": f"**Translate the following lyrics EXCLUSIVELY into {target_lang}.**  "
                                    f"It is crucial that the translated lyrics are **entirely in {target_lang}**, with **no mixing of languages.** "
                                    f"Maintain the original poetic and emotional tone, ensuring grammatical correctness and natural flow – **all within the {target_lang} language only.** "
                                    f"Preserve the original formatting, including line breaks and any verse/chorus structure.\n\n"
                                    f"**Do NOT include any words, phrases, or sentences from the original language or any other language besides {target_lang} in the translation.**\n\n"
                                    f"Lyrics to translate:\n{text}"
                    }
                ],
        )
            translated_text = response.choices[0].message.content
            return translated_text
        except Exception as e:
            error_msg = f"API Error: {str(e)}"
            if "Invalid authentication credentials" in str(e):
                error_msg = "Invalid API Key. Please check your API key in Settings."
            elif "Rate limit exceeded" in str(e):
                error_msg = "API Rate Limit Exceeded. Please wait and try again later."
            raise Exception(error_msg)


class LocalTranslator:
    def translate(self, text, target_lang):
        lines = text.split('\n')
        translated = [f"[{target_lang.upper()} {i + 1}] {line}" for i, line in enumerate(lines)]
        return '\n'.join(translated)


class TranslationApp(QMainWindow):
    def __init__(self):
        super().__init__()

        app_icon = QIcon("./lyric_translate.ico") # 创建 QIcon 对象
        self.setWindowIcon(app_icon) # 设置窗口图标

        self.setWindowTitle("Lyrics Translator Pro")
        self.setMinimumSize(800, 600) # 适当调整最小尺寸，可以根据你的喜好设置

        self.settings = QSettings("LyricsTranslatorPro", "Settings")
        self.api_key = self.settings.value("api_key", "")

        self.translators = {
            "GLM-4-Flash": None,
            "Local Engine": LocalTranslator()
        }

        self.file_paths = []
        self.current_file_index = 0
        self.total_files = 0

        self.init_ui()
        self.setup_styles()
        self.apply_font_scaling() # 初始应用字体缩放

    def setup_styles(self):
        qdarktheme.setup_theme("auto")
        self.setStyleSheet("""
            QTextEdit {
                font-family: 'Consolas';
                font-size: 12pt; /* 基础字体大小，会根据缩放调整 */
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px;
            }
            QLabel {
                font-weight: bold;
                font-size: 12pt; /* 基础字体大小，会根据缩放调整 */
            }
            QProgressBar {
                height: 20px;
                text-align: center;
                border-radius: 8px;
            }
            QListWidget {
                font-family: 'Consolas';
                font-size: 10pt; /* 基础字体大小，会根据缩放调整 */
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px;
            }
            QPushButton {
                font-size: 14px; /* 基础字体大小，会根据缩放调整 */
                padding: 5px 10px;
            }
            QComboBox {
                font-size: 12pt; /* 基础字体大小，会根据缩放调整 */
                padding: 5px;
            }
        """)

    def init_ui(self):
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # Header Section
        header_layout = QHBoxLayout()
        self.engine_combo = QComboBox()
        self.engine_combo.addItems(["GLM-4-Flash", "Local Engine"])

        self.lang_combo = QComboBox()
        self.lang_combo.addItems([
            "English", "Chinese", "Japanese",
            "Korean", "Spanish", "French",
            "German", "Italian", "Russian"
        ])
        self.lang_combo.setCurrentText("Chinese")

        self.settings_btn = QPushButton("⚙️ Settings")
        self.settings_btn.clicked.connect(self.open_settings)

        header_layout.addWidget(QLabel("Engine:"))
        header_layout.addWidget(self.engine_combo)
        header_layout.addStretch()
        header_layout.addWidget(QLabel("Target Language:"))
        header_layout.addWidget(self.lang_combo)
        header_layout.addWidget(self.settings_btn)

        # Text Areas
        text_layout = QHBoxLayout()
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("Original Lyrics will be shown here during translation...")
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setPlaceholderText("Translation will appear here...")

        text_layout.addWidget(self.input_text)
        text_layout.addWidget(self.output_text)

        # File List Display
        file_list_layout = QHBoxLayout()
        self.file_list_label = QLabel("Selected Files:")
        self.file_list_display = QListWidget()
        self.file_list_display.setVisible(False)
        self.file_status_display = QLineEdit()
        self.file_status_display.setReadOnly(True)
        self.file_status_display.setVisible(False)

        file_list_layout.addWidget(self.file_list_display)

        # Current File Label & Progress Bars
        self.current_file_label = QLabel("Processing File: None")
        self.current_file_label.setVisible(False)
        self.overall_progress_bar = QProgressBar()
        self.overall_progress_bar.setVisible(False)
        self.overall_progress_label = QLabel("Overall Progress:")
        self.overall_progress_label.setVisible(False)
        self.file_progress_bar = QProgressBar()
        self.file_progress_bar.setVisible(False)
        self.file_progress_label = QLabel("File Progress:")
        self.file_progress_label.setVisible(False)

        # Control Buttons
        button_layout = QHBoxLayout()
        self.open_btn = QPushButton("📂 Open Files")
        self.translate_btn = QPushButton("🌍 Translate")
        self.save_btn = QPushButton("💾 Save Result")
        self.save_btn.setEnabled(False)

        for btn in [self.open_btn, self.translate_btn, self.save_btn]:
            btn.setFixedHeight(40) # 按钮高度可以固定，宽度会缩放

        self.open_btn.clicked.connect(self.open_files)
        self.translate_btn.clicked.connect(self.start_translation)
        self.save_btn.clicked.connect(self.save_file)

        button_layout.addWidget(self.open_btn)
        button_layout.addWidget(self.translate_btn)
        button_layout.addWidget(self.save_btn)

        # Assemble Layout
        main_layout.addLayout(header_layout, stretch=1)
        main_layout.addLayout(text_layout, stretch=6)
        main_layout.addWidget(self.file_list_label, stretch=1)
        main_layout.addLayout(file_list_layout, stretch=2)
        main_layout.addWidget(self.current_file_label, stretch=1)
        main_layout.addWidget(self.overall_progress_label, stretch=1)
        main_layout.addWidget(self.overall_progress_bar, stretch=1)
        main_layout.addWidget(self.file_progress_label, stretch=1)
        main_layout.addWidget(self.file_progress_bar, stretch=1)
        main_layout.addLayout(button_layout, stretch=1)

        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

    def open_settings(self):
        settings_dialog = SettingsDialog(self)
        settings_dialog.exec()
        self.api_key = self.settings.value("api_key", "")

    def open_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Open Lyrics Files", "",
            "Text Files (*.txt);;Lyric Files (*.lrc);;All Files (*)"
        )
        if file_paths:
            self.file_paths = file_paths
            self.input_text.clear()
            self.output_text.clear()
            self.file_list_display.clear()

            if len(file_paths) > 1:
                self.file_list_display.setVisible(True)
                self.file_list_label.setVisible(True)
                for path in file_paths:
                    filename = os.path.basename(path)
                    item = QListWidgetItem(filename)
                    self.file_list_display.addItem(item)

                QMessageBox.information(self, "Info", f"Opened {len(file_paths)} files for batch translation. Click 'Translate' to begin.")
            elif len(file_paths) == 1:
                self.file_list_display.setVisible(False)
                self.file_list_label.setVisible(False)
                try:
                    with open(file_paths[0], 'r', encoding='utf-8') as f:
                        self.input_text.setPlainText(f.read())
                    self.file_paths = []
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to open file:\n{str(e)}")
            else:
                self.file_list_display.setVisible(False)
                self.file_list_label.setVisible(False)

    def save_file(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Translation", "",
            "Text Files (*.txt);;Lyric Files (*.lrc);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.output_text.toPlainText())
                QMessageBox.information(self, "Success", "File saved successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save file:\n{str(e)}")

    def save_translated_file(self, translated_text, original_filename):
        base, ext = os.path.splitext(original_filename)
        target_lang = self.lang_combo.currentText()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_filename = f"{base}_{target_lang}_{timestamp}.lrc"
        save_path = os.path.join(os.path.dirname(original_filename), save_filename)

        try:
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(translated_text)
            return True, save_path
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save translated file:\n{str(e)}")
            return False, None

    def start_translation(self):
        engine = self.engine_combo.currentText()
        target_lang = self.lang_combo.currentText().lower()

        if self.file_paths:
            if engine == "GLM-4-Flash" and not self.api_key:
                QMessageBox.warning(self, "Error", "API Key is required for GLM-4-Flash! Please set it in Settings.")
                return
            self.start_batch_translation(engine, target_lang, self.file_paths)
        else:
            text = self.input_text.toPlainText().strip()
            if not text:
                QMessageBox.warning(self, "Error", "Please enter or load lyrics to translate!")
                return
            if engine == "GLM-4-Flash" and not self.api_key:
                QMessageBox.warning(self, "Error", "API Key is required for GLM-4-Flash! Please set it in Settings.")
                return
            self.start_single_translation(engine, target_lang, text)

    def start_single_translation(self, engine, target_lang, text):
        self._prepare_ui_for_translation()
        self.save_btn.setEnabled(True)
        self.input_text.setPlainText(text)

        try:
            translator = self._create_translator_instance(engine)
        except Exception as e:
            self.handle_error(str(e), "Single File Translation")
            return

        self.worker = TranslationWorker(translator, text, target_lang, "single_file")
        self.worker.finished.connect(self.handle_translation_result)
        self.worker.error.connect(self.handle_error)
        self.worker.start()

    def start_batch_translation(self, engine, target_lang, file_paths):
        self._prepare_ui_for_translation(is_batch=True)
        self.save_btn.setEnabled(False)
        self.input_text.clear()
        self.output_text.clear()
        self.current_file_label.setVisible(True)

        self.file_paths = file_paths
        self.total_files = len(file_paths)
        self.current_file_index = 0

        self.overall_progress_bar.setRange(0, self.total_files)
        self.overall_progress_bar.setValue(0)
        self.overall_progress_label.setVisible(True)
        self.overall_progress_bar.setVisible(True)

        self.translate_next_file_in_batch(engine, target_lang)

    def translate_next_file_in_batch(self, engine, target_lang):
        if self.current_file_index < self.total_files:
            filepath = self.file_paths[self.current_file_index]
            filename = os.path.basename(filepath)

            self.current_file_label.setText(f"Processing File: {filename}")
            self.file_progress_label.setText(f"File Progress: Translating {filename} ({self.current_file_index + 1}/{self.total_files})")
            self.file_progress_label.setVisible(True)
            self.file_progress_bar.setVisible(True)
            self.file_progress_bar.setRange(0, 0)

            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    text = f.read()
                    self.input_text.setPlainText(text)

                list_item = self.file_list_display.item(self.current_file_index)
                list_item.setData(Qt.UserRole, filename)

            except Exception as e:
                self.handle_batch_error(f"Failed to open file {filename}:\n{str(e)}", filename)
                return

            try:
                translator = self._create_translator_instance(engine)
            except Exception as e:
                self.handle_batch_error(str(e), filename)
                return

            self.worker = TranslationWorker(translator, text, target_lang, filename)
            self.worker.finished.connect(self.handle_batch_translation_result)
            self.worker.error.connect(self.handle_batch_error)
            self.worker.start()
        else:
            self.batch_translation_finished()

    def _create_translator_instance(self, engine):
        if engine == "GLM-4-Flash":
            return GLMTranslator(self.api_key)
        else:
            return self.translators[engine]

    def _prepare_ui_for_translation(self, is_batch=False):
        self.overall_progress_bar.setVisible(False)
        self.overall_progress_label.setVisible(False)
        self.file_progress_bar.setVisible(True)
        self.file_progress_label.setVisible(True)
        self.file_progress_bar.setRange(0, 0)
        self.set_buttons_enabled(False)
        self.output_text.clear()

    def handle_translation_result(self, result, warning, filename):
        self.file_progress_bar.setVisible(False)
        self.file_progress_label.setVisible(False)
        self.set_buttons_enabled(True)
        self.output_text.setPlainText(result)
        if warning:
            QMessageBox.warning(self, "Warning", warning)

    def handle_batch_translation_result(self, result, warning, filename):
        list_item = self.file_list_display.item(self.current_file_index)
        if list_item:
            original_filename = list_item.text()
            list_item.setText(f"{original_filename} - Translated")

        self.output_text.setPlainText(result)
        success, save_path = self.save_translated_file(result, filename)
        self.file_progress_bar.setVisible(False)
        self.file_progress_label.setVisible(False)
        if warning:
            QMessageBox.warning(self, "Warning", warning)

        self.current_file_index += 1
        self.overall_progress_bar.setValue(self.current_file_index)
        engine = self.engine_combo.currentText()
        target_lang = self.lang_combo.currentText().lower()
        self.translate_next_file_in_batch(engine, target_lang)

    def handle_error(self, error_msg, filename):
        self.file_progress_bar.setVisible(False)
        self.file_progress_label.setVisible(False)
        self.set_buttons_enabled(True)
        QMessageBox.critical(self, "Error", f"Error during translation:\n{error_msg}")

    def handle_batch_error(self, error_msg, filename):
        list_item = self.file_list_display.item(self.current_file_index)
        if list_item:
            original_filename = list_item.text()
            list_item.setText(f"{original_filename} - Error")

        self.file_progress_bar.setVisible(False)
        self.file_progress_label.setVisible(False)
        QMessageBox.critical(self, "Batch Translation Error", f"Error processing file {filename}:\n{error_msg}")
        self.current_file_index += 1
        self.overall_progress_bar.setValue(self.current_file_index)
        engine = self.engine_combo.currentText()
        target_lang = self.lang_combo.currentText().lower()
        self.translate_next_file_in_batch(engine, target_lang)

    def batch_translation_finished(self):
        self.overall_progress_bar.setVisible(False)
        self.overall_progress_label.setVisible(False)
        self.file_progress_bar.setVisible(False)
        self.file_progress_label.setVisible(False)
        self.current_file_label.setVisible(False)
        self.file_list_label.setVisible(False)
        self.set_buttons_enabled(True)
        QMessageBox.information(self, "Batch Translation", "Batch translation completed!")
        self.file_paths = []
        self.total_files = 0
        self.current_file_index = 0

    def set_buttons_enabled(self, enabled):
        for btn in [self.open_btn, self.translate_btn, self.settings_btn, self.engine_combo, self.lang_combo]:
            btn.setEnabled(enabled)

    def apply_font_scaling(self):
        """根据窗口宽度动态调整字体大小"""
        window_width = self.width()
        base_width = 1200.0  # 你可以根据你的初始UI设计的宽度调整这个基准值
        scale_factor = max(0.5, window_width / base_width) # 缩放因子，最小0.5，避免字体过小

        app_font = QApplication.font()
        default_font_size = 12 #  默认字体大小，与你的样式表中的基础字体大小一致
        scaled_font_size = int(default_font_size * scale_factor)
        app_font.setPointSize(max(8, scaled_font_size)) # 字体大小最小8，避免过小无法阅读
        QApplication.setFont(app_font)

    def resizeEvent(self, event):
        """窗口大小改变事件处理器，重新应用字体缩放"""
        super().resizeEvent(event)
        self.apply_font_scaling()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    app_icon = QIcon("./lyric_translate.ico") # 创建 QApplication 的 QIcon 对象
    app.setWindowIcon(app_icon) # 设置 QApplication 的窗口图标

    window = TranslationApp()
    window.show()
    sys.exit(app.exec())
