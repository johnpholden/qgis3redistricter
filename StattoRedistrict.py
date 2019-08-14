# -*- coding: utf-8 -*-
"""
/***************************************************************************
 StattoRedistrict
                                 A QGIS plugin
 Easily create political districts of equal population
                              -------------------
        begin                : 2018-05-21
        git sha              : $Format:%H$
        copyright            : (C) 2018-19 by John Holden, Statto Software LLC
        email                : redistricting@stattosoftware.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from __future__ import print_function
from __future__ import absolute_import
from builtins import str
from builtins import range
from builtins import object
from qgis.PyQt.QtCore import QSettings, QTranslator, qVersion, QCoreApplication, Qt, QFileInfo, QVariant
from qgis.PyQt.QtWidgets import QAction, QDialogButtonBox, QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.core import QgsProject, QgsMessageLog, QgsSymbol, QgsVectorLayer, QgsCategorizedSymbolRenderer, QgsSimpleFillSymbolLayer, QgsRendererCategory, QgsSpatialIndex, QgsField, QgsExpression, QgsFeatureRequest
from qgis.gui import QgsMapCanvas, QgsMapToolEmitPoint, QgsMapTool, QgsMapToolIdentifyFeature
#from qgis.analysis import QgsGeometryAnalyzer
from random import randrange
#from . import ogr2ogr
# Initialize Qt resources from file resources.py
from . import resources
import csv

# Import the code for the DockWidget
from .StattoRedistrict_dockwidget import StattoRedistrictDockWidget
from .StattoRedistrict_attrdockwidget import StattoRedistrictAttrDockWidget
from .StattoRedistrict_dlgparameter import StattoRedistrictDlgParameter
from .StattoRedistrict_dlgtoolbox import StattoRedistrictDlgToolbox
from .StattoRedistrict_dlgelectorates import StattoRedistrictDlgElectorates
import os.path

dataFieldList = []
locked = {}
districtId = {}
districtName = {}
distPop = {}

class DataField(object):
        name = None
        type = 0
        total_sum = 0
        field_sum = []
        def __init__(self, values):
                self.name = values[0]
                if values[1] == 'Sum' or values[1] == 1:
                        self.type = 1
                elif values[1] == '% of Dist. Pop' or values[1] == 2:
                        self.type = 2
                elif values[1] == '% of Total Pop' or values[1] == 3:
                        self.type = 3
                elif values[1] == 'Population' or values[1] == 99:
                        self.type = 99
                else:
                        self.type = 4
                self.field_sum = []
                dataFieldList.append(self)

class StattoRedistrict(object):
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgisInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface

#        QgsMapTool.__init(self, self.iface.mapCanvas())
        self.canvas = self.iface.mapCanvas()
        self.canvas.setMouseTracking(True)
        

        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)

        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'StattoRedistrict_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Statto Software Redistricter')
        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'StattoRedistrict')
        self.toolbar.setObjectName(u'StattoRedistrict')

        #print "** INITIALIZING StattoRedistrict"

        # variables to initialise
        self.pluginIsActive = False
        self.dockwidget = None                #variable for the main dock
        self.attrdockwidget = None                #variable for the attribute table dock
        self.dlgparameters = None                #variable for the parameters dialog
        self.dlgtoolbox = None                #variable for the toolbox dialog
        self.dlgelectorates = None        #variable for the electorates dialog
        self.featIdentTool = None                #make sure we can use the identify tool in the code



        self.districts = None                #number of districts in the tool
        self.activedistrict = '1'                #which district is active. We use string literals
        self.activeLayer = None                #which layer is active - which layer we're reapportioning
        self.popfield = None                #the population field in the database
        self.distfield = None                #the district field in the database
        self.geofield = None
        self.totalpop = 0                #the total population
        self.targetpop = 0                #the target population
        self.targetpoppct = 0                #target population percentage tolerance
        self.targetpoplower = 0                #target pop lower bound
        self.targetpophigher = 0                #target pop upper bound
        self.undoAttr = {}

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('StattoRedistrict', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon("icon.png")
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action


    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/StattoRedistricter/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Statto Software Redistricter'),
            callback=self.run,
            parent=self.iface.mainWindow())

    #--------------------------------------------------------------------------

    def onClosePlugin(self):
        """Cleanup necessary items here when plugin dockwidget is closed"""

        #print "** CLOSING StattoRedistrict"

        # disconnects
        self.attrdockwidget.closingPlugin.disconnect(self.onClosePlugin)        
        self.dockwidget.closingPlugin.disconnect(self.onClosePlugin)

        # remove this statement if dockwidget is to remain
        # for reuse if plugin is reopened
        # Commented next statement since it causes QGIS crashe
        # when closing the docked window:
        # self.dockwidget = None

        self.pluginIsActive = False


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""

        #print "** UNLOAD StattoRedistrict"

        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Statto Software Redistricter'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar

    #--------------------------------------------------------------------------

    def run(self):
        """Run method that loads and starts the plugin"""

        if not self.pluginIsActive:
            self.pluginIsActive = True

            self.dockwidget = None                #variable for the main dock
            self.attrdockwidget = None                #variable for the attribute table dock
            self.dlgparameters = None                #variable for the parameters dialog
            self.dlgtoolbox = None                #variable for the toolbox dialog
            self.dlgelectorates = None        #variable for the electorates dialog
            self.featIdentTool = None                #make sure we can use the identify tool in the code



            self.districts = None                #number of districts in the tool
            self.activedistrict = '1'                #which district is active. We use string literals
            self.activeLayer = None                #which layer is active - which layer we're reapportioning
            self.popfield = None                #the population field in the database
            self.distfield = None                #the district field in the database
            self.geofield = None
            self.totalpop = 0                #the total population
            self.targetpop = 0                #the target population
            self.targetpoppct = 0                #target population percentage tolerance
            self.targetpoplower = 0                #target pop lower bound
            self.targetpophigher = 0                #target pop upper bound
            self.undoAttr = {}


            #print "** STARTING StattoRedistrict"

            # dockwidget may not exist if:
            #    first run of plugin
            #    removed on close (see self.onClosePlugin method)
            if self.dockwidget == None:
                # Create the dockwidget (after translation) and keep reference
                self.dockwidget = StattoRedistrictDockWidget()

            if self.attrdockwidget == None:
                self.attrdockwidget = StattoRedistrictAttrDockWidget()

            if self.dlgparameters == None:
                self.dlgparameters = StattoRedistrictDlgParameter()

            if self.dlgtoolbox == None:
                self.dlgtoolbox = StattoRedistrictDlgToolbox()

            if self.dlgelectorates == None:
                self.dlgelectorates = StattoRedistrictDlgElectorates()

            # connect to provide cleanup on closing of dockwidget
            self.dockwidget.closingPlugin.connect(self.onClosePlugin)

            #provide other gui options
            self.dockwidget.btnParameters.clicked.connect(self.openParametersDialog)
            self.dockwidget.btnUpdate.clicked.connect(self.updateAttributes)
            self.dockwidget.btnEraser.clicked.connect(self.setEraser)
            self.dockwidget.btnSelect.clicked.connect(self.updateSelectedElectorate)
#            self.dockwidget.btnCompactness.clicked.connect(self.showCompactness)
            self.dockwidget.btnToolbox.clicked.connect(self.openToolbox)
#            self.dockwidget.btnToolbox.clicked.connect(self.enclaveRemover)
            self.dockwidget.sliderDistricts.valueChanged.connect(self.updateDistrict)
            self.dockwidget.btnActiveDistrictMinus.clicked.connect(self.updateDecreaseDistrictIncrement)
            self.dockwidget.btnActiveDistrictPlus.clicked.connect(self.updateIncreaseDistrictIncrement)
            self.dockwidget.btnUndo.clicked.connect(self.undoLast)
            self.dockwidget.btnPreview.clicked.connect(self.previewSelection)
            self.dockwidget.btnGeoSelect.clicked.connect(self.selectByGeography)
            self.dockwidget.cmbGeoField.currentIndexChanged.connect(self.updateGeographyColumn)

            self.attrdockwidget.tblPop.itemClicked.connect(self.updateLockedFields)

            self.dlgparameters.cmbActiveLayer.currentIndexChanged.connect(self.updateFields)

            self.dlgparameters.boxButton.button(QDialogButtonBox.Ok).clicked.connect(self.saveParameters)
            self.dlgparameters.btnAddDataField.clicked.connect(self.addDataField)
            self.dlgparameters.btnRemoveDataField.clicked.connect(self.removeDataField)
            self.dlgparameters.btnLoadParameters.clicked.connect(self.loadParameters)

            self.dlgtoolbox.btnExportToCsv.clicked.connect(self.exportToCsv)
            self.dlgtoolbox.btnRename.clicked.connect(self.renameElectorates)

            self.dlgelectorates.boxButton.button(QDialogButtonBox.Ok).clicked.connect(self.updateElectorates)

            # show the dockwidget
            # TODO: fix to allow choice of dock location
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dockwidget)
            self.dockwidget.show()

            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.attrdockwidget)
            self.attrdockwidget.show()

    def canvasReleaseEvent(self, event):
        """Deprecated"""
        QgsMessageLog.logMessage("released!")
        with edit(self.activeLayer):
                selection = self.activeLayer.selectedFeatures()
                for feature in selection:
                        feature[self.distfield] = self.activedistrict

    def updateAttributes(self):
        """Updates the attributes when the Update Selected Polygons feature is clicked"""
        global locked
        self.undoAttr = {}
        self.dockwidget.lblPreview.setText('')
        QgsMessageLog.logMessage("released!")
        if locked[districtName[self.activedistrict]] == 0:
            selection = self.activeLayer.selectedFeatures()
            field_id = self.activeLayer.fields().indexFromName(self.distfield)
            self.activeLayer.startEditing()
            for feature in selection:
    #                try:
                            QgsMessageLog.logMessage(format(locked))
                            QgsMessageLog.logMessage(str(districtId[str(feature[self.distfield])]))
                            if locked[str(districtId[str(feature[self.distfield])])] == 0:
                                    self.undoAttr[feature.id()] = feature[self.distfield]
                                    self.updateFeatureValue(feature, districtName[self.activedistrict])
    #                except:
    #                        self.updateFeatureValue(feature)
    #               QgsMessageLog.logMessage(str(feature.id) + " changed to: " + str(self.activedistrict) + " on " + str(field_id))
            self.activeLayer.commitChanges()
        self.activeLayer.removeSelection()
        self.updateTable()
        self.dockwidget.btnUndo.setEnabled(True)

    def previewSelection(self):
        prevpop = 0
        prevpoplock = 0
        newprevpop = 0
        strActiveDistPop = ''
        if self.activedistrict > 0:
            curselpop = distPop[self.activedistrict]
        selection = self.activeLayer.selectedFeatures()
        for feature in selection:
            field_id = self.activeLayer.fields().indexFromName(self.distfield)
            prevpop = prevpop + feature[self.popfield]
            if str(feature[self.distfield]) != str(districtName[self.activedistrict]):
                prevpoplock = prevpoplock+ feature[self.popfield]
                if locked[str(districtId[str(feature[self.distfield])])] == 0:
                    newprevpop = newprevpop + feature[self.popfield]
        if self.activedistrict > 0:
            strActiveDistPop = ', in district: ' + str(prevpop - prevpoplock) + ', active district +' + str(newprevpop) + ' (' + str(distPop[self.activedistrict]) + '->' + str(distPop[self.activedistrict] + newprevpop) + ')'
        self.dockwidget.lblPreview.setText('in selection:' + str(prevpop) + strActiveDistPop)

    def undoLast(self):
        self.activeLayer.startEditing()
        for feature, value in self.undoAttr.items():
            self.updateFeatureValue(self.activeLayer.getFeature(feature), value)
        self.activeLayer.commitChanges()
        self.undoAttr = {}
        self.updateTable()
        self.dockwidget.btnUndo.setEnabled(False)

    def updateFeatureValue(self, feature, change_to):
#        QgsMessageLog.logMessage("updating feature value")
        global distPop
        field_id = self.activeLayer.fields().indexFromName(self.distfield)
        try:
                distPop[int(districtId[str(feature[self.distfield])])] = distPop[int(districtId[str(feature[self.distfield])])] - feature[self.popfield] # feature[self.popfield]
#                QgsMessageLog.logMessage("from: " + str(districtId[str(feature[self.distfield])]))
        except:
                try:
                        distPop[0] = distPop[0] - feature[self.popfield]
#                        QgsMessageLog.logMessage("from: zero")
                except:
                        errors = 1
#                        QgsMessageLog.logMessage(self.distfield + " failed on load")
        for d in dataFieldList:
                try:
                        d.field_sum[int(districtId[str(feature[self.distfield])])] = d.field_sum[int(districtId[str(feature[self.distfield])])] - feature[d.name]
                        d.total_sum = d.total_sum - feature[d.name]
                except:
                        QgsMessageLog.logMessage(feature[d.name])
                        d.field_sum[0] = d.field_sum[0] - feature[d.name]
                        d.total_sum = d.total_sum - feature[d.name]

#        QgsMessageLog.logMessage(str(districtId[str(feature[self.distfield])]))
        self.activeLayer.changeAttributeValue(feature.id(),field_id,change_to)
        newId = int(districtId[str(change_to)])

        try:
                distPop[newId] = distPop[newId] + feature[self.popfield]
                QgsMessageLog.logMessage("to: " + str(newId))
        except:
                try:
                        distPop[0] = distPop[0] + feature[self.popfield]
                        QgsMessageLog.logMessage("to: zer0")
                except:
                        errors = 1
#                        QgsMessageLog.logMessage(self.distfield + " failed on load")
        for d in dataFieldList:
                try:
                        d.field_sum[newId] = d.field_sum[newId] + feature[d.name]
                        d.total_sum = d.total_sum + feature[d.name]
                except:
                        d.field_sum[0] = d.field_sum[0] + feature[d.name]
                        d.total_sum = d.total_sum + feature[d.name]


    def openParametersDialog(self):
        self.dlgparameters.show()
#        old QGIS 2 code
#        layers = self.iface.legendInterface().layers()
        layers = [tree_layer.layer() for tree_layer in QgsProject.instance().layerTreeRoot().findLayers()]
        layer_list = []
        for layer in layers:
                layer_list.append(layer.name())
        self.dlgparameters.cmbActiveLayer.clear()
        self.dlgparameters.cmbActiveLayer.addItems(layer_list)
        if self.activeLayer != None:
                self.dlgparameters.cmbActiveLayer.setCurrentIndex(self.dlgparameters.cmbActiveLayer.findText(self.activeLayer.name()))
                self.setParameters()

    def openToolbox(self):
        self.dlgtoolbox.show()

    def saveParametersToFile(self):
#        try:
        f = open(self.activeLayer.source() + '.qgis.red','w')
        f.write(str(self.districts) + '\n')
        f.write(str(self.totalpop) + '\n')
        f.write(str(self.targetpop) + '\n')
        f.write(str(self.targetpoppct) + '\n')
        f.write(str(self.targetpoplower) + '\n')
        f.write(str(self.targetpophigher) + '\n')
        f.write(str(self.popfield) + '\n')
        f.write(str(self.distfield) + '\n')
        f.write(str(self.geofield) + '\n')
        counter = 0
        for d in dataFieldList:
                counter = counter + 1
        f.write(str(counter) + '\n')
        for d in dataFieldList:
                f.write(d.name + '\n')
                f.write(str(d.type) + '\n')

        f.write(str(len(districtName)) + '\n')
        for r in districtName:
                f.write(str(districtName[r]) + '\n')

    def updateLockedFields(self):
        QgsMessageLog.logMessage("Locking...")
        global locked
        locked = {}
        for r in range(0,self.districts+1):
                locked[districtName[r]] = 0
                if self.attrdockwidget.tblPop.item(r,1).checkState() == Qt.Checked:
#flock                        QgsMessageLog.logMessage((districtId[str(r)]) + " Locked")
                        locked[districtName[r]] = 1
        self.updateDistrict()

    def updateGeographyColumn(self):
        self.geofield = self.dockwidget.cmbGeoField.currentText()
        if self.activeLayer:
            self.saveParametersToFile()


    def loadParameters(self):
#        try:
#                layers = self.iface.legendInterface().layers()
                self.dlgparameters.chkStyleMap.setChecked(False)
                layers = [tree_layer.layer() for tree_layer in QgsProject.instance().layerTreeRoot().findLayers()]
                selectedLayerIndex = self.dlgparameters.cmbActiveLayer.currentIndex()
                selectedLayer = layers[selectedLayerIndex]
                f = open(selectedLayer.source() + '.qgis.red','r')
                self.districts = f.readline()
                self.districts = int(self.districts)
                self.totalpop = f.readline()
                self.totalpop = int(self.totalpop)
                self.targetpop = f.readline()
                self.targetpop = int(self.targetpop)
                self.targetpoppct = f.readline()
                self.targetpoppct = int(self.targetpoppct)
                self.targetpoplower = f.readline()
                self.targetpoplower = int(self.targetpoplower)
                self.targetpophigher = f.readline()
                self.targetpophigher = int(self.targetpophigher)
                self.popfield = f.readline().rstrip()
                self.distfield = f.readline().rstrip()
                self.geofield = f.readline().rstrip()
                fieldparams = int(f.readline())
                self.setParameters()
                del dataFieldList[:]
                for fp in range(0, fieldparams):
                        newfield = f.readline().rstrip()
                        newfieldtype = f.readline()
                        newfieldtype = int(newfieldtype)
                        df = DataField([newfield, newfieldtype])
                loader = f.readline()
                loader_int = int(loader)
                for fn in range(0, loader_int):
                        tmpDistrictName = f.readline().rstrip()
                        districtName[fn] = tmpDistrictName
                        if str(tmpDistrictName) not in districtId:
                                districtId[str(tmpDistrictName)] = str(fn)
#                self.updateDistricts()
#                self.updateTable()
                self.updateFieldTable()
#        except:
                #QgsMessageLog.logMessage("Save file failed to load")

    def setParameters(self):
        self.dlgparameters.inpDistricts.setValue(self.districts)
        self.dlgparameters.cmbPopField.setCurrentIndex((self.dlgparameters.cmbPopField.findText(self.popfield)))
        self.dlgparameters.cmbDistField.setCurrentIndex((self.dlgparameters.cmbDistField.findText(self.distfield)))
        self.dlgparameters.inpTolerance.setValue(self.targetpoppct)
        self.dockwidget.cmbGeoField.setCurrentIndex((self.dockwidget.cmbGeoField.findText(self.geofield)))
        self.updateFieldTable()

    def updateDistricts(self):
        try:
                if len(districtName) < self.districts:
                        counter = 1
                        for p in range(len(districtName),self.districts+1):
                                if str(p) not in districtName:
                                        districtName[p] = str(p)
                                else:
                                        while (str(self.districts+counter) in districtName) or (counter < 10000):
                                                counter = counter + 1
                                        districtName[p] = str(self.districts+counter)
                                if districtName[p] not in districtId:
                                        districtId[str(p)] = str(p)
                        QgsMessageLog.logMessage("Updating districts:")
                        QgsMessageLog.logMessage(format(districtName))
                        QgsMessageLog.logMessage(format(districtId))
        except:
                QgsMessageLog.logMessage("No map loaded")


    def saveParameters(self):
        self.updateDistricts()
        #layers = self.iface.legendInterface().layers()
        layers = [tree_layer.layer() for tree_layer in QgsProject.instance().layerTreeRoot().findLayers()]
        selectedLayerIndex = self.dlgparameters.cmbActiveLayer.currentIndex()
        selectedLayer = layers[selectedLayerIndex]
        self.activeLayer = selectedLayer
        self.districts = self.dlgparameters.inpDistricts.value()
        self.activedistrict = 1
        self.dockwidget.lblActiveDistrict.setText("Active District: " + str(self.activedistrict))
        self.dockwidget.sliderDistricts.setMinimum(1)
        self.dockwidget.sliderDistricts.setMaximum(self.districts)
        self.dockwidget.sliderDistricts.setValue(1)
        self.popfield = self.dlgparameters.cmbPopField.currentText()
        self.distfield = self.dlgparameters.cmbDistField.currentText()
#        self.geofield = self.dockwidget.cmbGeoField.currentText()
#        self.dispfield1 = self.dlgparameters.cmbDispField1.currentText()
 #       self.dispfield2 = self.dlgparameters.cmbDispField1.currentText()
        QgsMessageLog.logMessage("Popfield:" + str(self.popfield))
        self.totalpop = 0
        self.targetpop = 0
        for feature in self.activeLayer.getFeatures():
                self.totalpop = self.totalpop + int(feature[self.popfield])
        self.targetpop = int(self.totalpop / self.districts)
        self.targetpoppct = self.dlgparameters.inpTolerance.value()
        targetpoprem = int((self.targetpop / 100) * self.targetpoppct)
        self.targetpoplower = int(self.targetpop - targetpoprem)
        self.targetpophigher = int(self.targetpop + targetpoprem + 1)
        QgsMessageLog.logMessage("TargetPop:" + str(self.targetpop) + "(" + str(self.targetpoplower) + ", " + str(self.targetpophigher) + ")")
        QgsMessageLog.logMessage("Districts:" + str(self.districts))
        self.dockwidget.lblMainInfo.setText("Active Layer: " + self.activeLayer.name() + "\nActive District Field: " + self.distfield + "\nTarget Population: " + str(self.targetpop) + " (" + str(self.targetpoplower) + ", " + str(self.targetpophigher) + ")")
        self.attrdockwidget.tblPop.setRowCount(self.districts+1)
        numDataFields = 0
        for d in dataFieldList:
                numDataFields = numDataFields + 1
                self.attrdockwidget.tblPop.setHorizontalHeaderItem(4+numDataFields,QTableWidgetItem(d.name))
        self.attrdockwidget.tblPop.setColumnCount(5+numDataFields)
        for r in range(0,self.districts+1):
                chkBoxItem = QTableWidgetItem()
                chkBoxItem.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                chkBoxItem.setCheckState(Qt.Unchecked)       
                self.attrdockwidget.tblPop.setItem(r,1,chkBoxItem)
                self.attrdockwidget.tblPop.setVerticalHeaderItem(r, QTableWidgetItem(str(r)))
        self.attrdockwidget.tblPop.setHorizontalHeaderLabels(['#','Lock','Population','To Target','Dev%'])
        numDataFields = 0
        for d in dataFieldList:
                numDataFields = numDataFields + 1
                if d.type == 1:
                        self.attrdockwidget.tblPop.setHorizontalHeaderItem(4+numDataFields,QTableWidgetItem(d.name))
                else:
                        self.attrdockwidget.tblPop.setHorizontalHeaderItem(4+numDataFields,QTableWidgetItem(d.name + '%'))


        if len(districtName) == 0:
                self.initializeElectorates()

        try:
                self.saveParametersToFile()
                QgsMessageLog.logMessage("Parameters file saved!")
        except:
                QgsMessageLog.logMessage("Parameters file could not be saved")


        if self.dlgparameters.chkStyleMap.isChecked():
                self.styleMap()
                self.dlgparameters.chkStyleMap.setChecked(False)
        self.updateFieldValues()
        self.updateTable()
        self.updateLockedFields()
        self.updateDistricts()

    def styleMap(self):
                categories = []
                for cat in range(0,self.districts+1):
                        symbol = QgsSymbol.defaultSymbol(self.activeLayer.geometryType())
                        layer_style = {}
                        layer_style['color'] = '%d, %d, %d' % (randrange(0, 256), randrange(0, 256), randrange(0, 256))
                        layer_style['outline'] = '#000000'
                        symbol_layer = QgsSimpleFillSymbolLayer.create(layer_style)

                        # replace default symbol layer with the configured one
                        if symbol_layer is not None:
                                symbol.changeSymbolLayer(0, symbol_layer)

                        # create renderer object
                        if cat == 0:
                                category = QgsRendererCategory("", symbol, "")
                        else:
                                category = QgsRendererCategory(districtName[cat], symbol, str(districtName[cat]))
                        # entry for the list of category items
                        categories.append(category)
                renderer = QgsCategorizedSymbolRenderer(self.distfield, categories)
                # assign the created renderer to the layer
                if renderer is not None:
                        self.activeLayer.setRenderer(renderer)

                self.activeLayer.triggerRepaint()

    def updateDistrict(self):
        self.activedistrict = self.dockwidget.sliderDistricts.value()
        try:
            QgsMessageLog.logMessage("Active District:" + str(districtName[self.activedistrict]))
            lkd = ''
            if locked[districtName[self.activedistrict]] == 1:
                lkd = ' LOCKED!'
            self.dockwidget.lblActiveDistrict.setText("Active district: " + str(districtName[self.activedistrict]) + lkd)
        except:
            QgsMessageLog.logMessage("District failed to update")

    def updateDecreaseDistrictIncrement(self):
        try:
            self.activedistrict = int(self.activedistrict) - 1
            if self.activedistrict < 1:
                self.activedistrict = 1
            if self.activedistrict > self.districts:
                self.activedistrict = self.districts
            lkd = ''
            if locked[districtName[self.activedistrict]] == 1:
                lkd = ' LOCKED!'
            self.dockwidget.lblActiveDistrict.setText("Active district: " + str(districtName[self.activedistrict]) + lkd)
            self.dockwidget.sliderDistricts.setValue(int(self.activedistrict))
        except:
            self.updateDistrict()

    def updateIncreaseDistrictIncrement(self):
        try:
            self.activedistrict = int(self.activedistrict) + 1
            if self.activedistrict < 1:
                self.activedistrict = 1
            if self.activedistrict > self.districts:
                self.activedistrict = self.districts
            lkd = ''
            if locked[districtName[self.activedistrict]] == 1:
                lkd = ' LOCKED!'
            self.dockwidget.lblActiveDistrict.setText("Active district: " + str(districtName[self.activedistrict]) + lkd)
            self.dockwidget.sliderDistricts.setValue(int(self.activedistrict))
        except:
            self.updateDistrict()



    def updateFieldValues(self):
        global distPop
        QgsMessageLog.logMessage("Updating Field Values")
        QgsMessageLog.logMessage(format(districtName))
        QgsMessageLog.logMessage(format(districtId))
        numDataFields = 0
        for d in dataFieldList:
                del d.field_sum[:]
                for p in range(0,self.districts+1):
                        d.field_sum.append(p)
                        d.field_sum[p] = 0
                        d.total_sum = 0
                        numDataFields = numDataFields + 1
        for p in range(0,self.districts+1):
                distPop[p] = 0
        for feature in self.activeLayer.getFeatures():
                try:
                        distPop[int(districtId[str(feature[self.distfield])])] = distPop[int(districtId[str(feature[self.distfield])])] + feature[self.popfield]
                except:
                        try:
                                distPop[0] = distPop[0] + feature[self.popfield]
                        except:
                                errors = 1
#                        QgsMessageLog.logMessage(self.distfield + " failed on load")
                for d in dataFieldList:
                        try:
                                d.field_sum[int(districtId[str(feature[self.distfield])])] = d.field_sum[int(districtId[str(feature[self.distfield])])] + int(feature[d.name])
                                d.total_sum = d.total_sum + int(feature[d.name])
                        except:
                                d.field_sum[0] = d.field_sum[0] + int(feature[d.name])
                                d.total_sum = d.total_sum + int(feature[d.name])


    def updateTable(self):
        QgsMessageLog.logMessage("Updating Table")
        global distPop
        for p in range(0,self.districts+1):
                self.attrdockwidget.tblPop.setItem(p,0,QTableWidgetItem(str(districtName[p])))
                self.attrdockwidget.tblPop.setItem(p,2,QTableWidgetItem(str(distPop[p])))
                self.attrdockwidget.tblPop.setItem(p,3,QTableWidgetItem(str(self.targetpop - distPop[p])))
                self.attrdockwidget.tblPop.setItem(p,4,QTableWidgetItem(str(round((float(float(distPop[p]) / float(self.targetpop)) * 100)-100,2))+'%'))
                self.attrdockwidget.tblPop.item(p,0).setBackground(QColor(255,255,255))
                self.attrdockwidget.tblPop.item(p,1).setBackground(QColor(255,255,255))
                self.attrdockwidget.tblPop.item(p,2).setBackground(QColor(255,255,255))
                self.attrdockwidget.tblPop.item(p,3).setBackground(QColor(255,255,255))
                self.attrdockwidget.tblPop.item(p,4).setBackground(QColor(255,255,255))
                if distPop[p] >= self.targetpoplower and distPop[p] <= self.targetpophigher:
                        self.attrdockwidget.tblPop.item(p,0).setBackground(QColor(0,200,0))                        
                        self.attrdockwidget.tblPop.item(p,1).setBackground(QColor(0,200,0))
                        self.attrdockwidget.tblPop.item(p,2).setBackground(QColor(0,200,0))
                        self.attrdockwidget.tblPop.item(p,3).setBackground(QColor(0,200,0))    
                        self.attrdockwidget.tblPop.item(p,4).setBackground(QColor(0,200,0))    
                rowNum = 0
                for d in dataFieldList:
                        rowNum = rowNum + 1
                        if d.type == 1:
                                self.attrdockwidget.tblPop.setItem(p,4+rowNum,QTableWidgetItem(str(d.field_sum[p])))
                        elif d.type == 2:
                                if distPop[p] > 0:
#                                        QgsMessageLog.logMessage(str(d.field_sum[p]) + " " + str(distPop[p]))
                                        self.attrdockwidget.tblPop.setItem(p,4+rowNum,QTableWidgetItem(str(round(float(float(d.field_sum[p]) / float(distPop[p])) * 100,2))+'%'))
                                else:
                                        self.attrdockwidget.tblPop.setItem(p,4+rowNum,QTableWidgetItem('0.00%'))                
                        elif d.type == 3:
                                if self.totalpop > 0:
#                                        QgsMessageLog.logMessage(str(d.field_sum[p]) + " " + str(self.totalpop))
                                        self.attrdockwidget.tblPop.setItem(p,4+rowNum,QTableWidgetItem(str(round(float(float(d.field_sum[p]) / float(self.totalpop)) * 100,2))+'%'))
                                else:
                                        self.attrdockwidget.tblPop.setItem(p,4+rowNum,QTableWidgetItem('0.00%'))
                        elif d.type == 4:
                                if d.total_sum > 0:
#                                        QgsMessageLog.logMessage(str(d.field_sum[p]) + " " + str(d.total_sum))
                                        self.attrdockwidget.tblPop.setItem(p,4+rowNum,QTableWidgetItem(str(round(float(float(d.field_sum[p]) / float(d.total_sum)) * 100,2))+'%'))
                                else:
                                        self.attrdockwidget.tblPop.setItem(p,4+rowNum,QTableWidgetItem('0.00%'))

        self.attrdockwidget.tblPop.resizeColumnToContents(0)
        self.attrdockwidget.tblPop.resizeColumnToContents(1)
        self.attrdockwidget.tblPop.resizeColumnToContents(2)
        self.attrdockwidget.tblPop.resizeColumnToContents(3)
        self.attrdockwidget.tblPop.resizeColumnToContents(4)

    def addDataField(self):
        f = DataField([self.dlgparameters.cmbDataField.currentText(),self.dlgparameters.cmbDataType.currentText()])
        self.updateFieldTable()

    def removeDataField(self):
        indexes = self.dlgparameters.tblDataFields.selectionModel().selectedRows()
        counter = 0
        for f in dataFieldList:
                for g in indexes:
                        if counter == g.row():
                                dataFieldList.remove(f)
                counter = counter + 1
        self.updateFieldTable()

    def updateFieldTable(self):
        tblRows = 0
        for d in dataFieldList:
                tblRows = tblRows + 1
        self.dlgparameters.tblDataFields.setRowCount(tblRows)
        self.dlgparameters.tblDataFields.setColumnCount(2)
        tblRows = 0
        for d in dataFieldList:
                self.dlgparameters.tblDataFields.setItem(tblRows,0,QTableWidgetItem(d.name))
#                QgsMessageLog.logMessage("Districts:" + str(d.type))
                if d.type == 1:
                        self.dlgparameters.tblDataFields.setItem(tblRows,1,QTableWidgetItem('Sum'))
                elif d.type == 2:
                        self.dlgparameters.tblDataFields.setItem(tblRows,1,QTableWidgetItem('% of district pop'))
                elif d.type == 3:
                        self.dlgparameters.tblDataFields.setItem(tblRows,1,QTableWidgetItem('% of total pop'))
                elif d.type == 4:
                        self.dlgparameters.tblDataFields.setItem(tblRows,1,QTableWidgetItem('% of field'))
                elif d.type == 99:
                        self.dlgparameters.tblDataFields.setItem(tblRows,1,QTableWidgetItem('population'))


                tblRows = tblRows + 1
        
    def updateFields(self):
        print("updateFields")
        self.dlgparameters.cmbPopField.clear()
        self.dlgparameters.cmbDistField.clear()
        self.dlgparameters.cmbDataField.clear()
        self.dockwidget.cmbGeoField.clear()
        self.dlgparameters.cmbDataType.clear()
#        self.dlgparameters.cmbDispField1.clear()
#        self.dlgparameters.cmbDispField2.clear()
#        layers = self.iface.legendInterface().layers()
        layers = [tree_layer.layer() for tree_layer in QgsProject.instance().layerTreeRoot().findLayers()]
        selectedLayerIndex = self.dlgparameters.cmbActiveLayer.currentIndex()
        selectedLayer = layers[selectedLayerIndex]
        fields = selectedLayer.fields()
        field_names = [field.name() for field in fields]
        self.dlgparameters.cmbPopField.addItems(field_names)
        self.dlgparameters.cmbDistField.addItems(field_names)
        self.dockwidget.cmbGeoField.addItems(field_names)
#        self.dlgparameters.cmbDispField1.addItems(["None"])
#        self.dlgparameters.cmbDispField2.addItems(["None"])        
        self.dlgparameters.cmbDataField.addItems(field_names)
        self.dlgparameters.cmbDataType.addItems(['Sum','% of Dist. Pop','% of Total Pop','% of Field'])
 #       self.dlgparameters.cmbDispField2.addItems(field_names)
        selectedLayerIndex = self.dlgparameters.cmbActiveLayer.currentIndex()
        selectedLayer = layers[selectedLayerIndex]

        loadFile = selectedLayer.source() + '.qgis.red'
        QgsMessageLog.logMessage('loadfile: ' + loadFile)
        if os.path.isfile(loadFile) == True:
                self.dlgparameters.btnLoadParameters.setEnabled(True)
        else:
                self.dlgparameters.btnLoadParameters.setEnabled(False)


    def showCompactness(self):
        field_id = self.activeLayer.fields().indexFromName(self.distfield)
        QgsMessageLog.logMessage("Starting...")
        QgsMessageLog.logMessage(self.activeLayer.source())
        QgsMessageLog.logMessage(self.activeLayer.name())
        ogr2ogr.main(['',self.activeLayer.name() + '_compactness.shp',self.activeLayer.source(),'-dialect','sqlite','-sql','SELECT ST_Union(geometry), ' + self.distfield + ' from ' + self.activeLayer.name() + ' GROUP BY ' + self.distfield])
        QgsMessageLog.logMessage("...done.")
        comp_layer = QgsVectorLayer(self.activeLayer.name() + "_compactness.shp","Compactness Report","ogr")
        if comp_layer.isValid():
                QgsMessageLog.logMessage("valid layer!.")
                comp_layer.startEditing()
                comp_layer.dataProvider().addAttributes([QgsField("Area",QVariant.Double), QgsField("Perimeter",QVariant.Double),QgsField("Contiguous",QVariant.Int)] )
                comp_layer.updateFields()
                area = 0
                for feature in comp_layer.getFeatures():
                        calculator = QgsDistanceArea()
                        calculator.setEllipsoid('WGS84')
                        calculator.setEllipsoidalMode(True)
                        calculator.computeAreaInit()
                        geom = gFeat.geometry()
                        landArea = feature['Area']
                        if geom.isMultipart():
                                polyg = geom.asPolygon()
                                if len(polyg) > 0:
                                        area = calculator.measurePolygon(polyg[0])
                                        landArea = area
                        else:
                                multi = geom.asMultiPolygon()
                                for polyg in multi:
                                        area = area + calculator.measurePolygon(polyg[0])
                                landArea = area
                comp_layer.commitChanges()

    def setEraser(self):
        if self.activedistrict == 0:
                self.activedistrict = self.dockwidget.sliderDistricts.value()
                self.dockwidget.lblActiveDistrict.setText("Active District: " + str(self.activedistrict))
        else:
                self.activedistrict = 0
                self.dockwidget.lblActiveDistrict.setText("Eraser Active")

    def exportToCsv(self):
        saveFileName, __ = QFileDialog.getSaveFileName(None)
        if saveFileName:
            with open(saveFileName, 'w') as csvFile:
                csvWriter = csv.writer(csvFile, delimiter=',', quoting=csv.QUOTE_MINIMAL)
                headerWriter = ['District','Population','To Target', 'Dev%']
                for d in dataFieldList:
                        headerWriter.append(d.name)
                csvWriter.writerow(headerWriter)
                for p in range(0,self.districts+1):
                        rowWriter = [str(p)]
                        rowWriter.append(str(distPop[p]))
                        rowWriter.append(str(self.targetpop - distPop[p]))
                        rowWriter.append(str(round((float(float(distPop[p]) / float(self.targetpop)) * 100)-100,2))+'%')
                        for d in dataFieldList:
                                if d.type == 1:
                                        rowWriter.append(str(d.field_sum[p]))
                                elif d.type == 2:
                                        if distPop[p] > 0:
                                                QgsMessageLog.logMessage(str(d.field_sum[p]) + " " + str(distPop[p]))
                                                rowWriter.append(str(round(float(float(d.field_sum[p]) / float(distPop[p])) * 100,2))+'%')
                                        else:
                                                rowWriter.append('0.00%')
                                elif d.type == 3:
                                        if self.totalpop > 0:
                                                QgsMessageLog.logMessage(str(d.field_sum[p]) + " " + str(self.totalpop))
                                                rowWriter.append(str(round(float(float(d.field_sum[p]) / float(self.totalpop)) * 100,2))+'%')
                                        else:
                                                rowWriter.append('0.00%')
                                elif d.type == 4:
                                        if d.total_sum > 0:
                                                QgsMessageLog.logMessage(str(d.field_sum[p]) + " " + str(d.total_sum))
                                                rowWriter.append(str(round(float(float(d.field_sum[p]) / float(d.total_sum)) * 100,2))+'%')
                                        else:
                                                rowWriter.append('0.00%')
                                csvWriter.writerow(rowWriter)

    def enclaveRemover(self):
        field_id = self.activeLayer.fields().indexFromName(self.distfield)
        self.activeLayer.startEditing()
        # Create a dictionary of all features
        feature_dict = {f.id(): f for f in self.activeLayer.getFeatures()}

        QgsMessageLog.logMessage("Building spatial index...")
        # Build a spatial index
        index = QgsSpatialIndex()
        for f in list(feature_dict.values()):
            index.insertFeature(f)

        QgsMessageLog.logMessage("Finding neighbors...")
        # Loop through all features and find features that touch each feature
        for f in list(feature_dict.values()):
            geom = f.geometry()
            # Find all features that intersect the bounding box of the current feature.
            # We use spatial index to find the features intersecting the bounding box
            # of the current feature. This will narrow down the features that we need
            # to check neighboring features.
            intersecting_ids = index.intersects(geom.boundingBox())
            # Initalize neighbors list and sum
            neighbors = []
            neighbors_district = -1
            finished = 0
            if f[self.distfield] == 0:
                    QgsMessageLog.logMessage("feature " + str(f.id()) + " with null distfield found!")
                    while neighbors_district != -2 and finished == 0:
                            finished = 0
                            for intersecting_id in intersecting_ids:
                                # Look up the feature from the dictionary
                                intersecting_f = feature_dict[intersecting_id]
                                # QgsMessageLog.logMessage("Neighbor found!")
                                # For our purpose we consider a feature as 'neighbor' if it touches or
                                # intersects a feature. We use the 'disjoint' predicate to satisfy
                                # these conditions. So if a feature is not disjoint, it is a neighbor.
                                if (f != intersecting_f and not intersecting_f.geometry().disjoint(geom)): 
                                        if intersecting_f[self.distfield] > 0:
                                                QgsMessageLog.logMessage("Neighbor found with > 0!")
                                                if neighbors_district == -1:
                                                        neighbors_district = intersecting_f[self.distfield]
                                                        QgsMessageLog.logMessage("neighbors_district set to " + str(neighbors_district))
                                                elif neighbors_district != intersecting_f[self.distfield]:
                                                        neighbors_district = -2
                                                        QgsMessageLog.logMessage("neighbors_district set to " + str(neighbors_district) + ", " + str(intersecting_f[self.distfield]) + " not matching")
                            if neighbors_district > 0:
                                QgsMessageLog.logMessage(str(f.id()) + " updating district to " + str(neighbors_district))
                                self.activeLayer.changeAttributeValue(f.id(),field_id,neighbors_district)
                                # Update the layer with new attribute values.
                            finished = 1

        self.activeLayer.commitChanges()

    def renameElectorates(self):
        self.dlgelectorates.show()
        self.dlgtoolbox.hide()
        txtBox = ''
#        try:
        for d, val in list(districtName.items()):
                if d != '0' and d != 0:
#                        QgsMessageLog.logMessage("looping through " + str(val))
                        txtBox = txtBox + str(val) + '\n'
        self.dlgelectorates.txtElectorates.setPlainText(txtBox)
#        except:
        # just to give the error checker something to do
        #        txtBox = ''


    def initializeElectorates(self):
        global districtId
        global districtName
        QgsMessageLog.logMessage("initializeElectorates called")
        counter = 1
        districtId = {}
        districtName = {}
        districtName[0] = str("0")
        districtId[str("0")] = 0
        for j in range(counter, self.districts+1):
                districtName[counter] = str(counter)
                districtId[str(counter)] = counter
                counter = counter + 1
        QgsMessageLog.logMessage(format(districtName))
        QgsMessageLog.logMessage(format(districtId))
        self.saveParametersToFile()
        self.updateFieldValues()
        self.updateTable()


    def updateElectorates(self):
        global districtId
        global districtName
        QgsMessageLog.logMessage("updateElectorates called")
        electorates = self.dlgelectorates.txtElectorates.toPlainText()
        electorateNames = electorates.split('\n')
        counter = 1
        districtId = {}
        districtName = {}
        districtName[0] = "0"
        districtId["0"] = 0
        for i in electorateNames:
                if counter <= self.districts:
                        districtName[counter] = str(i)
                        districtId[str(i)] = counter
                        counter = counter + 1
                        QgsMessageLog.logMessage(i)
        if counter > self.districts:
                for j in range(counter, self.districts):
                        districtName[counter] = str(counter)
                        districtId[str(counter)] = counter
                        counter = counter + 1
        QgsMessageLog.logMessage(format(districtName))
        QgsMessageLog.logMessage(format(districtId))
        self.saveParametersToFile()
        self.updateFieldValues()
        self.updateTable()
        self.updateLockedFields()

    def updateSelectedElectorate(self):
        self.dockwidget.lblActiveDistrict.setText("Click on the map...")
        self.featIdentTool =  QgsMapToolIdentifyFeature(self.canvas)
        self.featIdentTool.featureIdentified.connect(self.toolbtnSelectAction)
        self.featIdentTool.setLayer(self.activeLayer)
        self.canvas.setMapTool(self.featIdentTool)

    def selectByGeography(self):
        self.dlgtoolbox.hide()
        self.featIdentTool =  QgsMapToolIdentifyFeature(self.canvas)
        self.featIdentTool.featureIdentified.connect(self.selectByGeographyAction)
        self.featIdentTool.setLayer(self.activeLayer)
        self.canvas.setMapTool(self.featIdentTool)

    def toolbtnSelectAction(self, feature):
        #QgsMessageLog.logMessage(str(feature.id()) + " updating district to " + str(feature[self.distfield]))
        self.activedistrict = feature[self.distfield]
        self.dockwidget.lblActiveDistrict.setText("Active District: " + str(self.activedistrict))
        self.dockwidget.sliderDistricts.setValue(int(districtId[str(self.activedistrict)]))
        self.canvas.unsetMapTool(self.featIdentTool)
        self.featIdentTool = None

    def selectByGeographyAction(self, feature):
        field_id = self.activeLayer.fields().indexFromName(self.geofield)
        expr = QgsExpression("\"" + self.geofield + "\" = '" + str(feature[field_id]) + "'")
        iterator = self.activeLayer.getFeatures(QgsFeatureRequest(expr))
        ids = [i.id() for i in iterator]
        self.activeLayer.select(ids)
#        for feature_search in self.activeLayer.getFeatures():
#             try:
#                if feature_search[field_id] == feature[field_id]:
#                     self.activeLayer.select(feature_search.id())
#             except:
#                     QgsMessageLog.logMessage("error when selecting geography")

    def toolbtnSelectDeselect(self):
        self.dockwidget.lblActiveDistrict.setText("Active District: " + str(self.activedistrict))

    def onClosePlugin(self):
        self.dockwidget.closingPlugin.disconnect(self.onClosePlugin)
        self.attrdockwidget.closingPlugin.disconnect(self.onClosePlugin)
        self.dlgparameters.closingPlugin.disconnect(self.onClosePlugin)
        self.pluginIsActive = False
