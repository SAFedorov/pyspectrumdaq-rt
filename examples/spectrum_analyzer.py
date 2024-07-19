# Starts the real-time spectrum analyzer app with a given configuration. 

from datetime import datetime
import os

from pyqtgraph import mkQApp
from pyqtgraph import QtGui

from pyspectrumdaq import RtsWindow

if __name__ == "__main__":
    # if __name__ == '__main__' is required because the app starts more 
    # than one process.

    app = mkQApp()
    # The same as app = QtGui.QApplication(*args) with some parameters 
    # pre-set by pyqtgraph.

    today = datetime.now()
    data_dir = os.path.join("Z:", os.sep, "data", 
                            f"{today.year}-{today.month}-{today.day}")

    mw = RtsWindow(acq_settings={"channels": (1,)}, basedir=data_dir)
    mw.show()

    QtGui.QApplication.instance().exec_()