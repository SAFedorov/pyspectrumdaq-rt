from typing import Union

import os
import json

import numpy as np
import h5py

from pyqtgraph.Qt import QtCore
from pyqtgraph.Qt import QtGui
from pyqtgraph.Qt import QtWidgets 

class TraceList:
    """A class that manages a combination of a list widget, pyqtgraph plot
    and directory edit field to color traces, edit their names,
    hide/show them from the display and save their data in txt or hdf5 files.

    Traces are dictionaries that have 1D arrays of data under "x" and "y" keys 
    plus optional metadata entries under other keys. Metadata can be any 
    serializable objects, possibly nested.
    """

    def __init__(self, listWidget, plotItem, dirLineEdit) -> None:
        """Inits a list and links interactive controls to it.

        Args:
            listWidget (QListWidget): 
                A widget that displays the items in the list with their names.
            plotItem (plotItem):
                A pyqtgraph plot in which the traces are to be displayed.
            dirLineEdit (QLineEdit):
                An edit field to input the base directory.
        """
        super().__init__()
        self.listWidget = listWidget
        self.plotItem = plotItem
        self.dirLineEdit = dirLineEdit

        self.unsaved_item_color = (252, 165, 82)  # rgb
        self.saved_item_color = (0, 0, 0)  # rgb

        self._list = []

        self._trace_colors = ((0, 0, 0),  # black
                              (42, 75, 186),  # dark blue
                              (66, 127, 245),  # blue
                              (111, 181, 207),  # greenish-blue
                              (142, 0, 73),  # dark red
                              (158, 146, 238),  # violet
                              (106, 16, 166))  # dark violet
        self._color_ind = 0
        # The colors are not implemented as a geneerator because 
        # the index is decremented sometimes.
        

    def __len__(self):
        return len(self._list)

    def __getitem__(self, ind):
        return self._list[ind]["xytrace"]

    def append(self, xytrace: dict, name: str = '') -> None:
        """Adds a new item to the list, creates and entry in the list widget
        and displays it in the plot.

        Args:
            tr: 
                The dictionary to be appended to the list. Has to contain two
                arrays of the same size under the 'x' and 'y' keys.
            name: 
                The name of the trace.
        """

        # Creates a new list item.
        item = QtWidgets.QListWidgetItem(name)
        item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled
                      | QtCore.Qt.ItemIsEditable)
        # Flags:
        # ItemIsEnabled - enables user interaction
        # ItemIsEditable - allows to edit the text

        item.setForeground(QtGui.QColor(*self.unsaved_item_color))

        # Plots the new trace in the axes.
        nc = len(self._trace_colors)
        line_color = self._trace_colors[self._color_ind % nc]
        line = self.plotItem.plot(xytrace["x"], xytrace["y"], pen=line_color)

        self._color_ind += 1

        # Adds an icon to the trace that has the same color as the line.
        item.setIcon(QtGui.QIcon(_draw_item_icon(line_color)))

        # The item is added to the list only after we are done with editing it 
        # to prevent useless firings of itemChanged signal by the list widget.
        self.listWidget.addItem(item)

        self._list.append({"xytrace": xytrace,
                           "item": item, 
                           "line": line, 
                           "line_color": line_color,
                           "is_visible": True})


    def toggle_visibility(self) -> None:
        """Sets or toggles the visibility of the current trace in the plot."""

        d = self._selected_item()
        if not d:
            return

        line = d["line"]
        v = not d["is_visible"]

        # Creates an item icon.
        if v:
            color = d["line_color"]
            icon = _draw_item_icon(color)
        else:
            color = (255, 255, 255, 0)  # rgba transparent
            icon = _draw_item_icon(color, border=False)

        line.setPen(color)

        self.listWidget.blockSignals(True)
        d["item"].setIcon(QtGui.QIcon(icon))
        self.listWidget.blockSignals(False)

        d["is_visible"] = v

    def remove_selected(self) -> None:
        """Removes the currently selected element from the list and deletes 
        the corresponding curve from the plot.
        """

        d = self._selected_item()
        if not d:
            return

        self.plotItem.removeItem(d["line"])

        # Removes the item from the widget. 
        r = self.listWidget.row(d["item"])
        self.listWidget.takeItem(r)

        self._list.pop(r)

        if len(self._list) == 0:
            # If the list contains no more items, the color counter is reset.
            self._color_ind = 0
        elif r == len(self._list):
            # If the latest item was removed, the color counter is decremented.
            self._color_ind -= 1

    def save_selected(self, fmt: str = "txt"):
        """Saves the currently selected trace."""

        d = self._selected_item()
        if not d:
            return

        file_name = d["item"].text()
        dir_name = self.dirLineEdit.text()

        full_name = os.path.join(dir_name, file_name + "." + fmt)

        if os.path.isfile(full_name):

            # Asks the user if the file should be overwritten.
            resp = QtWidgets.QMessageBox.question(
                self.listWidget,
                "Overwrite dialog",
                "File already exists. Would you like to overwrite?",
                buttons=(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No),
                defaultButton=QtWidgets.QMessageBox.No
            )

            if resp == QtWidgets.QMessageBox.Yes:
                print(f"Overwriting file {full_name}")
            else:
                print(f"Keeping the exiting file {full_name}.")
                return
        elif not os.path.exists(dir_name):
            os.makedirs(dir_name)  # Creates the base directory.

        tr = d["xytrace"].copy()  # TODO: come up with a better way of doing it
        x = tr.pop("x")
        y = tr.pop("y")

        if fmt == "txt":
            # Saves the x and y values in two-column format and prints 
            # the rest as a header.

            arr = np.vstack([x, y]).T
            np.savetxt(full_name, arr, header=json.dumps(tr, indent=2))
        elif fmt == "hdf5":
            # Saves in hdf5 format. Only the y values are actually written, 
            # while the x values are assumed to be regularly spaced between
            # xmax and xmin.

            with h5py.File(full_name, "w") as f:
                f["ydata"] = y
                f["ydata"].attrs["xmin"] = np.min(x)
                f["ydata"].attrs["xmax"] = np.max(x)

                mdt = _flatten_dict(tr)
                for k in mdt:
                    f["ydata"].attrs[k] = mdt[k]
        else:
            raise ValueError(f"Unsupported file format {fmt}.")

        # Marks the list item as saved
        d["item"].setForeground(QtGui.QColor(*self.saved_item_color))
    
    def _selected_item(self) -> Union[dict, None]:
        """Returns the currently selected item."""

        ind = self.listWidget.selectedIndexes()

        if ind:
            r = ind[0].row()
            return self._list[r]
        else:
            return None


def _draw_item_icon(color: Union[str, tuple], border=True) -> QtGui.QPixmap:
    """Creates a pixel map circle with transparent background.

    Args:
        color: 
            The circle fill color, defined by a hex code string (e.g. #ff7f0e), 
            an RGB tuple with three elements or an RGBA tuple with four 
            elements. Tuple elements take values between 0 and 255.
    """

    a = 30  # icon size in pixels

    pixmap = QtGui.QPixmap(a, a)
    pixmap.fill(QtGui.QColor(255, 255, 255, 0))  # rgba transparent white

    if border:
        border_qcolor = QtGui.QColor(0, 0, 0)
    else:
        border_qcolor = QtGui.QColor(255, 255, 255, 0)

    painter = QtGui.QPainter(pixmap)
    painter.setPen(QtGui.QColor(border_qcolor))

    if type(color) is str:
        # The color is given as a hex code string.
        qtcolor = QtGui.QColor(color)
    else:
        # Otherwise the color must be given as a tupe.
        qtcolor = QtGui.QColor(*color)

    painter.setBrush(qtcolor)

    r = int(a/2)  # radius
    painter.drawEllipse(int(r/2), int(r/2), r, r)

    return pixmap


def _flatten_dict(d: dict, prefix='', sep=':') -> dict:
    """Flattens a nested dictionary to single level, for example

    {'a': 1, 'b': {'c': 4, 'd': 5}} 
    
    is transformed to 
    
    {'a': 1, 'b/c': 4, 'b/d':5}

    """
    out = {}
    for k, v in d.items():
        if prefix:
            new_key = prefix + sep + k
        else:
            new_key = k

        if type(v) == dict:
            out.update(_flatten_dict(v, new_key, sep))
        else:
            out[new_key] = v
    return out
