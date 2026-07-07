from PyQt5.QtWidgets import QMessageBox

def show_question_dialog(parent, title, text):
    """Показывает диалог с вопросом и кнопками Да/Нет (на русском)"""
    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle(title)
    msg_box.setText(text)
    msg_box.setIcon(QMessageBox.Question)
    btn_yes = msg_box.addButton("Да", QMessageBox.YesRole)
    btn_no = msg_box.addButton("Нет", QMessageBox.NoRole)
    msg_box.setDefaultButton(btn_yes)
    msg_box.exec_()
    return msg_box.clickedButton() == btn_yes