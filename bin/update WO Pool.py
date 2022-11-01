import sys, os, sqlite3, configparser, glob, qdarktheme, re
from pathlib import PurePath
from sqlite3 import Error
from PyQt6 import QtWidgets, uic
from datetime import datetime

# _DEBUG = True
_DEBUG = False

DATABASE = "sqlite.db"

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
        self.buttonBox.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        QtWidgets.QApplication.processEvents()

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
                dt = datetime.now().strftime("%Y%m%d%H%M%S")
                os.rename(os.path.join('.', DATABASE), os.path.join('.',f'sqlite{dt}.db'))
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

        conn = self.create_connection(DATABASE)

        if conn is not None:
            self.create_table(conn, sql_create_igf_table)
            self.create_table(conn, sql_create_pdf_table)
            self.create_table(conn, sql_create_thumbs_table)
            self.create_table(conn, sql_create_info_table)

            """
            IGF
            """
            igf_list = []
            for n, fn in enumerate(glob.glob(pathIGF + '/**/*.pda', recursive=True)):
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
            res = self.insertIGF(conn, igf_list)
            if(res):
                if(res.rowcount > 0):
                    self.plainTextEdit.appendPlainText(f'{res.rowcount} PDA files toegevoegd.')
            self.insertInfo(conn, (datetime.now().isoformat(), backup_folder))
            self.progressBar.setValue(33)
            QtWidgets.QApplication.processEvents()

            """
            Create dictionary of PDF files
            """
            pdf_list = []
            for n, fn in enumerate(glob.glob(pathPDF + '/**/*.pdf', recursive=True)):
                pp = PurePath(fn)
                filename = pp.name
                found = re.search(r'\d{7,}', filename)
                if(found is not None):
                    basename = pp.stem
                    mm = found.group()
                    path = pp.parent
                    pdf_list.append((filename, basename, str(mm), str(path)))
            res = self.insertPDF(conn, pdf_list)
            if(res):
                if(res.rowcount > 0):
                    self.plainTextEdit.appendPlainText(f'{res.rowcount} PDF files toegevoegd.')
            self.progressBar.setValue(66)
            QtWidgets.QApplication.processEvents()
            
            """
            Create dictionary of thumbnails
            """
            thumbnail_list = []
            for n, fn in enumerate(glob.glob(pathThumbnail + '/**/*.jpg', recursive=True)):
                pp = PurePath(fn)
                filename = pp.name
                found = re.search(r'\d{7,}', filename)
                if(found is not None):
                    basename = pp.stem
                    mm = found.group()
                    path = pp.parent
                    thumbnail_list.append((filename, basename, str(mm), str(path)))
            res = self.insertThumbs(conn, thumbnail_list)
            if(res):
                if(res.rowcount > 0):
                    self.plainTextEdit.appendPlainText(f'{res.rowcount} thumbnails toegevoegd.')
            
            self.progressBar.setValue(100)
            self.plainTextEdit.appendPlainText('Ready')
        else:
            self.plainTextEdit.appendPlainText('Error connection database. Try again.')
        
        self.buttonBox.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setEnabled(True)

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
            return True
        except Error as e:
            print(e)
            return False

    def insertIGF(self, conn, values):
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

    def insertPDF(self, conn, values):
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

    def insertThumbs(self, conn, values):
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

    def insertInfo(self, conn, values):
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

app = QtWidgets.QApplication(sys.argv)
app.setStyleSheet(qdarktheme.load_stylesheet(border="sharp"))
window = winUpdate()
"""===============
For developing
==============="""
if _DEBUG:
    window.show()
    app.exec()