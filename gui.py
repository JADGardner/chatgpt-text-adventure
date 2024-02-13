import sys
import os
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QTextEdit, QPushButton, QHBoxLayout, QDialog, QLineEdit
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt, pyqtSignal

def get_path(filename):
    if getattr(sys, 'frozen', False):  # Check if running as executable
        datadir = os.path.dirname(sys.executable)
    else:
        datadir = os.path.dirname(__file__)  # Running as a normal script
    return os.path.join(datadir, filename)

class IntroDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Enter OpenAI Key")
        self.setModal(True)
        self.api_key = None

        layout = QVBoxLayout(self)

        self.key_input = QLineEdit(self)
        self.key_input.setPlaceholderText("Enter your OpenAI API Key here")
        layout.addWidget(self.key_input)

        submit_button = QPushButton("Submit", self)
        submit_button.clicked.connect(self.submit_key)
        layout.addWidget(submit_button)

    def submit_key(self):
        self.api_key = self.key_input.text()
        self.accept()


class GUI(QWidget):
    update_text_signal = pyqtSignal(str, bool)  # Signal to update text box
    update_button_single_signal = pyqtSignal(int, str, bool)  # Signal to update a single button
    update_image_signal = pyqtSignal(QPixmap)  # Signal to update the image
    button_clicked_signal = pyqtSignal(int)  # Signal to indicate a button has been clicked
    close_signal = pyqtSignal()  # Signal to close the GUI

    def __init__(self, parent, width, height, title=""):
        super().__init__()
        self.parent = parent
        self.width = width
        self.height = height
        self.initUI(title)
        self.update_text_signal.connect(self.update_text_box)  # Connect signal to slot
        self.update_button_single_signal.connect(self.update_button_single)
        self.update_image_signal.connect(self.update_image)

        for button in self.buttons:
            button.clicked.connect(self.button_clicked)
    
    def closeEvent(self, event):
        self.close_signal.emit()
        super(GUI, self).closeEvent(event)

    def initUI(self, title):
        self.setGeometry(0, 0, self.width, self.height)
        self.setWindowTitle(title)

        # Main vertical layout
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # Horizontal layout for centering the image
        image_layout = QHBoxLayout()
        image_layout.addStretch()  # Add stretch before the image

        # Load and display the image
        self.imageLabel = QLabel(self)
        pixmap = QPixmap(get_path('holder.png'))
        self.imageLabel.setPixmap(pixmap.scaled(400, 400, Qt.KeepAspectRatio))
        image_layout.addWidget(self.imageLabel)

        image_layout.addStretch()  # Add stretch after the image
        main_layout.addLayout(image_layout)  # Add the image layout to the main layout

        # Text display area
        self.textEdit = QTextEdit(self)
        self.textEdit.setReadOnly(True)
        self.textEdit.setFixedHeight(300)
        main_layout.addWidget(self.textEdit)

        # Buttons with text wrap
        button_height = 100  # Set the desired height for the buttons
        self.buttons = []
        for i in range(3):
            button = QPushButton(self)
            label = QLabel(f"")
            label.setAlignment(Qt.AlignCenter)
            label.setWordWrap(True)
            layout = QVBoxLayout()
            layout.addWidget(label)
            button.setLayout(layout)
            button.setFixedHeight(button_height)  # Set the fixed height
            button.clicked.connect(self.button_clicked)
            main_layout.addWidget(button)
            button.setProperty("button_index", i)  # Assign an identifier to the button
            self.buttons.append(button)

        # Exit button
        exit_button = QPushButton('Restart', self)
        exit_button.clicked.connect(self.close)
        main_layout.addWidget(exit_button)

        self.show()

    def button_clicked(self):
        sender = self.sender()
        button_index = sender.property("button_index")
        self.button_clicked_signal.emit(button_index)

    def update_text_box(self, text, clear_text):
        if clear_text:
            # we are clearing the text box first
            self.textEdit.clear()
        self.textEdit.insertPlainText(text)  # Directly insert text without new line
    
    def update_button_single(self, button_index, text, clear_text):
        if clear_text:
            # we are clearing the button first
            self.buttons[button_index].layout().itemAt(0).widget().setText("")
        # append the text to the button
        current_label = self.buttons[button_index].layout().itemAt(0).widget()
        new_text = current_label.text() + text  # Append new text to existing text
        current_label.setText(new_text)

    def update_image(self, pixmap):
        self.imageLabel.setPixmap(pixmap.scaled(400, 400, Qt.KeepAspectRatio))