import os,sys, sqlite3

from PyQt6 import uic
from PyQt6.QtSql import QSqlDatabase, QSqlTableModel
from PyQt6.QtWidgets import QApplication, QMainWindow

# _DEBUG = True
_DEBUG = False

class databaseViewer(QMainWindow):
    def __init__(self, data={'dbname':'sqlite.db', 'table':'igf'}):
        super(databaseViewer,self).__init__()
        uic.loadUi(os.path.join(os.path.dirname(__file__), 'viewer.ui'), self)

        con = sqlite3.connect('sqlite.db')
        cursor = con.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        for table in cursor.fetchall():
            self.comboBox.addItem(table[0])

        self.comboBox.currentIndexChanged.connect(self.selectionCombobox)

        db = QSqlDatabase("QSQLITE")
        db.setDatabaseName(os.path.join('.', data['dbname']))
        if not db.open():
            print("Could not open the database")

        self.model = QSqlTableModel(db=db)

        self.tableView.setModel(self.model)

        self.model.setTable(data['table'])
        self.model.select()
        self.tableView.resizeColumnsToContents()

    def selectionCombobox(self, index):
        item = self.comboBox.currentText()
        self.model.setTable(item)
        self.model.select()
        self.tableView.resizeColumnsToContents()

app = QApplication(sys.argv)
window = databaseViewer()
if _DEBUG:
    window.show()
    app.exec()