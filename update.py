from random import random
import sys, os, sqlite3, configparser, glob, qdarktheme, re, uuid, time
from pathlib import PurePath
from sqlite3 import Error
from PyQt6 import QtWidgets, uic
from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, pyqtSlot, QTimer, QThreadPool, QAbstractListModel
from datetime import datetime

# _DEBUG = True
_DEBUG = False

DATABASE = "sqlite.db"

STATUS_WAITING = "waiting"
STATUS_RUNNING = "running"
STATUS_ERROR = "error"
STATUS_COMPLETE = "complete"

DEFAULT_STATE = {"progress": 0, "status": STATUS_WAITING}

def create_connection(db_file):
    conn = None
    try:
        conn = sqlite3.connect(db_file) # , check_same_thread=False
        return conn
    except Error as e:
        print(e)
    return conn

def create_table(conn, create_table_sql):
    try:
        c = conn.cursor()
        c.execute(create_table_sql)
        return True
    except Error as e:
        print(e)
        return False

def insertIGF(conn, values):
    try:
        sql = """
            INSERT INTO
                igf
                (
                    filename,
                    basename,
                    mm,
                    path,
                    cat,
                    modified
                )
            VALUES
                (?, ?, ?, ?, ?, ?)
        """
        cur = conn.cursor()
        cur.executemany(sql, values)
        conn.commit()
        return cur
    except Error as e:
        print(e)
        return False

def insertPDF(conn, values):
    try:
        sql = """
            INSERT INTO
                pdf
                (
                    filename,
                    basename,
                    mm,
                    path
                )
            VALUES
                (?, ?, ?, ?)
        """
        cur = conn.cursor()
        cur.executemany(sql, values)
        conn.commit()
        return cur
    except Error as e:
        print(e)
        return False

def insertThumbs(conn, values):
    try:
        sql = """
            INSERT INTO
                thumbs
                (
                    filename,
                    basename,
                    mm,
                    path
                )
            VALUES
                (?, ?, ?, ?)
        """
        cur = conn.cursor()
        cur.executemany(sql, values)
        conn.commit()
        return cur
    except Error as e:
        print(e)
        return False

def insertInfo(conn, values):
    try:
        sql = """
            INSERT INTO
                info
                (
                    last_updated,
                    folder
                )
            VALUES
                (?, ?)
        """
        cur = conn.cursor()
        cur.execute(sql, values)
        conn.commit()
        return cur
    except Error as e:
        print(e)
        return False

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
        conn = create_connection(DATABASE)
        type, path = self.args
        result = []

        try:
            self.signals.result.emit(self.job_id, [f'Bezig met ophalen van {type}'])
            self.signals.status.emit(self.job_id, STATUS_RUNNING)

            """
            Create dictionary of PDF files
            """
            if type == 'PDF':
                pdf_list = []
                for n, fn in enumerate(glob.glob(path + '/**/*.pdf', recursive=True)):
                    pp = PurePath(fn)
                    filename = pp.name
                    found = re.search(r'\d{7,}', filename)
                    if(found is not None):
                        basename = pp.stem
                        mm = found.group()
                        path = pp.parent
                        pdf_list.append((filename, basename, str(mm), str(path)))
                res = insertPDF(conn, pdf_list)
                if(res):
                    if(res.rowcount > 0):
                        result.append(f'{res.rowcount} PDF files toegevoegd.')
                        pass
                winUpdate().progressBar.setValue(33)

            """
            Create dictionary of thumbnails
            """
            if type == 'Thumbnail':
                thumbnail_list = []
                for n, fn in enumerate(glob.glob(path + '/**/*.jpg', recursive=True)):
                    pp = PurePath(fn)
                    filename = pp.name
                    found = re.search(r'\d{7,}', filename)
                    if(found is not None):
                        basename = pp.stem
                        mm = found.group()
                        path = pp.parent
                        thumbnail_list.append((filename, basename, str(mm), str(path)))
                res = insertThumbs(conn, thumbnail_list)
                if(res):
                    if(res.rowcount > 0):
                        result.append(f'{res.rowcount} thumbnails toegevoegd.')

            """
            IGF
            """
            if type == 'IGF':
                igf_list = []
                for n, fn in enumerate(glob.glob(path + '/**/*.pda', recursive=True)):
                    pp = PurePath(fn)
                    filename = pp.name
                    backup_folder = pp.parent.parent.parent.name
                    found = re.search(r'\d{7,}', filename)
                    if(found is not None):
                        basename = pp.stem
                        mm = found.group()
                        path = pp.parent
                        cat = pp.parent.name
                        try:
                            modified = datetime.fromtimestamp(os.path.getmtime(fn)).isoformat()
                        except OSError as e:
                            modified = None
                            print(e)
                        igf_list.append((filename, basename, str(mm), str(path), cat, modified))
                res = insertIGF(conn, igf_list)
                if(res):
                    if(res.rowcount > 0):
                        result.append(f'{res.rowcount} PDA files toegevoegd.')
                insertInfo(conn, (datetime.now().isoformat(), backup_folder))

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


class winUpdate(QtWidgets.QMainWindow):

    def __init__(self):
        super(winUpdate,self).__init__()
        uic.loadUi(os.path.join(os.path.dirname(__file__), 'update.ui'), self)
        
        self.workers = WorkerManager()

        self.workers.status.connect(self.statusBar().showMessage)

        self.buttonBox.accepted.connect(self.accepted)
        self.buttonBox.rejected.connect(self.rejected)

        self.btnIGF.clicked.connect(lambda *args, type='IGF': self.browse(type))
        self.btnPDF.clicked.connect(lambda *args, type='PDF': self.browse(type))
        self.btnThumbnail.clicked.connect(lambda *args, type='Thumbnail': self.browse(type))

        try:
            config = configparser.ConfigParser()
            if os.path.exists(os.path.join('.', 'conf.ini')):
                config.read(os.path.join('.', 'conf.ini'))
                # print('Found')
                if config.has_option('DEFAULT','IGFBackupPath') == True:
                    self.leIGF.setText(config['DEFAULT']['IGFBackupPath'])
                if config.has_option('DEFAULT','PDFPath') == True:
                    self.lePDF.setText(config['DEFAULT']['PDFPath'])
                if config.has_option('DEFAULT','ThumbnailPath') == True:
                    self.leThumbnail.setText(config['DEFAULT']['ThumbnailPath'])
        except Exception as e:
            print('Error' , e)

    def browse(self, type):
        try:
            config = configparser.ConfigParser()
            if os.path.exists(os.path.join('.', 'conf.ini')):
                config.read(os.path.join('.', 'conf.ini'))

            match type:
                case 'IGF':
                    savedPath = config['DEFAULT']['IGFBackupPath'] if config.has_option('DEFAULT','IGFBackupPath') == True else 'C:/'
                case 'PDF':
                    savedPath = config['DEFAULT']['PDFPath'] if config.has_option('DEFAULT','PDFPath') == True else '//srv-w2012-cad/ME10_data$/data/pdf/code'
                case 'Thumbnail':
                    savedPath = config['DEFAULT']['ThumbnailPath'] if config.has_option('DEFAULT','ThumbnailPath') == True else '//srv-w2012-cad/ME10_data$/data/Thumbnail_3D/code'

            selectedPath = QtWidgets.QFileDialog.getExistingDirectory(self, 'Select Directory', savedPath)
                
            if selectedPath != '':
                match type:
                    case 'IGF':
                        self.leIGF.setText(selectedPath)
                        config['DEFAULT']['IGFBackupPath'] = selectedPath
                    case 'PDF':
                        self.lePDF.setText(selectedPath)
                        config['DEFAULT']['PDFPath'] = selectedPath
                    case 'Thumbnail':
                        self.leThumbnail.setText(selectedPath)
                        config['DEFAULT']['ThumbnailPath'] = selectedPath
                with open(os.path.join('.', 'conf.ini'), 'w') as configfile:
                    config.write(configfile)

        except Exception as e:
            print('Error' , e)

    def accepted(self):
        # self.buttonBox.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        
        workers = len(self.workers._workers)
        if workers > 0:
            return self.plainTextEdit.appendPlainText('Wacht tot de taken zijn voltooid voor je een nieuwe start.')

        pathIGF = self.leIGF.text()
        pathPDF = self.lePDF.text()
        pathThumbnail = self.leThumbnail.text()
        
        if pathIGF == '' or pathPDF == '' or pathThumbnail == '':
            return self.plainTextEdit.appendPlainText('Geen of niet alle paden zijn geselecteerd.')
        if os.path.isdir(pathIGF) == False:
            return self.plainTextEdit.appendPlainText(f'{PurePath(pathIGF).name}\nHet pad bestaat niet. Controleer het pad en probeer het opnieuw.')
        if os.path.isdir(pathPDF) == False:
            return self.plainTextEdit.appendPlainText(f'{PurePath(pathPDF).name}\nHet pad bestaat niet. Controleer het pad en probeer het opnieuw.')
        if os.path.isdir(pathThumbnail) == False:
            return self.plainTextEdit.appendPlainText(f'{PurePath(pathThumbnail).name}\nHet pad bestaat niet. Controleer het pad en probeer het opnieuw.')

        if os.path.isfile(os.path.join('.', DATABASE)):
            try:
                dt = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
                pp = PurePath(DATABASE)
                os.rename(os.path.join('.', DATABASE), os.path.join('.',f'{pp.stem}_{dt}{pp.suffix}'))
            except Exception as e:
                print(e)
                return self.plainTextEdit.appendPlainText('Kan database niet hernoemen.')

        sql_create_igf_table = """CREATE TABLE IF NOT EXISTS igf (
                                    id integer PRIMARY KEY,
                                    filename varchar(255) NOT NULL,
                                    basename varchar(255) NOT NULL,
                                    mm varchar(255) NOT NULL,
                                    path varchar(255) NOT NULL,
                                    cat varchar(255) NOT NULL,
                                    modified datetime
                                );"""

        sql_create_pdf_table = """CREATE TABLE IF NOT EXISTS pdf (
                                    id integer PRIMARY KEY,
                                    filename varchar(255) NOT NULL,
                                    basename varchar(255) NOT NULL,
                                    mm varchar(255) NOT NULL,
                                    path varchar(255) NOT NULL
                                );"""

        sql_create_thumbs_table = """CREATE TABLE IF NOT EXISTS thumbs (
                                        id integer PRIMARY KEY,
                                        filename varchar(255) NOT NULL,
                                        basename varchar(255) NOT NULL,
                                        mm varchar(255) NOT NULL,
                                        path varchar(255) NOT NULL
                                    );"""

        sql_create_info_table = """CREATE TABLE IF NOT EXISTS info (
                                        id integer PRIMARY KEY,
                                        last_updated DATETIME NOT NULL,
                                        folder varchar(255) NOT NULL
                                    );"""

        conn = create_connection(DATABASE)

        if conn is not None:
            create_table(conn, sql_create_igf_table)
            create_table(conn, sql_create_pdf_table)
            create_table(conn, sql_create_thumbs_table)
            create_table(conn, sql_create_info_table)
            
            w = Worker('IGF', pathIGF)
            w.signals.result.connect(self.display_result)
            w.signals.error.connect(self.display_result)
            self.workers.enqueue(w)
            w = Worker('PDF', pathPDF)
            w.signals.result.connect(self.display_result)
            w.signals.error.connect(self.display_result)
            self.workers.enqueue(w)
            w = Worker('Thumbnail', pathThumbnail)
            w.signals.result.connect(self.display_result)
            w.signals.error.connect(self.display_result)
            self.workers.enqueue(w)
        else:
            return self.plainTextEdit.appendPlainText('Kan geen verbinding maken met de database.')

    def rejected(self):
        self.close()

    def start_worker(self):
        x = random.randint(0, 1000)
        y = random.randint(0, 1000)

        w = Worker(x, y)
        w.signals.result.connect(self.display_result)
        w.signals.error.connect(self.display_result)

        self.workers.enqueue(w)

    def display_result(self, job_id, data):
        # self.plainTextEdit.appendPlainText("WORKER %s: %s" % (job_id, data))
        self.plainTextEdit.appendPlainText(data[0])

    def closeEvent(self, event):
        workers = len(self.workers._workers)
        if workers == 0:
            event.accept()
        else:
            QtWidgets.QMessageBox.information(self, "Oops!", f"Er zijn nog {workers} taken bezig.\nWacht tot alle taken zijn voltooid.")
            event.ignore()

app = QtWidgets.QApplication(sys.argv)
app.setStyleSheet(qdarktheme.load_stylesheet(corner_shape="sharp"))
window = winUpdate()
"""===============
For developing
==============="""
if _DEBUG:
    window.show()
    app.exec()