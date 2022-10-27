import sys, os, sqlite3, time, configparser, glob, qdarktheme, re
from pathlib import Path, PurePath
from sqlite3 import Error
from PyQt6 import QtWidgets, uic
from PyQt6.QtGui import *
from PyQt6.QtCore import QObject, pyqtSignal, QRunnable
from datetime import datetime

_DEBUG = True
# _DEBUG = False


class WorkerSignals(QObject):
    '''
    Defines the signals available from a running worker thread.

    Supported signals are:

    finished
        No data

    error
        tuple (exctype, value, traceback.format_exc() )

    result
        object data returned from processing, anything

    progress
        int indicating % progress

    '''
    finished = pyqtSignal()
    error = pyqtSignal(tuple)
    result = pyqtSignal(object)
    progress = pyqtSignal(int)


class Worker(QRunnable):
    '''
    Worker thread

    Inherits from QRunnable to handler worker thread setup, signals and wrap-up.

    :param callback: The function callback to run on this worker thread. Supplied args and
                     kwargs will be passed through to the runner.
    :type callback: function
    :param args: Arguments to pass to the callback function
    :param kwargs: Keywords to pass to the callback function

    '''

    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()

        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

        # Add the callback to our kwargs
        self.kwargs['progress_callback'] = self.signals.progress

    @pyqtSlot()
    def run(self):
        '''
        Initialise the runner function with passed args, kwargs.
        '''

        # Retrieve args/kwargs here; and fire processing using them
        try:
            result = self.fn(*self.args, **self.kwargs)
        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done


class winUpdate(QtWidgets.QMainWindow):

    def __init__(self):
        super(winUpdate,self).__init__()
        uic.loadUi(os.path.join(os.path.dirname(__file__), 'update.ui'), self)

        self.buttonBox.accepted.connect(self.accepted)
        self.buttonBox.rejected.connect(self.rejected)

        self.btnIGF.clicked.connect(lambda *args, type='IGF': self.browse(type))
        self.btnPDF.clicked.connect(lambda *args, type='PDF': self.browse(type))
        self.btnThumbnail.clicked.connect(lambda *args, type='Thumbnail': self.browse(type))

        try:
            config = configparser.ConfigParser()
            if os.path.exists(os.path.join(os.path.dirname(__file__), 'conf.ini')):
                config.read(os.path.join(os.path.dirname(__file__), 'conf.ini'))
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
            if os.path.exists(os.path.join(os.path.dirname(__file__), 'conf.ini')):
                config.read(os.path.join(os.path.dirname(__file__), 'conf.ini'))

            match type:
                case 'IGF':
                    savedPath = config['DEFAULT']['IGFBackupPath'] if config.has_option('DEFAULT','IGFBackupPath') == True else 'C:/'
                case 'PDF':
                    savedPath = config['DEFAULT']['PDFPath'] if config.has_option('DEFAULT','PDFPath') == True else '//srv-w2012-cad/ME10_data$/data/code_tekeningen'
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
                with open(os.path.join(os.path.dirname(__file__), 'conf.ini'), 'w') as configfile:
                    config.write(configfile)

        except Exception as e:
            print('Error' , e)

    def accepted(self):
        self.lblStatus.setText('')
        pathIGF = self.leIGF.text()
        pathPDF = self.lePDF.text()
        pathThumbnail = self.leThumbnail.text()
        self.lblStatus.setStyleSheet("QLabel { color : red; }")
        
        if pathIGF == '' or pathPDF == '' or pathThumbnail == '':
            return self.lblStatus.setText('Geen of niet alle paden zijn geselecteerd.')
        if os.path.isdir(pathIGF) == False:
            return self.lblStatus.setText(f'{PurePath(pathIGF).name}\nHet pad bestaat niet. Controleer het pad en probeer het opnieuw.')
        if os.path.isdir(pathPDF) == False:
            return self.lblStatus.setText(f'{PurePath(pathPDF).name}\nHet pad bestaat niet. Controleer het pad en probeer het opnieuw.')
        if os.path.isdir(pathThumbnail) == False:
            return self.lblStatus.setText(f'{PurePath(pathThumbnail).name}\nHet pad bestaat niet. Controleer het pad en probeer het opnieuw.')

        self.lblStatus.setStyleSheet("QLabel { color : white; }")

        database = r"sqlite.db"
        # os.path.isfile(os.path.join(os.path.dirname(__file__), database))
        # dt = datetime.now().strftime("%Y%m%d%H%M%S")
        # os.rename(os.path.join(os.path.dirname(__file__), database), f'sqlite{dt}.db')

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

        sql_create_matches_table = """CREATE TABLE IF NOT EXISTS matches (
                                        id integer PRIMARY KEY,
                                        id_igf integer NOT NULL,
                                        id_thumbs integer NOT NULL,
                                        id_pdf integer NOT NULL
                                    );"""

        sql_create_cats_table = """CREATE TABLE IF NOT EXISTS cats (
                                    id integer PRIMARY KEY,
                                    cat varchar(255) NOT NULL
                                );"""

        conn = self.create_connection(database)

        if conn is not None:
            self.create_table(conn, sql_create_igf_table)
            self.create_table(conn, sql_create_pdf_table)
            self.create_table(conn, sql_create_thumbs_table)
            # self.create_table(conn, sql_create_matches_table)
            # self.create_table(conn, sql_create_cats_table)


            """
            Create dictionary of PDF files
            """
            pdf_list = []
            for n, fn in enumerate(glob.glob(pathPDF + '/**/*.pdf', recursive=True)):
                pp = PurePath(fn)
                filename = pp.name
                found = re.search(r'\d{7,}', filename)
                if(found is not None):
                    pdf_list.append({'filename':pp.name, 'basename':pp.stem, 'mm':found.group(), 'path':str(pp.parent)})

            """
            Create dictionary of thumbnails
            """
            thumbnail_list = []
            for n, fn in enumerate(glob.glob(pathThumbnail + '/**/*.jpg', recursive=True)):
                pp = PurePath(fn)
                filename = pp.name
                found = re.search(r'\d{7,}', filename)
                if(found is not None):
                    thumbnail_list.append({'filename':pp.name, 'basename':pp.stem, 'mm':found.group(), 'path':str(pp.parent)})

            """
            IGF
            """
            igf_list = []
            for n, fn in enumerate(glob.glob(pathIGF + '/**/*.pda', recursive=True)):
                pp = PurePath(fn)
                filename = pp.name
                found = re.search(r'\d{7,}', filename)
                if(found is not None):
                    basename = pp.stem
                    mm = found.group()
                    type = '.PDA'
                    path = pp.parent
                    cat = pp.parent.name
                    try:
                        modified = datetime.fromtimestamp(os.path.getmtime(fn)).isoformat()
                    except OSError as e:
                        modified = None
                        print(e)
                    # print(f'FN {filename}\nBN {basename}\nP {path}\nC {cat}\nM {modified}')
                    igf_list.append((filename, basename, mm, type, str(path), cat, modified))

                    res = next((i for i in pdf_list if i["mm"] == mm), False)
                    if(res):
                        # self.insertPDF(conn, (filename, basename, mm, path))
                        print('match')
                    res = next((i for i in thumbnail_list if i["mm"] == mm), False)
                    if(res):
                        print('match')
                        # self.insertThumbs(conn, (filename, basename, mm, path))


            # self.insertIGF(conn, igf_list)

            self.progressBar.setValue(100)
            self.lblStatus.setText('Ready')
        else:
            self.lblStatus.setStyleSheet("QLabel { color : red; }")
            return self.lblStatus.setText('Error connection database. Try again.')

    def rejected(self):
        self.close()

    def create_connection(self, db_file):
        conn = None
        try:
            conn = sqlite3.connect(db_file)
            return conn
        except Error as e:
            print(e)
        return conn

    def create_table(self, conn, create_table_sql):
        try:
            c = conn.cursor()
            c.execute(create_table_sql)
        except Error as e:
            print(e)

    def insertIGF(self, conn, values):
        try:
            sql = """
                INSERT INTO
                    igf
                    (filename,basename,mm,type,path,cat,modified)
                VALUES
                    (?,?,?,?,?,?,?)
            """
            cur = conn.cursor()
            # cur.execute(sql, values)
            cur.executemany(sql, values)
            conn.commit()
            return cur.lastrowid
        except Error as e:
            print(e)

    def insertPDF(self, conn, values):
        try:
            sql = """
                INSERT INTO
                    pdf
                    (filename,basename,mm,path)
                VALUES
                    (?,?,?,?)
            """
            cur = conn.cursor()
            cur.execute(sql, values)
            conn.commit()
            return cur.lastrowid
        except Error as e:
            print(e)

    def insertThumbs(self, conn, values):
        try:
            sql = f"""
                INSERT INTO
                    thumbs
                    (filename,basename,mm,path)
                VALUES
                    (?,?,?,?)
            """
            cur = conn.cursor()
            cur.execute(sql, values)
            conn.commit()
            return cur.lastrowid
        except Error as e:
            print(e)

    def insertMatches(self, conn, values):
        try:
            sql = f"""
                INSERT INTO
                    matches
                    (id_igf,id_thumbs,id_pdf)
                VALUES
                    (?,?,?)
            """
            cur = conn.cursor()
            # cur.execute(sql, values)
            cur.executemany(sql, values)
            conn.commit()
            return cur.lastrowid
        except Error as e:
            print(e)

app = QtWidgets.QApplication(sys.argv)
app.setStyleSheet(qdarktheme.load_stylesheet(border="sharp"))
window = winUpdate()
"""===============
For developing
==============="""
if _DEBUG:
    window.show()
    app.exec()