import sys
import json
import requests
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                                    QHBoxLayout, QTextEdit, QLabel, QPushButton,
                                    QFileDialog, QComboBox, QLineEdit, QMessageBox,
                                    QProgressBar, QDialog, QDialogButtonBox,
                                    QFormLayout, QListWidget, QListWidgetItem) # Import QListWidget and QListWidgetItem
from PySide6.QtCore import Qt, QThread, Signal, QSettings
import qdarktheme
from zhipuai import ZhipuAI  # Import the zhipuai library
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
    finished = Signal(str, str, str)  # Signal(translated_text, warning, filename)
    error = Signal(str, str)  # Signal(error_message, filename)
    progress = Signal(int) # Signal(percentage)

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
        # Initialize ZhipuAI client using the API key
        self.client = ZhipuAI(api_key=api_key)

    def translate(self, text, target_lang):
        try:
            # Use client.chat.completions.create to call the glm-4 model
            response = self.client.chat.completions.create(
                model="glm-4-flash",  # Specify the model name as glm-4
                messages=[
                        {
                            "role": "user",
                            # More Precise Prompt for Lyrics Translation - Language Purity Focus
                            "content": f"**Translate the following lyrics EXCLUSIVELY into {target_lang}.**  "
                                        f"It is crucial that the translated lyrics are **entirely in {target_lang}**, with **no mixing of languages.** "
                                        f"Maintain the original poetic and emotional tone, ensuring grammatical correctness and natural flow – **all within the {target_lang} language only.** "
                                        f"Preserve the original formatting, including line breaks and any verse/chorus structure.\n\n"
                                        f"**Do NOT include any words, phrases, or sentences from the original language or any other language besides {target_lang} in the translation.**\n\n"
                                        f"Lyrics to translate:\n{text}"
                        }
                ],
            )
            # Extract the translated content from the response
            translated_text = response.choices[0].message.content
            return translated_text
        except Exception as e:
            error_msg = f"API Error: {str(e)}"
            # More specific error handling can be added here based on zhipuai library's exceptions
            if "Invalid authentication credentials" in str(e):
                error_msg = "Invalid API Key. Please check your API key in Settings."
            elif "Rate limit exceeded" in str(e):  # Example for rate limit error (adjust as per actual error message)
                error_msg = "API Rate Limit Exceeded. Please wait and try again later."
            raise Exception(error_msg)


class LocalTranslator:
    def translate(self, text, target_lang):
        # Simple mock translation preserving line breaks
        lines = text.split('\n')
        translated = [f"[{target_lang.upper()} {i + 1}] {line}" for i, line in enumerate(lines)]
        return '\n'.join(translated)


class TranslationApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lyrics Translator Pro")
        self.setMinimumSize(1200, 800) # Increase width

        self.settings = QSettings("LyricsTranslatorPro", "Settings")
        self.api_key = self.settings.value("api_key", "")

        self.translators = {
            "GLM-4-Flash": None,  # We'll initialize GLM-4-Flash translator only when needed and with API Key
            "Local Engine": LocalTranslator()
        }

        self.file_paths = [] # List to store multiple file paths for batch translation
        self.current_file_index = 0 # Index to track current file in batch
        self.total_files = 0 # Total number of files in batch

        self.init_ui()
        self.setup_styles()

    def setup_styles(self):
        qdarktheme.setup_theme("auto")
        self.setStyleSheet("""
            QTextEdit {
                font-family: 'Consolas';
                font-size: 12pt;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px;
            }
            QLabel {
                font-weight: bold;
                font-size: 12pt;
            }
            QProgressBar {
                height: 20px;
                text-align: center;
                border-radius: 8px;
            }
            QListWidget {
                font-family: 'Consolas';
                font-size: 10pt;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px;
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
        self.engine_combo.addItems(["GLM-4-Flash", "Local Engine"])  # Keep "GLM-4-Flash" as UI option
        self.engine_combo.setFixedWidth(200)

        self.lang_combo = QComboBox()
        self.lang_combo.addItems([
            "English", "Chinese", "Japanese",
            "Korean", "Spanish", "French",
            "German", "Italian", "Russian"
        ])
        self.lang_combo.setCurrentText("Chinese")
        self.lang_combo.setFixedWidth(150)

        self.settings_btn = QPushButton("⚙️ Settings")
        self.settings_btn.setFixedWidth(100)
        self.settings_btn.clicked.connect(self.open_settings)

        header_layout.addWidget(QLabel("Engine:"))
        header_layout.addWidget(self.engine_combo)
        header_layout.addStretch()
        header_layout.addWidget(QLabel("Target Language:"))
        header_layout.addWidget(self.lang_combo)
        header_layout.addWidget(self.settings_btn)


        # Text Areas - Take 60% of vertical space
        text_layout = QHBoxLayout()
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("Original Lyrics will be shown here during translation...") # Updated placeholder
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setPlaceholderText("Translation will appear here...")

        text_layout.addWidget(self.input_text)
        text_layout.addWidget(self.output_text)

        # File List Display with Status - Horizontal Layout
        file_list_layout = QHBoxLayout()
        self.file_list_label = QLabel("Selected Files:")
        self.file_list_display = QListWidget() # Use QListWidget to list files
        self.file_list_display.setVisible(False) # Initially Hidden
        self.file_status_display = QLineEdit() # Text box for status - now will be integrated into list
        self.file_status_display.setReadOnly(True)
        self.file_status_display.setVisible(False) # Hide initially, will manage status in ListWidgetItem

        file_list_layout.addWidget(self.file_list_display)
        # file_list_layout.addWidget(self.file_status_display) # No longer directly adding status box, managed in list

        # Current File Label - To show current file being translated
        self.current_file_label = QLabel("Processing File: None")
        self.current_file_label.setVisible(False) # Initially Hidden

        # Progress Bar - Overall Batch Progress
        self.overall_progress_bar = QProgressBar()
        self.overall_progress_bar.setVisible(False)
        self.overall_progress_label = QLabel("Overall Progress:")
        self.overall_progress_label.setVisible(False)

        # Progress Bar - File Progress (for each file in batch)
        self.file_progress_bar = QProgressBar()
        self.file_progress_bar.setVisible(False)
        self.file_progress_label = QLabel("File Progress:")
        self.file_progress_label.setVisible(False)


        # Control Buttons
        button_layout = QHBoxLayout()
        self.open_btn = QPushButton("📂 Open Files") # Changed button text to indicate multi-file
        self.translate_btn = QPushButton("🌍 Translate")
        self.save_btn = QPushButton("💾 Save Result")
        self.save_btn.setEnabled(False) # Disable single save in batch mode initially

        for btn in [self.open_btn, self.translate_btn, self.save_btn]:
            btn.setFixedHeight(40)
            btn.setStyleSheet("font-size: 14px;")

        self.open_btn.clicked.connect(self.open_files) # Changed to open_files
        self.translate_btn.clicked.connect(self.start_translation)
        self.save_btn.clicked.connect(self.save_file) # Single save will be for the last translated file


        button_layout.addWidget(self.open_btn)
        button_layout.addWidget(self.translate_btn)
        button_layout.addWidget(self.save_btn)

        # Assemble layout - Adjust vertical weights, text area takes more space (weight 6)
        main_layout.addLayout(header_layout, stretch=1) # Header takes less space
        main_layout.addLayout(text_layout, stretch=6)   # Text areas take 60% (weight 6 of total 10 approx)
        main_layout.addWidget(self.file_list_label, stretch=1) # File list section takes less space
        main_layout.addLayout(file_list_layout, stretch=2) # File list display and status
        main_layout.addWidget(self.current_file_label, stretch=1) # Labels and progresses less space
        main_layout.addWidget(self.overall_progress_label, stretch=1)
        main_layout.addWidget(self.overall_progress_bar, stretch=1)
        main_layout.addWidget(self.file_progress_label, stretch=1)
        main_layout.addWidget(self.file_progress_bar, stretch=1)
        main_layout.addLayout(button_layout, stretch=1) # Buttons less space

        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

    def open_settings(self):
        settings_dialog = SettingsDialog(self)
        settings_dialog.exec()
        self.api_key = self.settings.value("api_key", "") # Update API key in main app

    def open_files(self): # Modified to open_files
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Open Lyrics Files", "",
            "Text Files (*.txt);;Lyric Files (*.lrc);;All Files (*)"
        )
        if file_paths:
            self.file_paths = file_paths # Store multiple file paths
            self.input_text.clear() # Clear input and output text when opening new files.
            self.output_text.clear()
            self.file_list_display.clear() # Clear previous file list

            if len(file_paths) > 1:
                self.file_list_display.setVisible(True) # Show file list when multiple files selected
                self.file_list_label.setVisible(True)
                for path in file_paths:
                    filename = os.path.basename(path)
                    item = QListWidgetItem(filename)
                    self.file_list_display.addItem(item) # Add items to list, status will be appended later

                QMessageBox.information(self, "Info", f"Opened {len(file_paths)} files for batch translation. Click 'Translate' to begin.")
            elif len(file_paths) == 1:
                self.file_list_display.setVisible(False) # Hide file list if only single file selected
                self.file_list_label.setVisible(False)
                try:
                    with open(file_paths[0], 'r', encoding='utf-8') as f:
                        self.input_text.setPlainText(f.read())
                    self.file_paths = [] # Clear file_paths if only one file opened, reverting to single file mode.
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to open file:\n{str(e)}")
            else:
                self.file_list_display.setVisible(False)
                self.file_list_label.setVisible(False)


    def save_file(self): # Single save function - saves the content of output_text
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Translation", "",
            "Text Files (*.txt);;Lyric Files (*.lrc);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.output_text.toPlainText())
                QMessageBox.information(self, "Success", "File saved successfully!") # Keep save success message
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
            return True, save_path # Return success and save path
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save translated file:\n{str(e)}")
            return False, None # Return failure


    def start_translation(self):
        engine = self.engine_combo.currentText()
        target_lang = self.lang_combo.currentText().lower()

        if self.file_paths: # Batch translation mode
            if engine == "GLM-4-Flash" and not self.api_key:
                QMessageBox.warning(self, "Error", "API Key is required for GLM-4-Flash! Please set it in Settings.")
                return
            self.start_batch_translation(engine, target_lang, self.file_paths)
        else: # Single file translation mode
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
        self.save_btn.setEnabled(True) # Enable single save for single file mode
        self.input_text.setPlainText(text) # Show text in input text area

        # Create translator instance
        try:
            translator = self._create_translator_instance(engine)
        except Exception as e:
            self.handle_error(str(e), "Single File Translation") # Pass context
            return

        # Create worker thread
        self.worker = TranslationWorker(translator, text, target_lang, "single_file") # Filename not really used in single mode
        self.worker.finished.connect(self.handle_translation_result)
        self.worker.error.connect(self.handle_error)
        self.worker.start()


    def start_batch_translation(self, engine, target_lang, file_paths):
        self._prepare_ui_for_translation(is_batch=True)
        self.save_btn.setEnabled(False) # Disable single save in batch mode
        self.input_text.clear() # Clear input text area at start of batch
        self.output_text.clear() # Clear output text area at start of batch
        self.current_file_label.setVisible(True) # Show current file label

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

            self.current_file_label.setText(f"Processing File: {filename}") # Update current file label
            self.file_progress_label.setText(f"File Progress: Translating {filename} ({self.current_file_index + 1}/{self.total_files})")
            self.file_progress_label.setVisible(True)
            self.file_progress_bar.setVisible(True)
            self.file_progress_bar.setRange(0, 0) # Indeterminate for individual file

            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    text = f.read()
                    self.input_text.setPlainText(text) # Display original text in input text area

                # Find the corresponding QListWidgetItem and store it for status update
                list_item = self.file_list_display.item(self.current_file_index)
                list_item.setData(Qt.UserRole, filename) # Store filename for easy lookup if needed


            except Exception as e:
                self.handle_batch_error(f"Failed to open file {filename}:\n{str(e)}", filename) # Specific error for batch file open
                return # Stop processing this file and move to next

            # Create translator instance
            try:
                translator = self._create_translator_instance(engine)
            except Exception as e:
                self.handle_batch_error(str(e), filename) # Specific error for batch translator init
                return # Stop processing this file and move to next


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
        self.overall_progress_bar.setVisible(False) # Hide overall progress in single mode initially
        self.overall_progress_label.setVisible(False)
        self.file_progress_bar.setVisible(True) # File progress is visible even for single file
        self.file_progress_label.setVisible(True)
        self.file_progress_bar.setRange(0, 0) # Indeterminate progress
        self.set_buttons_enabled(False)
        self.output_text.clear()


    def handle_translation_result(self, result, warning, filename): # filename is now passed even for single file.
        self.file_progress_bar.setVisible(False)
        self.file_progress_label.setVisible(False)
        self.set_buttons_enabled(True)
        self.output_text.setPlainText(result)
        if warning:
            QMessageBox.warning(self, "Warning", warning)


    def handle_batch_translation_result(self, result, warning, filename):
        # Update status in file list
        list_item = self.file_list_display.item(self.current_file_index)
        if list_item:
            original_filename = list_item.text() # Get original filename
            list_item.setText(f"{original_filename} - Translated") # Append status

        self.output_text.setPlainText(result) # Display translated text in output text area
        success, save_path = self.save_translated_file(result, filename)
        self.file_progress_bar.setVisible(False)
        self.file_progress_label.setVisible(False)
        # Removed success dialog for batch translation as requested
        if warning:
            QMessageBox.warning(self, "Warning", warning)

        self.current_file_index += 1
        self.overall_progress_bar.setValue(self.current_file_index)
        engine = self.engine_combo.currentText()
        target_lang = self.lang_combo.currentText().lower()
        self.translate_next_file_in_batch(engine, target_lang) # Process next file


    def handle_error(self, error_msg, filename): # filename is now passed to error handler
        self.file_progress_bar.setVisible(False)
        self.file_progress_label.setVisible(False)
        self.set_buttons_enabled(True)
        QMessageBox.critical(self, "Error", f"Error during translation:\n{error_msg}")


    def handle_batch_error(self, error_msg, filename):
        # Update status in file list to show error
        list_item = self.file_list_display.item(self.current_file_index)
        if list_item:
            original_filename = list_item.text()
            list_item.setText(f"{original_filename} - Error") # Append error status

        self.file_progress_bar.setVisible(False)
        self.file_progress_label.setVisible(False)
        QMessageBox.critical(self, "Batch Translation Error", f"Error processing file {filename}:\n{error_msg}")
        self.current_file_index += 1
        self.overall_progress_bar.setValue(self.current_file_index)
        engine = self.engine_combo.currentText()
        target_lang = self.lang_combo.currentText().lower()
        self.translate_next_file_in_batch(engine, target_lang) # Continue to next file even on error



    def batch_translation_finished(self):
        self.overall_progress_bar.setVisible(False)
        self.overall_progress_label.setVisible(False)
        self.file_progress_bar.setVisible(False)
        self.file_progress_label.setVisible(False)
        self.current_file_label.setVisible(False) # Hide current file label after batch finish
        # self.file_list_display.clear() # Keep file list to show status
        # self.file_list_display.setVisible(False) # Keep file list visible to show status
        self.file_list_label.setVisible(False) # Hide file list label after batch finish
        self.set_buttons_enabled(True)
        QMessageBox.information(self, "Batch Translation", "Batch translation completed!") # Keep batch complete message
        self.file_paths = [] # Clear file paths after batch completion
        self.total_files = 0
        self.current_file_index = 0


    def set_buttons_enabled(self, enabled):
        for btn in [self.open_btn, self.translate_btn, self.settings_btn, self.engine_combo, self.lang_combo]:
            btn.setEnabled(enabled)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TranslationApp()
    window.show()
    sys.exit(app.exec())