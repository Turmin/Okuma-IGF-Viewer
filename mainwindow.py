import qdarktheme, sys, os, sqlite3, configparser, uuid
from sqlite3 import Error
from pathlib import Path
from datetime import datetime
from PyQt6 import QtWidgets, uic
from PyQt6.QtCore import Qt, QEvent, QCoreApplication, QObject, pyqtSignal, QRunnable, pyqtSlot, QTimer, QThreadPool, QAbstractListModel
from PyQt6.QtGui import QPixmap, QCursor, QIcon, QFont
from update import winUpdate

"""
https://www.pythonguis.com/faq/file-image-browser-app-with-thumbnails/
https://stackoverflow.com/questions/43949947/how-can-i-update-a-table-using-a-qthread
"""

_DEBUG = False

VERSION = 'Version 2.0.0.1 (Nov 2022)'

DATABASE = 'sqlite.db'
NUMBER_OF_COLUMNS = 10
CELLSIZE_HEIGHT = 200
CELLSIZE_WIDTH = 170
CELLMARGIN = 8
try:
    config = configparser.ConfigParser()
    if os.path.exists(os.path.join('.', 'conf.ini')):
        config.read(os.path.join('.', 'conf.ini'))
        if config.has_option('SETTINGS','NumberOfColumns') == True:
            NUMBER_OF_COLUMNS = int(config['SETTINGS']['NumberOfColumns'])
        if config.has_option('SETTINGS','CellSize_Height') == True:
            CELLSIZE_HEIGHT = int(config['SETTINGS']['CellSize_Height'])
        if config.has_option('SETTINGS','CellSize_Width') == True:
            CELLSIZE_WIDTH = int(config['SETTINGS']['CellSize_Width'])
        if config.has_option('SETTINGS','CellMargin') == True:
            CELLMARGIN = int(config['SETTINGS']['CellMargin'])
        else:
            config['SETTINGS'] = {}
            config['SETTINGS']['NumberOfColumns'] = str(NUMBER_OF_COLUMNS)
            config['SETTINGS']['CellSize_Height'] = str(CELLSIZE_HEIGHT)
            config['SETTINGS']['CellSize_Width'] = str(CELLSIZE_WIDTH)
            config['SETTINGS']['CellMargin'] = str(CELLMARGIN)
            with open(os.path.join('.', 'conf.ini'), 'w') as configfile:
                config.write(configfile)

except Exception as e:
    print(e)

def create_connection(db):
    conn = None
    try:
        if(os.path.isfile(os.path.join('.', db))):
            conn = sqlite3.connect(db)
    except Error as e:
        print(e)
    return conn

STATUS_WAITING = "waiting"
STATUS_RUNNING = "running"
STATUS_ERROR = "error"
STATUS_COMPLETE = "complete"

DEFAULT_STATE = {"progress": 0, "status": STATUS_WAITING}

class WorkerSignals(QObject):
    """
    Defines the signals available from a running worker thread.

    Supported signals are:

    finished
        No data
    
    error
        `tuple` (exctype, value, traceback.format_exc() )
    
    result
        `object` data returned from processing, anything

    progress
        `int` indicating % progress 

    """

    error = pyqtSignal(str, str)
    result = pyqtSignal(str, object)

    finished = pyqtSignal(str)
    progress = pyqtSignal(str, int)
    status = pyqtSignal(str, str)


class Worker(QRunnable):
    """
    Worker thread

    Inherits from QRunnable to handle worker thread setup, signals and wrap-up.

    :param args: Arguments to pass for the worker
    :param kwargs: Keywords to pass for the worker

    """

    def __init__(self, *args, **kwargs):
        super().__init__()

        # Store constructor arguments (re-used for processing).
        self.signals = WorkerSignals()

        # Give this job a unique ID.
        self.job_id = str(uuid.uuid4())

        # The arguments for the worker
        self.args = args
        self.kwargs = kwargs

        self.signals.status.emit(self.job_id, STATUS_WAITING)

    @pyqtSlot()
    def run(self):
        """
        Initialize the runner function with passed args, kwargs.
        """
        result = []

        try:
            conn = create_connection(DATABASE)

            cat, = self.args
            self.signals.status.emit(self.job_id, STATUS_RUNNING)

            cur = conn.cursor()
            cur.execute(f"""
                SELECT
                    igf.basename,
                    igf.path,
                    pdf.filename,
                    pdf.path,
                    thumbs.filename,
                    thumbs.path
                FROM
                    igf
                LEFT JOIN
                    pdf
                ON
                    igf.mm = pdf.mm
                LEFT JOIN
                    thumbs
                ON
                    igf.mm = thumbs.mm
                WHERE
                    igf.cat = '{cat}'
                GROUP BY
                    igf.mm
            """)

            result.append(cur.fetchall())

            self.signals.progress.emit(self.job_id, 1)
        except Exception as e:
            print(e)
            # We swallow the error and continue.
            self.signals.error.emit(self.job_id, str(e))
            self.signals.status.emit(self.job_id, STATUS_ERROR)

        else:
            self.signals.result.emit(self.job_id, result)
            self.signals.status.emit(self.job_id, STATUS_COMPLETE)

        self.signals.finished.emit(self.job_id)

class WorkerManager(QAbstractListModel):
    """
    Manager to handle our worker queues and state.
    Also functions as a Qt data model for a view
    displaying progress for each worker.

    """

    _workers = {}
    _state = {}

    status = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        # Create a threadpool for our workers.
        self.threadpool = QThreadPool()
        # self.threadpool.setMaxThreadCount(1)
        self.max_threads = self.threadpool.maxThreadCount()
        # print("Multithreading with maximum %d threads" % self.max_threads)

        self.status_timer = QTimer()
        self.status_timer.setInterval(100)
        self.status_timer.timeout.connect(self.notify_status)
        self.status_timer.start()

    def notify_status(self):
        n_workers = len(self._workers)
        running = min(n_workers, self.max_threads)
        waiting = max(0, n_workers - self.max_threads)
        self.status.emit(
            "{} running, {} waiting, {} threads".format(
                running, waiting, self.max_threads
            )
        )

    def enqueue(self, worker):
        """
        Enqueue a worker to run (at some point) by passing it to the QThreadPool.
        """
        worker.signals.error.connect(self.receive_error)
        worker.signals.status.connect(self.receive_status)
        worker.signals.progress.connect(self.receive_progress)
        worker.signals.finished.connect(self.done)

        self.threadpool.start(worker)
        self._workers[worker.job_id] = worker

        # Set default status to waiting, 0 progress.
        self._state[worker.job_id] = DEFAULT_STATE.copy()

        self.layoutChanged.emit()

    def receive_status(self, job_id, status):
        self._state[job_id]["status"] = status
        self.layoutChanged.emit()

    def receive_progress(self, job_id, progress):
        self._state[job_id]["progress"] = progress
        self.layoutChanged.emit()

    def receive_error(self, job_id, message):
        print(job_id, message)

    def done(self, job_id):
        """
        Task/worker complete. Remove it from the active workers
        dictionary. We leave it in worker_state, as this is used to
        to display past/complete workers too.
        """
        del self._workers[job_id]
        self.layoutChanged.emit()

    def cleanup(self):
        """
        Remove any complete/failed workers from worker_state.
        """
        for job_id, s in list(self._state.items()):
            if s["status"] in (STATUS_COMPLETE, STATUS_ERROR):
                del self._state[job_id]
        self.layoutChanged.emit()

class MainWindow(QtWidgets.QMainWindow):

    def __init__(self):
        super(MainWindow,self).__init__()
        uic.loadUi(os.path.join(os.path.dirname(__file__), 'mainwindow.ui'), self)

        self.workers = WorkerManager()

        self.tableWidget.horizontalHeader().setDefaultSectionSize(CELLSIZE_WIDTH)
        self.tableWidget.verticalHeader().setDefaultSectionSize(CELLSIZE_HEIGHT)
        self.tableWidget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tableWidget.customContextMenuRequested.connect(self.contextMenu)
        self.tableWidget.setStyleSheet("QTableWidget::item{background:transparent}")

        self.actionUpdate.triggered.connect(self.openWinUpdate)
        self.actionDatabase_Viewer.triggered.connect(self.openDatabaseViewer)
        self.actionExit.triggered.connect(self.close)
        self.actionAbout.triggered.connect(self.about)

        self.listWidget.itemClicked.connect(self.categoryItem)

        try:
            conn = create_connection(DATABASE)
            if conn:
                self.showCategories(conn)
                info = self.getInfo(conn)
                dt = datetime.fromisoformat(info[0]).strftime('%d-%m-%Y')
                self.labelStatusBar = QtWidgets.QLabel(f'Laatst bijgewerkt {dt}')
                self.statusbar.addPermanentWidget(self.labelStatusBar)
            else:
                self.statusbar.showMessage('Kan geen verbinding maken.')
        except Exception as e:
            self.statusbar.showMessage('Er is een fout opgetreden.')
            print(e)

    def display_result(self, job_id, data):
        self.tableWidget.setColumnCount(NUMBER_OF_COLUMNS)
        self.tableWidget.setRowCount(0)
        curColumn = 0

        for row in data[0]:
            igf_basename = row[0]
            igf_path = row[1]
            pdf_filename = row[2]
            pdf_path = row[3]
            thumbs_filename = row[4]
            thumbs_path = row[5]

            if curColumn == 0 or curColumn >= NUMBER_OF_COLUMNS:
                self.tableWidget.insertRow(self.tableWidget.rowCount())
                curColumn = 0
            curRow = self.tableWidget.rowCount()-1
            image = f'{thumbs_path}\{thumbs_filename}' if thumbs_path is not None and thumbs_filename is not None else None
            pdf = f'{pdf_path}\{pdf_filename}' if pdf_path is not None and pdf_filename is not None else None
            self.tableWidget.setCellWidget(curRow, curColumn, cellWidgets({'thumbnail':image,'igf_basename':igf_basename,'pdf':pdf}))
            curColumn += 1

    def showCategories(self, conn):
        cur = conn.cursor()
        cur.execute("SELECT cat FROM igf GROUP BY cat")
        for row in cur.fetchall():
            item = QtWidgets.QListWidgetItem(str(row[0]))
            self.listWidget.addItem(item)

    def getInfo(self, conn):
        cur = conn.cursor()
        cur.execute("SELECT last_updated, folder FROM info")
        return cur.fetchone()

    def categoryItem(self, item):
        if item:
            conn = create_connection(DATABASE)
            if conn:
                cat = item.text()
                self.statusbar.showMessage(cat)
                w = Worker(cat)
                w.signals.result.connect(self.display_result)
                w.signals.error.connect(self.display_result)
                self.workers.enqueue(w)
                conn.close()
            else:
                self.statusbar.showMessage('Kan geen verbinding maken.')

    def openDatabaseViewer(self):        
        from viewer import databaseViewer
        self.winDatabaseViewer = databaseViewer({'dbname':DATABASE, 'table':'igf'})
        self.winDatabaseViewer.show()

    def contextMenu(self, point):
        """
        Context menu
        """
        try:            
            menu = QtWidgets.QMenu()
            # menu.setStyleSheet("QMenu{padding:4px 0;}QMenu::item{padding:6px 10px;}")
            cursor = QCursor()

            selectedIndexes = self.tableWidget.selectedIndexes()
            curRow = self.tableWidget.currentRow()
            curCol = self.tableWidget.currentColumn()

            item = menu.addAction('Item')
            item.triggered.connect(self.item)
            item.setIcon(QIcon(os.path.join(os.path.dirname(__file__),"icons/.png")))
            item.setEnabled(False)

            item = menu.addAction('Item')
            item.triggered.connect(self.item)
            item.setIcon(QIcon(os.path.join(os.path.dirname(__file__),"icons/.png")))
            item.setEnabled(False)

            menu.addSeparator()

            item = menu.addAction('Item')
            item.triggered.connect(self.item)
            item.setIcon(QIcon(os.path.join(os.path.dirname(__file__),"icons/.png")))
            item.setEnabled(False)

            item = menu.addAction('Item')
            item.triggered.connect(self.item)
            item.setIcon(QIcon(os.path.join(os.path.dirname(__file__),"icons/.png")))
            # item.setEnabled(True) if QtWidgets.QApplication.clipboard().text() and (curCol > 4 and curCol != 6) else item.setEnabled(False)
            item.setEnabled(False)

            menu.addSeparator()

            item = menu.addAction('Item')
            item.triggered.connect(lambda: self.item(selectedIndexes))
            item.setIcon(QIcon(os.path.join(os.path.dirname(__file__),"icons/.png")))
            item.setEnabled(False)

            menu.exec(cursor.pos())
        except Exception as e:
            print(e)

    def item(self, selectedIndexes = None):
        print(selectedIndexes)

    def cellClicked(self, modelIndex):
        print(modelIndex.row(),modelIndex.column())

    # def resizeEvent(self, event):
    #     print("Window has been resized")
    #     QtWidgets.QMainWindow.resizeEvent(self, event)

    def closeEvent(self, event):
        print('Window closed')
        for window in QtWidgets.QApplication.topLevelWidgets():
            window.close()
        QCoreApplication.quit()
        QCoreApplication.exit(0)
        event.accept()

    def dialog(self, msg):
        dlg = QtWidgets.QMessageBox(self)
        dlg.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        dlg.setWindowTitle("Oops!")
        dlg.setText(msg)
        button = dlg.exec()
        
    def openWinUpdate(self):
        self.winUpdate = winUpdate()
        self.winUpdate.show()

    def about(self):
        QtWidgets.QMessageBox.about(self, 'About', f"""
            <p>Okuma IGF Viewer
            <br>{VERSION}</p>
            <p>
            © Michael van Druten
            <br><a style='color:lightblue' href='mailto:info@turmin.com?Subject=Okuma%20IGF%20Viewer'>info@turmin.com</a>
            </p>
            """
        )

class cellWidgets(QtWidgets.QWidget):

    def __init__(self, data=None, parent=None):
        super(cellWidgets,self).__init__(parent)

        # if data['pdf'] is not None or data['thumbnail'] is not None:
        layout = QtWidgets.QVBoxLayout()

        layout.setContentsMargins(CELLMARGIN, CELLMARGIN, CELLMARGIN, CELLMARGIN)
        layout.setSpacing(0)
        labelImage = QtWidgets.QLabel()
        labelImage.setScaledContents(True)
        image = data['thumbnail'] if data['thumbnail'] is not None else os.path.join(os.path.dirname(__file__), 'images\\no-image.png')
        im = QPixmap(image).scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
        labelImage.setPixmap(im)
        labelImage.mousePressEvent = lambda event, image=image: self.imageClicked(event, image)
        layout.addWidget(labelImage)

        """
        text_input = QtWidgets.QTextEdit()
        text_input.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Preferred)
        text_input.setFixedHeight(45)
        text_input.setFont(QFont('Arial',10))
        text_input.textChanged.connect(lambda *args, data=data: self.saveText(data))
        layout.addWidget(text_input)
        """

        button = QtWidgets.QPushButton(data['igf_basename'])
        button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Preferred)
        button.setFixedHeight(25)
        button.setFont(QFont('Arial',10))
        button.setStyleSheet("QPushButton{background-color:#004875;color:#fff}")
        if data['pdf'] is not None:
            button.setIcon(QIcon(os.path.join(os.path.dirname(__file__), 'icons/icons8-pdf-48.png')))
            button.clicked.connect(lambda *args, pdf=data['pdf']: self.buttonClicked(pdf))
            button.setStyleSheet("QPushButton{background-color:#004875;color:#fff}" "QPushButton::hover{background-color:#14243c}")
            button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        layout.addWidget(button)

        self.setLayout(layout)

    def imageClicked(self, event, image):
        try:
            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    os.startfile(image)
        except Exception as e:
            print(e)

    def buttonClicked(self, pdf):
        try:
            os.startfile(Path(pdf))
        except Exception as e:
            print(e)

    def saveText(self, data):
        try:
            print(self.sender().toPlainText())
            image = data['image']
        except Exception as e:
            print(e)

app = QtWidgets.QApplication(sys.argv)
# app.setStyleSheet(qdarktheme.load_stylesheet(corner_shape="sharp"))
app.setStyleSheet(qdarktheme.load_stylesheet(corner_shape="sharp"))
window = MainWindow()
window.showMaximized()
app.exec()