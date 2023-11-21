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
from qgis.PyQt.QtWidgets import QAction, QDialogButtonBox, QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox, QShortcut
from qgis.PyQt.QtGui import QIcon, QColor, QPalette
from PyQt5.QtGui import QKeySequence
from qgis.core import QgsProject, QgsMessageLog, QgsSymbol, QgsVectorLayer, QgsCategorizedSymbolRenderer, QgsSimpleFillSymbolLayer, QgsRendererCategory, QgsSpatialIndex, QgsField, QgsExpression, QgsFeature, QgsFeatureRequest, QgsGeometry, QgsPointXY, QgsPalLayerSettings, QgsVectorLayerSimpleLabeling, QgsTextFormat, QgsTextBufferSettings
from qgis.gui import QgsMapCanvas, QgsMapToolEmitPoint, QgsMapTool, QgsMapToolIdentifyFeature
from random import randrange
from . import resources
import csv
import locale
import os
import glob

# Import the code for the DockWidget
from .StattoRedistrict_dockwidget import StattoRedistrictDockWidget
from .StattoRedistrict_attrdockwidget import StattoRedistrictAttrDockWidget
from .StattoRedistrict_dlgparameter import StattoRedistrictDlgParameter
from .StattoRedistrict_dlgtoolbox import StattoRedistrictDlgToolbox
from .StattoRedistrict_dlgelectorates import StattoRedistrictDlgElectorates
from .StattoRedistrict_dlgplanmanager import StattoRedistrictDlgPlanManager
from .StattoRedistrict_dlgpreview import StattoRedistrictDlgPreview
import os.path
import gc

#for thousands separators
locale.setlocale(locale.LC_ALL, '')

#define our list containers
dataFieldList = []				#the list of fields used by the currently active project
#dataFieldMasterList = []		#the list of fields from all projects on the layer, for proper save/load mechanism. now deprecated
dataPlanList = []				#the list of plans on all projects on the layer, for proper save/load mechanism
locked = {}						#whether a plan is locked
districtId = {}					#a lookup table of district ID to name
								#	IDs are used as much as possible, but name is stored on the table
districtName = {}				#lookup table of district name to ID
distPop = {}					#the population of the district ID
distPop2 = {}					#the population of the district ID, field number two
planManagerList = []			#list of plans for the plan manager
activePlanName = ''				#the name of the currently active loaded plan

plansInDirectory = {}           #a dictionary of saved redistricting plans in the current directory (filename-plan name)

#define our DataField class
#this is used to hold the user defined columns in the plan
class DataField(object):
        name = None
        plan = None
        type = 0
        total_sum = 0
        field_sum = []
        preview_dict = {}       #container for the previewer
        def __init__(self, values):
                self.name = values[0]
                self.plan = values[2]
                if values[1] == 'Sum' or values[1] == 1:
                        self.type = 1
                elif values[1] == '% of Dist. Pop' or values[1] == 2:
                        self.type = 2
                elif values[1] == '% of Total Pop' or values[1] == 3:
                        self.type = 3
                elif values[1] == '% of Dist. Pop 2' or values[1] == 5:
                        self.type = 5
                elif values[1] == 'Population' or values[1] == 99:
                        self.type = 99
                else:
                        self.type = 4
                self.field_sum = []
                print('appending ' + self.name)
                dataFieldList.append(self)

#the redistrictingPlan object is used to load and save different plans
class redistrictingPlan(object):
        name = None
        layerName = None
        districts = 0
        totalpop = 0
        targetpop = 0
        targetpoppct = 0
        targetpophigher = 0
        targetpoplower = 0
        totalpop2 = 0
        targetpop2 = 0
        targetpop2pct = 0
        targetpop2higher = 0
        targetpop2lower = 0
        popfield = ''
        popfield2 = ''
        distfield = ''
        geofield = ''
        dataFieldList = []
        districtName = {}
        locked = {}
        saveFileName = ''
        def __init__(self):
            self.dataFieldList = []
            self.districtName = {}
            self.districtId = {}
            dataPlanList.append(self)
            
            
            
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
        self.popfield2 = None               #the secondary population field in the database
        self.usepopfield2 = 0
        self.usepopfield2tolerance = 0
        self.distfield = None                #the district field in the database
        self.geofield = None
        self.totalpop = 0                #the total population
        self.totalpop2 = 0
        self.targetpop = 0                #the target population
        self.targetpoppct = 0                #target population percentage tolerance
        self.targetpoplower = 0                #target pop lower bound
        self.targetpophigher = 0                #target pop upper bound
        self.targetpop2 = 0                #the target population
        self.targetpop2pct = 0                #target population percentage tolerance
        self.targetpop2lower = 0                #target pop lower bound
        self.targetpop2higher = 0                #target pop upper bound
        self.planName = ''
        self.oldPlanName = ''                   #if you start to load a new plan, but then you cancel
        self.saveFileName = ''
        self.flagNewPlan = 0
        self.spatialIndex = None
        self.activePlan = None
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

        icon = QIcon(":/plugins/qgis3redistricter-master/icon.png")
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
        self.key_action = self.add_action(
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
            self.dlgplanmanager = None        #variable for the electorates dialog
            self.dlgpreview = None            #variable for the preview dialog
            self.featIdentTool = None                #make sure we can use the identify tool in the code



            self.districts = None                #number of districts in the tool
            self.activedistrict = '1'                #which district is active. We use string literals
            self.activeLayer = None                #which layer is active - which layer we're reapportioning
            self.popfield = None                #the population field in the database
            self.popfield2 = None               #the secondary population field in the database
            self.distfield = None                #the district field in the database
            self.geofield = None
            self.totalpop = 0                #the total population
            self.targetpop = 0                #the target population
            self.targetpop2 = 0                #the target population
            self.targetpoppct = 0                #target population percentage tolerance
            self.targetpop2pct = 0                #target population percentage tolerance
            self.targetpoplower = 0                #target pop lower bound
            self.targetpophigher = 0                #target pop upper bound
            self.targetpop2lower = 0                #target pop lower bound
            self.targetpop2higher = 0                #target pop upper bound

            self.planName = ''                       #the name of the active plan
            self.flagNewPlan = 0                    #determines what should happen with saving/loading 
            self.activePlan = None                  #the active plan
            self.labelLayer = None
            self.undoAttr = {}
            self.visibleFeats = []

            self.defaultBG = QColor(QPalette().color(QPalette.Normal, QPalette.Window))

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

            if self.dlgplanmanager == None:
                self.dlgplanmanager = StattoRedistrictDlgPlanManager()
                
            if self.dlgpreview == None:
                self.dlgpreview = StattoRedistrictDlgPreview()

            # connect to provide cleanup on closing of dockwidget
            self.dockwidget.closingPlugin.connect(self.onClosePlugin)

            #provide other gui options
            self.dockwidget.btnParameters.clicked.connect(self.openPlanManager)
            self.dockwidget.btnUpdate.clicked.connect(self.updateAttributes)

            self.dockwidget.btnUpdate.shortcut = QShortcut(QKeySequence("`"), self.dockwidget.btnUpdate)
            self.dockwidget.btnUpdate.shortcut.activated.connect(self.updateAttributes)

            self.dockwidget.btnEraser.clicked.connect(self.setEraser)
            self.dockwidget.btnSelect.clicked.connect(self.updateSelectedElectorate)
            self.dockwidget.btnToolbox.clicked.connect(self.openToolbox)
            self.dockwidget.sliderDistricts.valueChanged.connect(self.updateDistrict)
            self.dockwidget.btnActiveDistrictMinus.clicked.connect(self.updateDecreaseDistrictIncrement)
            self.dockwidget.btnActiveDistrictPlus.clicked.connect(self.updateIncreaseDistrictIncrement)

            self.dockwidget.btnActiveDistrictMinus.shortcut = QShortcut(QKeySequence("2"), self.dockwidget.btnActiveDistrictMinus)
            self.dockwidget.btnActiveDistrictMinus.shortcut.activated.connect(self.updateDecreaseDistrictIncrement)

            self.dockwidget.btnActiveDistrictPlus.shortcut = QShortcut(QKeySequence("3"), self.dockwidget.btnActiveDistrictPlus)
            self.dockwidget.btnActiveDistrictPlus.shortcut.activated.connect(self.updateIncreaseDistrictIncrement)

            self.dockwidget.btnUndo.clicked.connect(self.undoLast)
            self.dockwidget.btnPreview.clicked.connect(self.previewSelection)
            self.dockwidget.btnUpdate.shortcut = QShortcut(QKeySequence("1"), self.dockwidget.btnPreview)
            self.dockwidget.btnUpdate.shortcut.activated.connect(self.previewSelection)
            
            self.dockwidget.btnFindDistrict.clicked.connect(self.selectByActiveDistrict)
            self.dockwidget.btnGeoSelect.clicked.connect(self.selectByGeography)
            self.dockwidget.cmbGeoField.currentIndexChanged.connect(self.updateGeographyColumn)
            self.dockwidget.btnFloodFill.clicked.connect(self.selectByFloodFill)
            self.dockwidget.btnCurrentPlan.clicked.connect(self.loadActivePlanParametersDialog)
            
            self.dockwidget.btnRefreshAttributes.clicked.connect(self.getVisibleFeatureAttributes)

            self.attrdockwidget.tblPop.itemClicked.connect(self.updateLockedFields)

            self.dlgparameters.cmbActiveLayer.currentIndexChanged.connect(self.updateFields)

#parameters event triggers
            self.dlgparameters.boxButton.button(QDialogButtonBox.Ok).clicked.connect(self.updatePanelAndSaveParameters)
            self.dlgparameters.boxButton.button(QDialogButtonBox.Cancel).clicked.connect(self.closeParameters)
            self.dlgparameters.btnAddDataField.clicked.connect(self.addDataField)
            self.dlgparameters.btnRemoveDataField.clicked.connect(self.removeDataField)
            self.dlgparameters.btnCreateNewField.clicked.connect(self.createNewDistrictField)

#toolbox event triggers
            self.dlgtoolbox.btnExportToCsv.clicked.connect(self.exportToCsv)
            self.dlgtoolbox.btnLabelLayer.clicked.connect(self.createLabelLayer)
            self.dlgtoolbox.btnRename.clicked.connect(self.renameElectorates)
            self.dlgtoolbox.btnSelectUnassigned.clicked.connect(self.selectUnassigned)
            self.dlgtoolbox.btnRefreshAttributeTable.clicked.connect(self.refreshTable)
            self.dlgtoolbox.btnExportCrosstabToCsv.clicked.connect(self.exportCrosstabToCsv)

            self.dlgelectorates.boxButton.button(QDialogButtonBox.Ok).clicked.connect(self.updateElectorates)

            self.dlgplanmanager.btnLoadPlan.clicked.connect(self.loadParametersDialog)
            self.dlgplanmanager.btnNewPlan.clicked.connect(self.newParametersDialog)

            # show the dockwidget
            # TODO: fix to allow choice of dock location
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dockwidget)
            self.dockwidget.show()

            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.attrdockwidget)
            self.attrdockwidget.show()

            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dlgpreview)


    def restoreWidgets():
        self.attrdockwidget.show()
        self.attrdockwidget.show()


    def canvasReleaseEvent(self, event):
        """Deprecated"""
        QgsMessageLog.logMessage("released!")
        with edit(self.activeLayer):
                selection = self.activeLayer.selectedFeatures()
                for feature in selection:
                        feature[self.distfield] = self.activedistrict
                        
    def getVisibleFeatureAttributes(self):
        layer = self.activeLayer
        rect = self.canvas.extent()
        request = QgsFeatureRequest().setFilterRect(rect)
        if layer:
            selected_feats = layer.getFeatures(request)
            idx = layer.fields().indexFromName(self.distfield)
            attr = [ str(feat.attributes()[idx]) for feat in selected_feats ]
            try:
                self.visibleFeats = list(dict.fromkeys(districtName[attr]))
            except:
                self.visibleFeats = list(dict.fromkeys(attr))
            self.updateTable()

    def updateAttributes(self):
        """Updates the attributes of the the data table when the Update Selected Polygons feature is clicked"""
        self.dockwidget.btnUpdate.setEnabled(False)
        global locked
        self.undoAttr.clear()
        gc.collect()
        
        self.dockwidget.lblPreview.setText('')
        counter = 0     #was originally in the if statement, but this crashes the status bar update if locked
        totfeatures = self.activeLayer.selectedFeatureCount()   #counts the number of features
        if locked[districtName[self.activedistrict]] == 0:
            

            ids = self.activeLayer.selectedFeatureIds()
            request = QgsFeatureRequest().setFlags(QgsFeatureRequest.NoGeometry)
            request.setFilterFids(ids)
            
            field_id = self.activeLayer.fields().indexFromName(self.distfield)
            
            self.activeLayer.startEditing()
            self.activeLayer.beginEditCommand( 'updating features' )
            self.iface.statusBarIface().showMessage(u"Updating features... ")
            field_id = self.activeLayer.fields().indexFromName(self.distfield)
                #after a certain point, see if it's faster to bifurcate attribute updates
            for feature in self.activeLayer.getFeatures(request):
                    try:
                            if locked[str(feature[self.distfield])] == 0:
                                    self.undoAttr[feature.id()] = feature[self.distfield]
                                    self.updateFeatureValue(feature, districtName[self.activedistrict], field_id)
#                                    self.updateFeatureValuev2(feature, districtName[self.activedistrict], field_id)

                    except:
                            self.updateFeatureValue(feature, districtName[self.activedistrict], field_id)
#                            self.updateFeatureValuev2(feature, districtName[self.activedistrict], field_id)
                    counter = counter + 1
                    if counter % 250 == 0:
                        self.activeLayer.endEditCommand()
                        self.activeLayer.commitChanges()
                        self.activeLayer.startEditing()
                        self.activeLayer.beginEditCommand( 'updating features' )
                        self.iface.statusBarIface().showMessage( u"Still updating features... (" + str(counter) + " updated)" )
                        QCoreApplication.processEvents()
#                    QgsMessageLog.logMessage(str(feature.id) + " changed to: " + str(self.activedistrict) + " on " + str(field_id))
            self.activeLayer.endEditCommand()
            self.iface.statusBarIface().showMessage( u"Updating population table" )
            
            QCoreApplication.processEvents()
            self.updateFieldValues()
            self.iface.statusBarIface().showMessage( u"Committing changes to table" )
            QCoreApplication.processEvents()
            self.activeLayer.commitChanges()
        self.activeLayer.removeSelection()
        self.updateTable()
        self.iface.mapCanvas().refresh()
        self.dockwidget.btnUndo.setEnabled(True)
        self.iface.mainWindow().statusBar().showMessage( u"Updated " + str(counter) + " features." )
        self.dockwidget.btnUpdate.setEnabled(True)
        gc.collect()

    def previewSelection(self):
        global locked
        global distPop
        prevpop = 0
        prevpoplock = 0
        newprevpop = 0
        strActiveDistPop = ''
        
        previewDistricts = {}
        gc.collect()
        
        for d in dataFieldList:
            d.preview_dict.clear()
       
        if str(self.activedistrict) != "0" and str(self.activedistrict) != "NULL":
            previewDistricts[str(districtName[self.activedistrict])] = distPop[self.activedistrict]
            curselpop = distPop[self.activedistrict]
            
            for d in dataFieldList:
                d.preview_dict[str(districtName[self.activedistrict])] = 0
            
        selection = self.activeLayer.selectedFeatures()
        for feature in selection:
            field_id = self.activeLayer.fields().indexFromName(self.distfield)
            prevpop = prevpop + feature[self.popfield]
            
            if str(feature[self.distfield]) != str(districtName[self.activedistrict]):
                prevpoplock = prevpoplock + feature[self.popfield]
                featId = str(feature[self.distfield])
                if featId == 'NULL':
                    featId = '0'
                if locked[featId] == 0:
                    newprevpop = newprevpop + feature[self.popfield]

                    if str(feature[self.distfield]) in previewDistricts.keys():
                        previewDistricts[str(feature[self.distfield])] = previewDistricts[str(feature[self.distfield])] - feature[self.popfield]
                        previewDistricts[str(districtName[self.activedistrict])] = previewDistricts[str(districtName[self.activedistrict])] + feature[self.popfield]
                    else:
# commented out code here which wasn't working, but didn't delete it just in case - you can probably do so safely
#                        print(str(int(districtId[feature[self.distfield]])))
                        try:
                            #avoids errors when values are null
                            previewDistricts[str(feature[self.distfield])] = distPop[int(districtId[str(feature[self.distfield])])]
                            previewDistricts[str(feature[self.distfield])] = previewDistricts[str(feature[self.distfield])] - feature[self.popfield]
#                            previewDistricts[str(feature[self.distfield])] = distPop[int(districtId[feature[self.distfield]])] - feature[self.popfield]
                            previewDistricts[str(districtName[self.activedistrict])] = previewDistricts[str(districtName[self.activedistrict])] + feature[self.popfield]
                        except:
                            previewDistricts['0'] = distPop[0] - feature[self.popfield]
                            previewDistricts[str(districtName[self.activedistrict])] = previewDistricts[str(districtName[self.activedistrict])] + feature[self.popfield]

            """
                    for d in dataFieldList:
                        if str(feature[self.distfield]) in d.preview_dict.items():
                            d.preview_dict[str(feature[self.distfield])] = d.preview_dict[str(feature[self.distfield])] - d.field_sum[int(districtId[str(feature[self.distfield])])]
                            d.preview_dict[str(districtName[self.activedistrict])] = d.preview_dict[str(districtName[self.activedistrict])] + d.field_sum[str(districtId[self.activedistrict])]
                        else:
                            try:
                                d.preview_dict[str(feature[self.distfield])] = (d.field_sum[int(districtId[str(feature[self.distfield])])] * -1)
                                d.preview_dict[str(districtName[self.activedistrict])] = d.preview_dict[str(districtName[self.activedistrict])] + d.field_sum[str(districtId[self.activedistrict])]
                            except:
                                d.preview_dict[str(feature[self.distfield])] = (d.field_sum[0] * -1)
                                d.preview_dict[str(districtName[self.activedistrict])] = d.preview_dict[str(districtName[self.activedistrict])] + d.field_sum[str(districtId[self.activedistrict])]
            """
        if self.activedistrict > 0:
            strActiveDistPop = ', in district: ' + str(prevpop - prevpoplock) + ', active district +' + str(newprevpop) + ' (' + str(distPop[self.activedistrict]) + '→' + str(distPop[self.activedistrict] + newprevpop) + ')'
        self.dockwidget.lblPreview.setText('in selection:' + str(prevpop) + strActiveDistPop)
        
        
        self.dlgpreview.tblPreview.setColumnCount(5)
        self.dlgpreview.tblPreview.setHorizontalHeaderLabels(['District','New Pop','Old Pop','Change','Dev%'])
        self.dlgpreview.show()
        counter = 0
        for p in previewDistricts:
            self.dlgpreview.tblPreview.setRowCount(counter+1)
            self.dlgpreview.tblPreview.setItem(counter,0,QTableWidgetItem(str(p)))
            self.dlgpreview.tblPreview.setItem(counter,1,QTableWidgetItem(str('{:,}'.format(previewDistricts[p]))))
#            try:
            self.dlgpreview.tblPreview.setItem(counter,2,QTableWidgetItem(str('{:,}'.format(distPop[int(districtId[p])]))))
            self.dlgpreview.tblPreview.setItem(counter,3,QTableWidgetItem(str('{:,}'.format(previewDistricts[p] - distPop[int(districtId[p])]))))
#            except:
#                self.dlgpreview.tblPreview.setItem(counter,2,QTableWidgetItem(str('{:,}'.format(distPop[0])))(
#                self.dlgpreview.tblPreview.setItem(counter,3,QTableWidgetItem(str('{:,}'.format(previewDistricts[p] - distPop[0]))))
            try:
                if self.targetpop > 0:
                    self.dlgpreview.tblPreview.setItem(counter,4,QTableWidgetItem(str(round((float(float(previewDistricts[p]) / float(self.targetpop)) * 100)-100,2))+'%'))
                else:
                    self.dlgpreview.tblPreview.setItem(counter,4,QTableWidgetItem('0.00%'))
            except:
                self.dlgpreview.tblPreview.setItem(counter,4,QTableWidgetItem('0.00%'))

            counter = counter + 1
            
        self.dlgpreview.tblPreview.resizeColumnToContents(0)
        self.dlgpreview.tblPreview.resizeColumnToContents(1)
        self.dlgpreview.tblPreview.resizeColumnToContents(2)
        self.dlgpreview.tblPreview.resizeColumnToContents(3)
        self.dlgpreview.tblPreview.resizeColumnToContents(4)



    def undoLast(self):
        self.activeLayer.startEditing()
        field_id = self.activeLayer.fields().indexFromName(self.distfield)
        for feature, value in self.undoAttr.items():
            self.updateFeatureValue(self.activeLayer.getFeature(feature), value, field_id)
        self.activeLayer.commitChanges()
        self.undoAttr.clear()
        gc.collect()
        self.updateTable()
        self.dockwidget.btnUndo.setEnabled(False)

    def updateFeatureValuev2(self, feature, change_to, field_id):
        self.activeLayer.changeAttributeValue(feature.id(),field_id,change_to)
        newId = int(districtId[str(change_to)])
        try:
                distPop[newId] = distPop[newId] + feature[self.popfield]
#                QgsMessageLog.logMessage("to: " + str(newId))
        except:
                try:
                        distPop[0] = distPop[0] + feature[self.popfield]
                except:
                        errors = 1

#    def updateAttributesUsingSQL(self):
#        for p in (0, self.districts+1):
#           district_pop = QgsExpression('sum(')

    def updateFeatureValue(self, feature, change_to,field_id):
#        QgsMessageLog.logMessage("updating feature value")
        global distPop
        global distPop2
#        field_id = self.activeLayer.fields().indexFromName(self.distfield)
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

        if self.popfield2:
            try:
                    distPop2[int(districtId[str(feature[self.distfield])])] = distPop2[int(districtId[str(feature[self.distfield])])] - feature[self.popfield2] # feature[self.popfield]
    #                QgsMessageLog.logMessage("from: " + str(districtId[str(feature[self.distfield])]))
            except:
                    try:
                            distPop2[0] = distPop2[0] - feature[self.popfield2]
    #                        QgsMessageLog.logMessage("from: zero")
                    except:
                            errors = 1
    #                        QgsMessageLog.logMessage(self.distfield + " failed on load")

        for d in dataFieldList:
                try:
                        d.field_sum[int(districtId[str(feature[self.distfield])])] = d.field_sum[int(districtId[str(feature[self.distfield])])] - feature[d.name]
                        d.total_sum = d.total_sum - feature[d.name]
                except:
                        d.field_sum[0] = d.field_sum[0] - feature[d.name]
                        d.total_sum = d.total_sum - feature[d.name]

#        QgsMessageLog.logMessage(str(districtId[str(feature[self.distfield])]))
        self.activeLayer.changeAttributeValue(feature.id(),field_id,change_to)
        
        if str(change_to) != 'NULL':
            newId = int(districtId[str(change_to)])
        else:
            newid = 'NULL'

        try:
                distPop[newId] = distPop[newId] + feature[self.popfield]
#                QgsMessageLog.logMessage("to: " + str(newId))
        except:
                try:
                        distPop[0] = distPop[0] + feature[self.popfield]
#                        QgsMessageLog.logMessage("to: zer0")
                except:
                        errors = 1
                        QgsMessageLog.logMessage(self.distfield + " failed on load")
                        
        if self.popfield2 == 1:
            try:
                distPop2[newId] = distPop2[newId] + feature[self.popfield2]
#                QgsMessageLog.logMessage("to: " + str(newId))
            except:
                try:
                        distPop2[0] = distPop2[0] + feature[self.popfield2]
#                        QgsMessageLog.logMessage("to: zer0")
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

    def deletePlan(self):
        if self.dlgplanmanager.lstRedistrictingPlans.selectedItems():
            for l in self.dlgplanmanager.lstRedistrictingPlans.selectedIndexes():
                layerName = l
        else:
            return

        if layerName != None:
            layers = planManagerList[layerName.row()].split('|')
            os.remove(layers[1])
        else:
            return
        self.loadParametersDialog()

    def openPlanManager(self):
        global planManagerList
        self.flagNewPlan = 0
        self.dlgplanmanager.show()
        self.dlgplanmanager.lstRedistrictingPlans.clear()
        planManagerList = []
#        old QGIS 2 code
#        layers = self.iface.legendInterface().layers()
        layers = [tree_layer.layer() for tree_layer in QgsProject.instance().layerTreeRoot().findLayers()]
        layer_list = []
        for layer in layers:
            fileDir = os.path.splitext(layer.source())
#            print('Source: ' + layer.source())
            for layerDir in fileDir:
                for ffile in glob.glob(str(layerDir) + '*qgis.red'):
                        print(' checking file ' + ffile)
#                    try:
                        f = open(ffile,'r')
                        planStatus = 0
                        for line in f:
        #                    QgsMessageLog.logMessage(str(line) + ' ' + str(planStatus))
                            line = line.strip()
                            lineList = line.split('\t')
                            if lineList[0] == 'New Plan' and planStatus == 0:
                                print('     plan status 1')
                                planStatus = 1
                            elif lineList[0] == 'planname' and planStatus == 1:
                                print('     plan status 2')
                                planStatus = 2
                                self.dlgplanmanager.lstRedistrictingPlans.addItem(layer.name() + ' (' + str(lineList[1]) + ')')
                                strLayerName = str(layer.name())
                                planManagerList.append(strLayerName + '|' + str(ffile))
                            elif lineList[0] == 'End Plan':
                                planStatus = 0
                        f.close()
#                    except:
#                        QgsMessageLog.logMessage("No plan found for layer " + layer.name())
        self.dlgparameters.cmbActiveLayer.clear()
        self.dlgparameters.cmbActiveLayer.addItems(layer_list)
        if self.activeLayer != None:
                self.dlgparameters.cmbActiveLayer.setCurrentIndex(self.dlgparameters.cmbActiveLayer.findText(self.activeLayer.name()))
                self.setParameters()



    def newParametersDialog(self):
        #creating a new plan
        self.flagNewPlan = 1
        self.dlgplanmanager.hide()
        self.dlgparameters.show()
        layers = [tree_layer.layer() for tree_layer in QgsProject.instance().layerTreeRoot().findLayers()]
        layer_list = []
        for layer in layers:
                layer_list.append(layer.name())
        self.dlgparameters.cmbActiveLayer.clear()
        self.dlgparameters.cmbActiveLayer.addItems(layer_list)
        if self.activeLayer != None:
                self.dlgparameters.cmbActiveLayer.setCurrentIndex(self.dlgparameters.cmbActiveLayer.findText(self.activeLayer.name()))
                self.setParameters()


    def loadParametersDialog(self):
        if self.dlgplanmanager.lstRedistrictingPlans.selectedItems():
            for l in self.dlgplanmanager.lstRedistrictingPlans.selectedIndexes():
                layerName = l
        else:
            return

        layers = []
        if layerName != None:
            layers = planManagerList[layerName.row()].split('|')
            l = QgsProject.instance().mapLayersByName(layers[0])
            self.activeLayer = l[0]
            self.loadParameters(layers[1])

        if self.activeLayer:
            self.dlgplanmanager.hide()
            self.dlgparameters.show()
            projectLayers = [tree_layer.layer() for tree_layer in QgsProject.instance().layerTreeRoot().findLayers()]
            layer_list = []
            for layer in projectLayers:
                    layer_list.append(layer.name())
            self.dlgparameters.cmbActiveLayer.clear()
            self.dlgparameters.cmbActiveLayer.addItems(layer_list)
            self.dlgparameters.chkStyleMap.setChecked(False)
            self.initialiseActivePlan(layers[1])
            self.dlgparameters.cmbActiveLayer.setCurrentIndex(self.dlgparameters.cmbActiveLayer.findText(self.activeLayer.name()))
            self.setParameters()
            self.updateFieldTable(layers[1])
        else:
#error message this
            return
            
    def loadActivePlanParametersDialog(self):
        if self.activeLayer:
            self.dlgplanmanager.hide()
            self.dlgparameters.show()
            projectLayers = [tree_layer.layer() for tree_layer in QgsProject.instance().layerTreeRoot().findLayers()]
            layer_list = []
            for layer in projectLayers:
                    layer_list.append(layer.name())
            self.dlgparameters.cmbActiveLayer.clear()
            self.dlgparameters.cmbActiveLayer.addItems(layer_list)
            self.dlgparameters.chkStyleMap.setChecked(False)
            self.dlgparameters.cmbActiveLayer.setCurrentIndex(self.dlgparameters.cmbActiveLayer.findText(self.activeLayer.name()))
            self.setParameters()

    def openToolbox(self):
    
        self.dlgtoolbox.cmbCrossTab.clear()
        if hasattr(self.activeLayer, 'fields'):
            fields = self.activeLayer.fields()
            field_names = [field.name() for field in fields]
            self.dlgtoolbox.cmbCrossTab.addItems(field_names)
        self.dlgtoolbox.show()


    def updateLockedFields(self):
        QgsMessageLog.logMessage("Locking...")
        global locked
        locked = {}
        locked['NULL'] = 0
        counter = 0
        for q in range(0,self.districts+1):
            locked[str(districtName[q])] = 0
        for q in range(0,self.districts+1):
            if q == 0 or (self.dockwidget.chkVisible.isChecked() == False) or (self.dockwidget.chkVisible.isChecked() == True and districtName[q] in self.visibleFeats):
                r = counter
                counter = counter + 1
                locked[districtName[r]] = 0
                if self.attrdockwidget.tblPop.item(r,1).checkState() == Qt.Checked:
                        locked[districtName[q]] = 1
        QgsMessageLog.logMessage("...locked. " + str(locked))
        self.updateDistrict()

    def updateGeographyColumn(self):
        self.geofield = self.dockwidget.cmbGeoField.currentText()

    def saveParametersToFile(self,fileName=None):
        global districtName
#        global dataPlanList

        """
#        try:
        f = open(self.activeLayer.srce() + '.qgis.red','w')
        f.write('New Plan\n')
        f.write('Plan Name\n')
#        f.write(dp.name)
        f.write('New Redistricting Plan')
        f.write('Fields\n')
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
        f.write('End Plan')
        f.close()
        """

#        try:
        if fileName == None:
            self.activeLayer.source() + '.qgis.red'
        f = open(fileName,'w')
        dp = self #exceptionally inelegant
        f.write('New Plan\n')
        f.write('planname\t'+ str(dp.planName) + '\n')
        f.write('districts\t' + str(dp.districts) + '\n')
        f.write('totalpop\t' + str(dp.totalpop) + '\n')
        f.write('targetpop\t' + str(dp.targetpop) + '\n')
        f.write('targetpoppct\t' + str(dp.targetpoppct) + '\n')
        f.write('targetpoplower\t' + str(dp.targetpoplower) + '\n')
        f.write('targetpophigher\t' + str(dp.targetpophigher) + '\n')
        f.write('targetpop2\t' + str(dp.targetpop2) + '\n')
        f.write('targetpop2pct\t' + str(dp.targetpop2pct) + '\n')
        f.write('targetpop2lower\t' + str(dp.targetpop2lower) + '\n')
        f.write('targetpop2higher\t' + str(dp.targetpop2higher) + '\n')
        f.write('popfield\t' + str(dp.popfield) + '\n')
        f.write('popfield2\t' + str(dp.popfield2) + '\n')
        f.write('distfield\t' + str(dp.distfield) + '\n')
        f.write('geofield\t' + str(dp.geofield) + '\n')
        for d in dataFieldList:
                writeStr = 'datafield\t' + d.name + '\t' + str(d.type) + '\n'
                f.write(writeStr)
        f.write('districtnames\t')
        for r in districtName:
                if districtName[r] != 'NULL':
                    f.write(str(districtName[r]) + '\t')
        f.write('\n')
        writeStr = 'locked\t'
        for l in locked:
            if locked[l] == 1:
                writeStr = writeStr + str(l)
        f.write(writeStr + '\n')
        f.write('End Plan\n')
        f.close()
#            QgsMessageLog.logMessage("Parameters file saved!")
#        except:
#            QgsMessageLog.logMessage("Parameters file could not be saved")



    def loadParameters(self,planName=None):
        global districtName
        global districtId
        global locked
        self.dlgparameters.chkStyleMap.setChecked(False)
        f = open(planName,'r')
        self.saveFileName = planName
        planStatus = 0
        del dataFieldList[:]
        districtId = {}
        districtName = {}
        locked = {}
        for line in f:
            line = line.strip()
            lineList = line.split('\t')
            if lineList:
                print(lineList)
                if lineList[0] == "planname":
                    self.planName = lineList[1]
                if lineList[0] == "districts":
                    self.districts = int(lineList[1])
                if lineList[0] == "totalpop":
                    self.totalpop = int(lineList[1])
                if lineList[0] == "targetpop":
                    self.targetpop = int(lineList[1])
                if lineList[0] == "targetpoppct":
                    self.targetpoppct = float(lineList[1])
                if lineList[0] == "targetpoplower":
                    self.targetpoplower = int(lineList[1])
                if lineList[0] == "targetpophigher":
                    self.targetpophigher = int(lineList[1])
                if lineList[0] == "targetpop2":
                    self.targetpop2 = float(lineList[1])
                if lineList[0] == "targetpop2pct":
                    self.targetpop2pct = float(lineList[1])
                if lineList[0] == "targetpop2lower":
                    self.targetpop2lower = int(lineList[1])
                if lineList[0] == "targetpop2higher":
                    self.targetpop2higher = int(lineList[1])
                if lineList[0] == "popfield":
                    self.popfield = (lineList[1])
                if lineList[0] == "popfield2":
                    self.popfield2 = (lineList[1])
                if lineList[0] == "distfield":
                    self.distfield = (lineList[1])
                if lineList[0] == "geofield":
                    if lineList[1]:
                        self.geofield = (lineList[1])
                if lineList[0] == "datafield":
                    newfield = (lineList[1])
                    newfieldtype = int(lineList[2])
                    df = DataField([newfield, newfieldtype, self.planName])
                if lineList[0] == "districtnames":
                    counter = 0
                    for i in lineList:
                        if counter > 0:
                            districtName[counter-1] = str(i)
                            if i not in districtId:
                                    districtId[i] = int(counter - 1)
                        counter = counter + 1
                if lineList[0] == "locked":
                    for i in lineList:
                        if str(i) != 'locked':
                            locked[str(i)] = 1
        self.updateFieldTable()
        f.close()

    def oldloadParameters(self,planName=None):
        """
        this loads a specific saved file
        import parameters imports all plans
        """
        self.dlgparameters.chkStyleMap.setChecked(False)
        f = open(self.activeLayer.source() + '.qgis.red','r')
        planStatus = 0
        planLoadedStatus = 0
        for line in f:
            line = line.strip()
            if line == 'New Plan':
                planStatus = 1
            if line == 'End Plan':
                planStatus = 0
            if line == 'Plan Name':
                loadedPlanName = f.readline()
                self.planName = loadedPlanName
                planStatus = 2
            if line == 'Fields' and planStatus == 2 and planName == loadedPlanName:
                planLoadedStatus = 1
                self.districts = f.readline()
                self.districts = int(self.districts)
                self.totalpop = f.readline()
                self.totalpop = int(self.totalpop)
                self.targetpop = f.readline()
                self.targetpop = int(self.targetpop)
                self.targetpoppct = f.readline()
                self.targetpoppct = float(self.targetpoppct)
                self.targetpoplower = f.readline()
                self.targetpoplower = int(self.targetpoplower)
                self.targetpophigher = f.readline()
                self.targetpophigher = int(self.targetpophigher)
                self.targetpop2 = f.readline()
                self.targetpop2 = float(self.targetpop2)
                self.targetpop2pct = f.readline()
                self.targetpop2pct = int(self.targetpop2pct)
                self.targetpop2lower = f.readline()
                self.targetpop2lower = int(self.targetpop2lower)
                self.targetpop2higher = f.readline()
                self.targetpop2higher = int(self.targetpop2higher)
                self.popfield = f.readline().rstrip()
                self.popfield2 = f.readline().rstrip()
                self.distfield = f.readline().rstrip()
                self.geofield = f.readline().rstrip()
                fieldparams = int(f.readline())
                for fp in range(0, fieldparams):
                #these are loaded elsewhere (importParameters), but we still need to parse the file
                        newfield = f.readline().rstrip()
                        newfieldtype = f.readline().strip()
                        newfieldtype = int(newfieldtype)
                        df = DataField([newfield, newfieldtype, self.planName])
                loader = f.readline()
                loader_int = int(loader)
                for fn in range(0, loader_int):
                        tmpDistrictName = f.readline().rstrip()
                        districtName[fn] = tmpDistrictName
                        if str(tmpDistrictName) not in districtId:
                                districtId[str(tmpDistrictName)] = str(fn)
        self.updateFieldTable()
        f.close()
#        del dataFieldList[:]
#        for d in dataFieldMasterList:
#            print("field:" + d.plan + '|' + self.planName)
#            if d.plan == self.planName:
#                dataFieldList.append(d)

    def importParameters(self):
        global dataPlanList
        dataPlanList = []
        
#        for d in dataFieldMasterList:
#            if d.plan != 'qgisRedistricterPendingField':
#                 dataFieldMasterList.remove(d)
        
        try:
            if self.activeLayer:
                f = open(self.activeLayer.source() + '.qgis.red','r')
                planStatus = 0
                planLoadedStatus = 0
                for line in f:
                    line = line.strip()
                    QgsMessageLog.logMessage(str(line) + ' ' + str(planStatus))
                    if line == 'New Plan':
                        planStatus = 1
                        a = redistrictingPlan()
                    if line == 'End Plan':
                        planStatus = 0
                    if line == 'Plan Name':
                        loadedPlanName = f.readline()
                        a.name = loadedPlanName
                        planStatus = 2
                    if line == 'Fields' and planStatus == 2:
                        planLoadedStatus = 1
                        a.layername = self.activeLayer.name()
                        a.districts = f.readline()
                        a.districts = int(a.districts)
                        a.totalpop = f.readline()
                        a.totalpop = int(a.totalpop)
                        a.targetpop = f.readline()
                        a.targetpop = int(a.targetpop)
                        a.targetpoppct = f.readline()
                        a.targetpoppct = float(a.targetpoppct)
                        a.targetpoplower = f.readline()
                        a.targetpoplower = int(a.targetpoplower)
                        a.targetpophigher = f.readline()
                        a.targetpophigher = int(a.targetpophigher)
                        a.targetpop2 = f.readline()
                        a.targetpop2 = float(a.targetpop2)
                        a.targetpop2pct = f.readline()
                        a.targetpop2pct = int(a.targetpop2pct)
                        a.targetpop2lower = f.readline()
                        a.targetpop2lower = int(a.targetpop2lower)
                        a.targetpop2higher = f.readline()
                        a.targetpop2higher = int(a.targetpop2higher)
                        a.popfield = f.readline().rstrip()
                        a.popfield2 = f.readline().rstrip()
                        a.distfield = f.readline().rstrip()
                        a.geofield = f.readline().rstrip()
                        fieldparams = int(f.readline())
                        for fp in range(0, fieldparams):
                                newfield = f.readline().rstrip()
                                newfieldtype = f.readline()
                                newfieldtype = int(newfieldtype)
                                print("data field found")
                                df = DataField([newfield, newfieldtype, a.name])
                        loader = f.readline()
                        loader_int = int(loader)
                        for fn in range(0, loader_int):
                                tmpDistrictName = f.readline().rstrip()
                                a.districtName[fn] = tmpDistrictName
                                if str(tmpDistrictName) not in districtId:
                                        a.districtId[str(tmpDistrictName)] = str(fn)
                f.close()
        except:
            QgsMessageLog.logMessage("Nothing to load for layer " + self.activeLayer.name())

    def initialiseActivePlan(self, strActivePlanName = ''):
        for p in dataPlanList:
            if p.name == strActivePlanName:
                self.activePlan = p
                return



    def setParameters(self):
        self.dlgparameters.inpDistricts.setValue(self.districts)
        self.dlgparameters.cmbPopField.setCurrentIndex((self.dlgparameters.cmbPopField.findText(self.popfield)))
        if self.popfield2 == None or self.popfield2 == 'None':
            self.dlgparameters.cmbPopField_2.setCurrentIndex((self.dlgparameters.cmbPopField_2.findText('None')))
        else:
            self.dlgparameters.cmbPopField_2.setCurrentIndex((self.dlgparameters.cmbPopField_2.findText(self.popfield2)))
            if self.usepopfield2 == 1:
                self.dlgparameters.chkIgnoreSecond.setChecked(False)
        self.dlgparameters.cmbDistField.setCurrentIndex((self.dlgparameters.cmbDistField.findText(self.distfield)))
#        print(self.targetpoppct)
        self.dlgparameters.inpTolerance.setValue(self.targetpoppct)
        self.dlgparameters.inpTolerance_2.setValue(self.targetpop2pct)
        self.dlgparameters.inpPlanName.setText(self.planName)
        self.dockwidget.cmbGeoField.setCurrentIndex((self.dockwidget.cmbGeoField.findText(self.geofield)))

    def updateDistricts(self):
        #this associates the district ID with the district name
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
#                        QgsMessageLog.logMessage("Updating districts:")
#                        QgsMessageLog.logMessage(format(districtName))
#                        QgsMessageLog.logMessage(format(districtId))
        except:
#               do not comment out the next line, the QgsMessageLog throws the error
                QgsMessageLog.logMessage("No map loaded")


    def updateActivePlan(self):
        if self.activePlan:
            self.activePlan.layerName = self.activeLayer.name()
            self.activePlan.districts = self.districts
            self.activePlan.popfield = self.popfield
            self.activePlan.popfield2 = self.popfield2
            self.activePlan.distfield = self.distfield
            self.activePlan.geofield = self.geofield
            self.activePlan.totalpop = self.totalpop
            self.activePlan.targetpoplower = self.targetpoplower
            self.activePlan.targetpophigher = self.targetpophigher
            self.activePlan.districtId = list(districtId)
            self.activePlan.districtName = list(districtName)
            self.activePlan.name = self.planName


    def saveParameters(self):
        global districtName
        global districtId
        global dataPlanList
        self.updateDistricts()
        #layers = self.iface.legendInterface().layers()
        layers = [tree_layer.layer() for tree_layer in QgsProject.instance().layerTreeRoot().findLayers()]
        selectedLayerIndex = self.dlgparameters.cmbActiveLayer.currentIndex()
        selectedLayer = layers[selectedLayerIndex]
        self.activeLayer = selectedLayer
        self.planName = self.dlgparameters.inpPlanName.text()
        self.districts = self.dlgparameters.inpDistricts.value()
        self.activedistrict = 1
        self.dockwidget.lblActiveDistrict.setText("Active District: " + str(self.activedistrict))
        self.dockwidget.sliderDistricts.setMinimum(1)
        self.dockwidget.sliderDistricts.setMaximum(self.districts)
        self.dockwidget.sliderDistricts.setValue(1)
        self.popfield = str(self.dlgparameters.cmbPopField.currentText())
        self.popfield2 = str(self.dlgparameters.cmbPopField_2.currentText())
        
        self.usepopfield2 = 0
        self.usepopfield2tolerance = 0
        
        if self.dlgparameters.chkIgnoreSecond.isChecked() == False:
            self.usepopfield2 = 1
        if self.dlgparameters.chkIgnoreSecondTolerance.isChecked() == False:
            self.usepopfield2tolerance = 1
        
        self.distfield = self.dlgparameters.cmbDistField.currentText()
#        self.geofield = self.dockwidget.cmbGeoField.currentText()
#        self.dispfield1 = self.dlgparameters.cmbDispField1.currentText()
 #       self.dispfield2 = self.dlgparameters.cmbDispField1.currentText()

        self.totalpop = 0
        self.targetpop = 0
        for feature in self.activeLayer.getFeatures():
                self.totalpop = self.totalpop + (feature[self.popfield])
                if self.popfield2 and self.popfield2 != 'None':
                    self.totalpop2 = self.totalpop2 + (feature[self.popfield2])
        #converting this to integer makes sure we can still load the file
        self.totalpop = int(self.totalpop)
        self.totalpop2 = int(self.totalpop2) 
        self.targetpop = int(round(self.totalpop / self.districts))
        self.targetpoppct = self.dlgparameters.inpTolerance.value()
        self.targetpoppct2 = self.dlgparameters.inpTolerance_2.value()
        targetpoprem = int((self.targetpop / 100) * self.targetpoppct)
        #has_remainder will add an additional person to the top end to reflect that not all people may fall equally into precincts
        #has_remainder = 0 when the modulo is 0, since that extra person isn't needed
        has_remainder = 1
        if self.totalpop % self.districts == 0:
            has_remainder = 0
        self.targetpoplower = int(self.targetpop - targetpoprem)
        self.targetpophigher = int(self.targetpop + targetpoprem + has_remainder)
        if self.usepopfield2 == 1:
            self.targetpop2 = int(round(self.totalpop2 / self.districts))
            targetpoprem2 = int((self.targetpop2 / 100) * self.targetpoppct2)
            self.targetpop2lower = int(self.targetpop2 - targetpoprem2)
            self.targetpop2higher = int(self.targetpop2 + targetpoprem2 + has_remainder)


        self.iface.statusBarIface().showMessage( u"Variables initialised, updating front-end..." )
        QCoreApplication.processEvents()

        self.dockwidget.lblMainInfo.setText("Active Layer: " + self.activeLayer.name() + "\nActive District Field: " + self.distfield + "\nTarget Population: " + str('{:,}'.format(self.targetpop)) + " (" + str('{:,}'.format(self.targetpoplower)) + "-" + str('{:,}'.format(self.targetpophigher)) + ")")
        self.attrdockwidget.tblPop.setRowCount(self.districts+1)
        numDataFields = 0
        if self.usepopfield2 == 1:
            numDataFields = numDataFields + 3
        for d in dataFieldList:
            #if the activeplan isn't set, the following nested code avoids an error: this used to be an or boolean but it didn't quite work
            #and try/except wouldn't be more functional since the qgisRedistricterPendingField could be true even if no error is raised
            numDataFields = numDataFields + 1
            self.attrdockwidget.tblPop.setHorizontalHeaderItem(4+numDataFields,QTableWidgetItem(d.name))

        self.attrdockwidget.tblPop.setColumnCount(5+numDataFields)
        for r in range(0,self.districts+1):
                chkBoxItem = QTableWidgetItem()
                chkBoxItem.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                chkBoxItem.setCheckState(Qt.Unchecked)
                self.attrdockwidget.tblPop.setItem(r,1,chkBoxItem)
                self.attrdockwidget.tblPop.setVerticalHeaderItem(r, QTableWidgetItem(str(r)))
        self.attrdockwidget.tblPop.setHorizontalHeaderLabels(['#','Lock','Population','Deviation','Dev%'])
        numDataFields = 0
        if self.usepopfield2 == 1:
            numDataFields = numDataFields + 3
            self.attrdockwidget.tblPop.setHorizontalHeaderLabels(['#','Lock','Population','Deviation','Dev%','Pop 2','Deviation','Dev%'])
        for d in dataFieldList:
            #if the activeplan isn't set, the following nested code avoids an error: this used to be an or boolean but it didn't quite work
            #and try/except wouldn't be more functional since the qgisRedistricterPendingField could be true even if no error is raised
            numDataFields = numDataFields + 1
            if d.type == 1:
                self.attrdockwidget.tblPop.setHorizontalHeaderItem(4+numDataFields,QTableWidgetItem(d.name))
            else:
                self.attrdockwidget.tblPop.setHorizontalHeaderItem(4+numDataFields,QTableWidgetItem(d.name + '%'))

        fileDir, fileext = os.path.splitext(self.activeLayer.source())
        self.saveFileName = fileDir + '_' + self.planName + '.qgis.red'

        if len(districtName) == 0:
                self.initializeElectorates()
                
        self.updateDistricts()


        self.iface.statusBarIface().showMessage( u"Front end initialised, saving file to disk..." )
        QCoreApplication.processEvents()

#        try:
#        self.importParameters()
        
#        foundplan = 0
#        for p in dataPlanList:
#            if p.name == self.planName:
#                self.activePlan = p
#                foundplan = 1
#        if foundplan == 0:
        newPlan = redistrictingPlan()
        self.activePlan = newPlan
#            self.activePlan.name = self.planName
        self.cementDataFields()
        self.updateActivePlan()
        self.saveParametersToFile(self.saveFileName)
        self.updateFields()             # this loads the Geographic Selection Field
#        except:
#                QgsMessageLog.logMessage("Parameters file could not be saved")

        self.iface.statusBarIface().showMessage( u"File saved to disk, making final updates..." )
        QCoreApplication.processEvents()


        if self.dlgparameters.chkStyleMap.isChecked():
                self.styleMap()
                self.dlgparameters.chkStyleMap.setChecked(False)
        self.updateFieldValues()
        self.updateTable()
        self.updateLockedFields()
        
        self.iface.statusBarIface().showMessage( u"...done." )


    def styleMap(self):
                categories = []
                for cat in range(0,self.districts+1):
                        symbol = QgsSymbol.defaultSymbol(self.activeLayer.geometryType())
                        layer_style = {}
                        layer_style['color'] = '%d, %d, %d' % (randrange(0, 256), randrange(0, 256), randrange(0, 256))
                        layer_style['outline'] = '#000000'
                        if cat == 0:
                            layer_style['color'] = '204, 204, 204'
                            layer_style['opacity'] = '0.5'
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
#            QgsMessageLog.logMessage("Active District:" + str(districtName[self.activedistrict]))
            lkd = ''
            if locked[districtName[self.activedistrict]] == 1:
                lkd = ' LOCKED!'
            self.dockwidget.lblActiveDistrict.setText("Active district: " + str(districtName[self.activedistrict]) + lkd)
        except:
#           commenting out the next line borks the try:except
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
        global distPop2
#        QgsMessageLog.logMessage("Updating Field Values")
#        QgsMessageLog.logMessage(format(districtName))
#        QgsMessageLog.logMessage(format(districtId))
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
                distPop2[p] = 0
        request = QgsFeatureRequest().setFlags(QgsFeatureRequest.NoGeometry)
        for feature in self.activeLayer.getFeatures(request):
            try:
                    distPop[int(districtId[str(feature[self.distfield])])] = distPop[int(districtId[str(feature[self.distfield])])] + feature[self.popfield]
            except:
                    try:
                            distPop[0] = distPop[0] + feature[self.popfield]
                    except:
                            errors = 1
#                        QgsMessageLog.logMessage(self.distfield + " failed on load")
            if self.popfield2:
                try:
                        distPop2[int(districtId[str(feature[self.distfield])])] = distPop2[int(districtId[str(feature[self.distfield])])] + feature[self.popfield2]
                except:
                        try:
                                distPop2[0] = distPop2[0] + feature[self.popfield2]
                        except:
                                errors = 1

            for d in dataFieldList:
                    try:
                            d.field_sum[int(districtId[str(feature[self.distfield])])] = d.field_sum[int(districtId[str(feature[self.distfield])])] + (feature[d.name])
                            d.total_sum = d.total_sum + (feature[d.name])
                    except:
                            d.field_sum[0] = d.field_sum[0] + (feature[d.name])
                            d.total_sum = d.total_sum + (feature[d.name])
        gc.collect()


    def updateTable(self):
#        QgsMessageLog.logMessage("Updating Table")
        global distPop
        global distPop2
        usepopfieldflag = 0
        counter = 0
        if self.usepopfield2 == 1 and self.usepopfield2tolerance == 1:
            usepopfieldflag = 1
        for q in range(0,self.districts+1):           
            if q == 0 or (self.dockwidget.chkVisible.isChecked() == False) or (self.dockwidget.chkVisible.isChecked() == True and districtName[q] in self.visibleFeats):
                p = counter
                counter = counter + 1
                
                self.attrdockwidget.tblPop.item(p,1).setCheckState(Qt.Unchecked)
                try:
                    if locked[districtName[q]] == 1:
                        self.attrdockwidget.tblPop.item(p,1).setCheckState(Qt.Checked)
                except:
                    try:
                        locked[districtName[q]] = 0
                    except:
                        QgsMessageLog("Could not lock field")
                
                self.attrdockwidget.tblPop.setItem(p,0,QTableWidgetItem(str(districtName[q])))
                if q == 0:
                    self.attrdockwidget.tblPop.setItem(p,0,QTableWidgetItem('Unassigned'))
                if isinstance(distPop[q],int) == True:
                    self.attrdockwidget.tblPop.setItem(p,2,QTableWidgetItem(str('{:,}'.format(distPop[q]))))
                    self.attrdockwidget.tblPop.setItem(p,3,QTableWidgetItem(str('{:+,}'.format(round(distPop[q] - self.targetpop,0)))))		    
                else:
                    self.attrdockwidget.tblPop.setItem(p,2,QTableWidgetItem(str('{:,}'.format(round(distPop[q],2)))))
                    self.attrdockwidget.tblPop.setItem(p,3,QTableWidgetItem(str('{:+,}'.format(round(distPop[q] - self.targetpop,2)))))
                self.attrdockwidget.tblPop.setItem(p,4,QTableWidgetItem(str(round((float(float(distPop[q]) / float(self.targetpop)) * 100)-100,2))+'%'))
                if self.usepopfield2 == 1:
                    self.attrdockwidget.tblPop.setItem(p,5,QTableWidgetItem(str('{:+,}'.format(distPop2[q]))))
                    self.attrdockwidget.tblPop.setItem(p,6,QTableWidgetItem(str('{:+,}'.format(distPop2[q] - self.targetpop2))))
                    if self.targetpop2 > 0:
                        self.attrdockwidget.tblPop.setItem(p,7,QTableWidgetItem(str(round((float(float(distPop2[q]) / float(self.targetpop2)) * 100)-100,2))+'%'))
                    else:
                        self.attrdockwidget.tblPop.setItem(p,7,QTableWidgetItem('N/A'))
                self.attrdockwidget.tblPop.item(p,0).setBackground(self.defaultBG)
                self.attrdockwidget.tblPop.item(p,1).setBackground(self.defaultBG)
                self.attrdockwidget.tblPop.item(p,2).setBackground(self.defaultBG)
                self.attrdockwidget.tblPop.item(p,3).setBackground(self.defaultBG)
                self.attrdockwidget.tblPop.item(p,4).setBackground(self.defaultBG)
                if self.usepopfield2 == 1:
                    self.attrdockwidget.tblPop.item(p,5).setBackground(self.defaultBG)
                    self.attrdockwidget.tblPop.item(p,6).setBackground(self.defaultBG)
                    self.attrdockwidget.tblPop.item(p,7).setBackground(self.defaultBG)

                if distPop[q] >= self.targetpoplower and distPop[q] <= self.targetpophigher:
                    if usepopfieldflag == 0 or (distPop2[q] >= self.targetpop2lower and distPop2[q] <= self.targetpop2higher):
                        self.attrdockwidget.tblPop.item(p,0).setBackground(QColor(0,200,0))
                        self.attrdockwidget.tblPop.item(p,1).setBackground(QColor(0,200,0))
                        self.attrdockwidget.tblPop.item(p,2).setBackground(QColor(0,200,0))
                        self.attrdockwidget.tblPop.item(p,3).setBackground(QColor(0,200,0))
                        self.attrdockwidget.tblPop.item(p,4).setBackground(QColor(0,200,0))
                        if self.usepopfield2 == 1:
                            self.attrdockwidget.tblPop.item(p,5).setBackground(QColor(0,200,0))
                            self.attrdockwidget.tblPop.item(p,6).setBackground(QColor(0,200,0))
                            self.attrdockwidget.tblPop.item(p,7).setBackground(QColor(0,200,0))


                try:
                    attcol = QgsCategorizedSymbolRenderer.categoryIndexForLabel(str(districtName[p]))
                except:
                    self.attrdockwidget.tblPop.item(p,0).setBackground(self.defaultBG)


                rowNum = 0
                if self.usepopfield2 == 1:
                    rowNum = 3
                for d in dataFieldList:
                        rowNum = rowNum + 1
                        if d.type == 1:
                        	if isinstance(d.field_sum[q], int) == True:
	                                self.attrdockwidget.tblPop.setItem(p,4+rowNum,QTableWidgetItem(str(d.field_sum[q])))
	                        else:
	                                self.attrdockwidget.tblPop.setItem(p,4+rowNum,QTableWidgetItem(str(round(d.field_sum[q],3))))	                        
                        elif d.type == 2:
                                if distPop[p] > 0:
#                                        QgsMessageLog.logMessage(str(d.field_sum[p]) + " " + str(distPop[p]))
                                        self.attrdockwidget.tblPop.setItem(p,4+rowNum,QTableWidgetItem(str(round(float(float(d.field_sum[q]) / float(distPop[q])) * 100,2))+'%'))
                                else:
                                        self.attrdockwidget.tblPop.setItem(p,4+rowNum,QTableWidgetItem('0.00%'))
                        elif d.type == 3:
                                if self.totalpop > 0:
#                                        QgsMessageLog.logMessage(str(d.field_sum[p]) + " " + str(self.totalpop))
                                        self.attrdockwidget.tblPop.setItem(p,4+rowNum,QTableWidgetItem(str(round(float(float(d.field_sum[q]) / float(self.totalpop)) * 100,2))+'%'))
                                else:
                                        self.attrdockwidget.tblPop.setItem(p,4+rowNum,QTableWidgetItem('0.00%'))
                        elif d.type == 4:
                                if d.total_sum > 0:
#                                        QgsMessageLog.logMessage(str(d.field_sum[p]) + " " + str(d.total_sum))
                                        self.attrdockwidget.tblPop.setItem(p,4+rowNum,QTableWidgetItem(str(round(float(float(d.field_sum[q]) / float(d.total_sum)) * 100,2))+'%'))
                                else:
                                        self.attrdockwidget.tblPop.setItem(p,4+rowNum,QTableWidgetItem('0.00%'))
                        elif d.type == 5:
                                if distPop2[p] > 0:
#                                        QgsMessageLog.logMessage(str(d.field_sum[p]) + " " + str(distPop[p]))
                                        self.attrdockwidget.tblPop.setItem(p,4+rowNum,QTableWidgetItem(str(round(float(float(d.field_sum[q]) / float(distPop2[q])) * 100,2))+'%'))
                                else:
                                        self.attrdockwidget.tblPop.setItem(p,4+rowNum,QTableWidgetItem('0.00%'))


#clear non-visible rows
        rowNum = 0
        if self.usepopfield2 == 1:
            rowNum = 3
        for d in dataFieldList:
            rowNum = rowNum + 1
        for p in range(counter,self.districts+1):
           for n in range(0,5+rowNum):
               self.attrdockwidget.tblPop.setItem(p,n,QTableWidgetItem(''))
           self.attrdockwidget.tblPop.item(p,0).setBackground(self.defaultBG)
           self.attrdockwidget.tblPop.item(p,1).setBackground(self.defaultBG)
           self.attrdockwidget.tblPop.item(p,2).setBackground(self.defaultBG)
           self.attrdockwidget.tblPop.item(p,3).setBackground(self.defaultBG)
           self.attrdockwidget.tblPop.item(p,4).setBackground(self.defaultBG)
               

        self.attrdockwidget.tblPop.resizeColumnToContents(0)
        self.attrdockwidget.tblPop.resizeColumnToContents(1)
        self.attrdockwidget.tblPop.resizeColumnToContents(2)
        self.attrdockwidget.tblPop.resizeColumnToContents(3)
        self.attrdockwidget.tblPop.resizeColumnToContents(4)

        self.updateAttributeTableColours()

    def addDataField(self):
        f = DataField([self.dlgparameters.cmbDataField.currentText(),self.dlgparameters.cmbDataType.currentText(),'qgisRedistricterPendingField'])
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

    def updateAttributeTableColours(self):
        colour_dict = {}
        renderer = self.activeLayer.renderer()
        if renderer.type() == 'categorizedSymbol':
            for cat in renderer.categories():
                rgb = cat.symbol().symbolLayer(0).color()
                colour_dict[cat.value()] = rgb
            QgsMessageLog.logMessage(str(colour_dict))
            counter = 0
            for q in range(0, self.districts+1):
                if q == 0 or (self.dockwidget.chkVisible.isChecked() == False) or (self.dockwidget.chkVisible.isChecked() == True and districtName[q] in self.visibleFeats):
                    i = counter
                    counter = counter + 1
                    if str(districtName[q]) in colour_dict:
                        try:
                            self.attrdockwidget.tblPop.item(i,0).setBackground(colour_dict[str(districtName[q])])
                        except:
                            self.iface.statusBarIface().showMessage( u"Colours could not be updated on attribute table")

    def updateFieldTable(self,loadedPlan=None):
        """
        Updates the custom fields table on the parameters screen
        """
        print('updating field table')
        tblRows = 0
        planName = 'qgisRedistricterPendingField'       #works around if self.activePlan is None, ensures planName is only 'qgisRedistricterPendingField' if no active plan exists
        if self.activePlan:
            planName = self.activePlan.name            #works around if self.activePlan is None
        if loadedPlan:
            planName = loadedPlan						#this is a workaround in case someone is loading a plan from a file
        
        print(planName)
        for d in dataFieldList:
            tblRows = tblRows + 1
        self.dlgparameters.tblDataFields.setRowCount(tblRows)
        self.dlgparameters.tblDataFields.setColumnCount(2)
        tblRows = 0
        for d in dataFieldList:
                QgsMessageLog.logMessage(str(d.plan) + " " + str(planName))
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
                elif d.type == 5:
                        self.dlgparameters.tblDataFields.setItem(tblRows,1,QTableWidgetItem('% of population 2'))
                elif d.type == 99:
                        self.dlgparameters.tblDataFields.setItem(tblRows,1,QTableWidgetItem('population'))
                tblRows = tblRows + 1
        
    def updateFields(self):
        self.dlgparameters.cmbPopField.clear()
        self.dlgparameters.cmbPopField_2.clear()
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
        self.dlgparameters.cmbPopField_2.addItem('None')
        
        if hasattr(selectedLayer, 'fields'):
            fields = selectedLayer.fields()
            field_names = [field.name() for field in fields]
            self.dlgparameters.cmbPopField.addItems(field_names)
            self.dlgparameters.cmbPopField_2.addItems(field_names)
            self.dlgparameters.cmbDistField.addItems(field_names)
            self.dockwidget.cmbGeoField.addItems(field_names)
    #        self.dlgparameters.cmbDispField1.addItems(["None"])
    #        self.dlgparameters.cmbDispField2.addItems(["None"])        
            self.dlgparameters.cmbDataField.addItems(field_names)
        self.dlgparameters.cmbDataType.addItems(['Sum','% of Dist. Pop','% of Total Pop','% of Field','% of Dist. Pop 2'])
 #       self.dlgparameters.cmbDispField2.addItems(field_names)
        selectedLayerIndex = self.dlgparameters.cmbActiveLayer.currentIndex()
        selectedLayer = layers[selectedLayerIndex]
        self.dockwidget.cmbGeoField.setCurrentIndex((self.dockwidget.cmbGeoField.findText(self.geofield)))

#        loadFile = selectedLayer.source() + '.qgis.red'
#        QgsMessageLog.logMessage('loadfile: ' + loadFile)
#        if os.path.isfile(loadFile) == True:
 #               self.dlgparameters.btnLoadParameters.setEnabled(True)
  #      else:
   #             self.dlgparameters.btnLoadParameters.setEnabled(False)


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
                self.dockwidget.lblActiveDistrict.setText("Active District: " + str(districtName[self.activedistrict]))
        else:
                self.activedistrict = 0
                self.dockwidget.lblActiveDistrict.setText("Eraser Active")

    def exportToCsv(self):
        saveFileName, __ = QFileDialog.getSaveFileName(None, "Save File", "export.csv", "Comma Separated Values (*.csv)")
        if saveFileName:
            with open(saveFileName, 'w') as csvFile:
                csvWriter = csv.writer(csvFile, delimiter=',')
                headerWriter = ['id','District','Population','To Target', 'Dev%']
                for d in dataFieldList:
                        headerWriter.append(d.name)
                csvWriter.writerow(headerWriter)
                counter = 0
                for p in range(0,self.districts+1):
                        counter = counter + 1
                        rowWriter = [str(p)]
                        rowWriter.append(str(districtName[p]))
                        rowWriter.append(str("{:,}".format(distPop[p])))
                        rowWriter.append(str("{:+,}".format(distPop[p] - self.targetpop)))
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
                                elif d.type == 5:
                                        if distPop2[p] > 0:
                                                rowWriter.append(str(round(float(float(d.field_sum[p]) / float(distPop2[p])) * 100,2))+'%')
                                        else:
                                                rowWriter.append('0.00%')
                        csvWriter.writerow(rowWriter)
            self.iface.statusBarIface().showMessage( u"File saved to " + saveFileName + ". " + str(counter) + " districts exported." )
            QCoreApplication.processEvents()

                                
    def exportCrosstabToCsv(self):
        crossTabFieldName = self.dlgtoolbox.cmbCrossTab.currentText()
        saveFileName, __ = QFileDialog.getSaveFileName(None, "Save File", "crosstab.csv", "Comma Separated Values (*.csv)")

        if saveFileName:
            saveExt = os.path.splitext(saveFileName)
            if saveExt[1] == '' or saveExt[1] == None:
                 saveFileName = saveFileName + '.csv'
            self.dlgtoolbox.hide()
            self.iface.statusBarIface().showMessage( u"Creating crosstabs..." )
            QCoreApplication.processEvents()
            crosstabPop = {}
            crosstabTotalPop = {}
            #roll everything up
            """
#       Data fields are not supported yet, sorry :(
        numDataFields = 0
        for d in dataFieldList:
                del d.field_sum[:]
                for p in range(0,self.districts+1):
                        d.field_sum.append(p)
                        d.field_sum[p] = 0
                        d.total_sum = 0
                        numDataFields = numDataFields + 1
            """
            for feature in self.activeLayer.getFeatures():
                if str(feature[crossTabFieldName]) + '|' + str(feature[self.distfield]) in crosstabPop.keys():
                    crosstabPop[str(feature[crossTabFieldName]) + '|' + str(feature[self.distfield])] = crosstabPop[str(feature[crossTabFieldName]) + '|' + str(feature[self.distfield])] + feature[self.popfield]
                    crosstabTotalPop[str(feature[crossTabFieldName])] = crosstabTotalPop[str(feature[crossTabFieldName])] + feature[self.popfield]
                else:
                    crosstabPop[str(feature[crossTabFieldName]) + '|' + str(feature[self.distfield])] = feature[self.popfield]
                    if str(feature[crossTabFieldName]) in crosstabTotalPop.keys():
                        crosstabTotalPop[str(feature[crossTabFieldName])] = crosstabTotalPop[str(feature[crossTabFieldName])] + feature[self.popfield]
                    else:
                        if feature[self.popfield] == 'NULL':
                            crosstabTotalPop[str(feature[crossTabFieldName])] = ''
                        else:
                            crosstabTotalPop[str(feature[crossTabFieldName])] = feature[self.popfield]


            self.iface.statusBarIface().showMessage( u"Saving the file..." )
            QCoreApplication.processEvents()
# and then save the file
            with open(saveFileName, 'w') as csvFile:
                csvWriter = csv.writer(csvFile, delimiter=',')
                headerWriter = [str(crossTabFieldName), 'District','Population','% of ' + str(crossTabFieldName), '% of District']
#                for d in dataFieldList:
#                        headerWriter.append(d.name)
                csvWriter.writerow(headerWriter)
                for key, value in sorted(crosstabPop.items()):
                    try:
                        keySplit = key.split('|')
                        rowWriter = [keySplit[0],keySplit[1]]
                        rowWriter.append(str(value))
                        if crosstabTotalPop[keySplit[0]] > 0:
                            rowWriter.append(str(value / crosstabTotalPop[keySplit[0]]))
                        if distPop[int(districtId[keySplit[1]])] > 0:
                            rowWriter.append(str(value / distPop[int(districtId[keySplit[1]])]))

                        """
#Fields are not yet supported, sorry
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
                                elif d.type == 5:
                                        if distPop2[p] > 0:
                                                rowWriter.append(str(round(float(float(d.field_sum[p]) / float(distPop2[p])) * 100,2))+'%')
                                        else:
                                                rowWriter.append('0.00%')
                        """
                    except:
                        rowWriter = [keySplit[0],keySplit[1]]
                        rowWriter.append("error processing key")
                    csvWriter.writerow(rowWriter)
#and release the memory
            del crosstabPop
            del crosstabTotalPop
            gc.collect()
            self.iface.statusBarIface().showMessage( u"...crosstab file saved." )

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
                    if str(d) != 'NULL':
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
        districtName[-1] = 'NULL'
        districtId["NULL"] = -1
        for j in range(counter, self.districts+1):
                districtName[counter] = str(counter)
                districtId[str(counter)] = districtName[counter]
                counter = counter + 1
        QgsMessageLog.logMessage(format(districtName))
        QgsMessageLog.logMessage(format(districtId))
        self.updateActivePlan()
        self.saveParametersToFile(self.saveFileName)
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
                        districtName[counter] = str(i.strip())
                        districtId[str(i.strip())] = counter
                        counter = counter + 1
#                        QgsMessageLog.logMessage(i)
        if counter > self.districts:
                for j in range(counter, self.districts):
                        districtName[counter] = str(counter)
                        districtId[str(counter)] = counter
                        counter = counter + 1
        QgsMessageLog.logMessage('dn' + str(districtName))
        QgsMessageLog.logMessage('di' + str(districtId))
        self.updateActivePlan()
        self.saveParametersToFile(self.saveFileName)
        self.updateFieldValues()
        self.updateTable()
        self.updateLockedFields()

    def updateSelectedElectorate(self):
        QgsMessageLog.logMessage("Pick a new selected electorate from the map")
        self.dockwidget.lblActiveDistrict.setText("Click on the map...")
        self.featIdentTool =  QgsMapToolIdentifyFeature(self.canvas)
        self.featIdentTool.featureIdentified.connect(self.toolbtnSelectAction)
        self.featIdentTool.setLayer(self.activeLayer)
        self.canvas.setMapTool(self.featIdentTool)

    def selectByFloodFill(self):
        self.dlgtoolbox.hide()
        QgsMessageLog.logMessage("Select by flood fill active")
        self.featIdentTool =  QgsMapToolIdentifyFeature(self.canvas)
        self.featIdentTool.featureIdentified.connect(self.selectByFloodFillAction)
        self.featIdentTool.setLayer(self.activeLayer)
        self.canvas.setMapTool(self.featIdentTool)


    def selectByFloodFillAction(self, feature):
        field_id = self.activeLayer.fields().indexFromName(self.distfield)
        select_list = []
        select_list.append(feature)
        feature_dict = {f.id(): f for f in self.activeLayer.getFeatures()}

        if self.spatialIndex == None:
            QgsMessageLog.logMessage("Building spatial index...")
            # Build a spatial index
            # this is inefficient - should probably build this once when the layer is initialised
            self.spatialIndex = QgsSpatialIndex()
            for f in list(feature_dict.values()):
                self.spatialIndex.insertFeature(f)

        QgsMessageLog.logMessage("Finding neighbors...")
        counter = 0
        # Loop through all features and find features that touch each feature
        for f in select_list:
            counter = counter + 1
            if counter == 16385:
                break
            geom = f.geometry()
            # Find all features that intersect the bounding box of the current feature.
            # We use spatial index to find the features intersecting the bounding box
            # of the current feature. This will narrow down the features that we need
            # to check neighboring features.
            intersecting_ids = self.spatialIndex.intersects(geom.boundingBox())
            for intersecting_id in intersecting_ids:
                    # Look up the feature from the dictionary
                    intersecting_f = feature_dict[intersecting_id]
                    # QgsMessageLog.logMessage("Neighbor found!")
                    # For our purpose we consider a feature as 'neighbor' if it touches or
                    # intersects a feature. We use the 'disjoint' predicate to satisfy
                    # these conditions. So if a feature is not disjoint, it is a neighbor.
                    if (f != intersecting_f and not intersecting_f.geometry().disjoint(geom)): 
                            if intersecting_f[field_id] == feature[field_id]:
#                                    QgsMessageLog.logMessage("Neighbor found!")
                                    if intersecting_f not in select_list:
                                        select_list.append(intersecting_f)
        ids = [i.id() for i in select_list]
        self.activeLayer.select(ids)

    def selectByGeography(self):
        self.dlgtoolbox.hide()
        QgsMessageLog.logMessage("Select by geography active")
        self.featIdentTool =  QgsMapToolIdentifyFeature(self.canvas)
        self.featIdentTool.featureIdentified.connect(self.selectByGeographyAction)
        self.featIdentTool.setLayer(self.activeLayer)
        self.canvas.setMapTool(self.featIdentTool)

    def toolbtnSelectAction(self, feature):
        #QgsMessageLog.logMessage(str(feature.id()) + " updating district to " + str(feature[self.distfield]))
        self.activedistrict = feature[self.distfield]
        try:
            self.dockwidget.lblActiveDistrict.setText("Active District: " + str(districtName[self.activedistrict]))
            self.dockwidget.sliderDistricts.setValue(int(districtId[districtName[self.activedistrict]]))
        except:
            self.dockwidget.lblActiveDistrict.setText("Active District: 0")
            self.dockwidget.sliderDistricts.setValue(0)
        self.canvas.unsetMapTool(self.featIdentTool)
        self.featIdentTool = None

    def selectByGeographyAction(self, feature):
        field_id = self.activeLayer.fields().indexFromName(self.geofield)
        strExpr = "\"" + self.geofield + "\" = '" + str(feature[field_id]) + "'"
        if self.dockwidget.radGeoSelectActive.isChecked() == True:
            strExpr = strExpr + " AND \"" + self.distfield + "\" = '" + str(districtName[self.activedistrict]) + "'"
        elif self.dockwidget.radGeoSelectUnassigned.isChecked() == True:
            strExpr = strExpr + " AND (\"" + self.distfield + "\" = '0' OR \"" + self.distfield + "\" IS NULL)"

        expr = QgsExpression(strExpr)
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
        self.dockwidget.lblActiveDistrict.setText("Active District: " + str(districtName[self.activedistrict]))

    def selectByActiveDistrict(self):
        self.activeLayer.removeSelection()
        strExpr = "\"" + self.distfield + "\" = '" + str(districtName[self.activedistrict]) + "'"
        expr = QgsExpression(strExpr)
        unselected = self.activeLayer.getFeatures(QgsFeatureRequest(expr))
        ids = [i.id() for i in unselected]
        self.activeLayer.select(ids)
        if len(ids) > 0:
            box = self.activeLayer.boundingBoxOfSelected()
            self.canvas.setExtent(box)
            self.canvas.refresh()

    def selectUnassigned(self):
        """
        Selects any unassigned districts
        """
        self.dlgtoolbox.hide()
        expr = QgsExpression("\"" + self.distfield + "\"='0' OR \"" + self.distfield + "\" IS NULL")
        unselected = self.activeLayer.getFeatures(QgsFeatureRequest(expr))
        ids = [i.id() for i in unselected]
        self.activeLayer.select(ids)

    def onClosePlugin(self):
        self.dlgparameters.hide() #closingPlugin.disconnect() #self.onClosePlugin)
        self.dlgpreview.hide() #closingPlugin.disconnect() #self.onClosePlugin)
        self.dockwidget.hide() #closingPlugin.disconnect() #self.onClosePlugin)
        self.attrdockwidget.hide() #closingPlugin.disconnect() #self.onClosePlugin)
        self.dockwidget.closingPlugin.disconnect(self.onClosePlugin)
        self.pluginIsActive = False
        
    def createLabelLayer(self):
        self.dlgtoolbox.hide()
        self.iface.statusBarIface().showMessage( u"Creating/updating label layer... please wait" )
        QCoreApplication.processEvents()
        
        if self.labelLayer:
            QgsProject.instance().removeMapLayers([self.labelLayer.id()])
            self.labelLayer = None

        QCoreApplication.processEvents()


        x = {}
        y = {}
        counter = {}
        for feature in self.activeLayer.getFeatures():
            if feature[self.distfield]:
                if str(feature[self.distfield]) != '0':
                    pt = feature.geometry().centroid().asPoint()
                    if feature[self.distfield] in counter:
                        x[feature[self.distfield]] = x[feature[self.distfield]] + pt.x()
                        y[feature[self.distfield]] = y[feature[self.distfield]] + pt.y()
                        counter[feature[self.distfield]] = counter[feature[self.distfield]] + 1
                    else:
                        x[feature[self.distfield]] = pt.x()
                        y[feature[self.distfield]] = pt.y()
                        counter[feature[self.distfield]] = 1
        self.iface.statusBarIface().showMessage( u"...done with feature analysis (step 1/3)" )
        QCoreApplication.processEvents()

        
        self.labelLayer = QgsVectorLayer("Point", "tempDistrictLabels", "memory")
        pr = self.labelLayer.dataProvider()
        pr.addAttributes([QgsField("district", QVariant.String)])
        self.labelLayer.updateFields()
        
        self.iface.statusBarIface().showMessage( u"...done initialising point layer (step 2/3)" )
        QCoreApplication.processEvents()

        
        for value, key in counter.items():
            if str(value) != '0':
                try:
                    f = QgsFeature()
                    f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY((x[value] / key), (y[value] / key))))
                    f.setAttributes([str(value)])
                    pr.addFeature(f)
                except:
                    QgsMessageLog.logMessage("could not create point for key pair " + str(key) + "|" + str(value))

        lbl = QgsPalLayerSettings()
        lbl.fieldName = 'district'
        lbl.enabled = True
        
        text_format = QgsTextFormat()
        text_format.setSize(16)
        text_buffer = QgsTextBufferSettings()
        text_buffer.setEnabled(True)
        text_buffer.setSize(2.0)
        text_format.setBuffer(text_buffer)
        lbl.setFormat(text_format)
        
        
        self.labelLayer.setLabeling(QgsVectorLayerSimpleLabeling(lbl))
        self.labelLayer.setLabelsEnabled(True)

        QgsProject.instance().addMapLayer(self.labelLayer)
        self.iface.statusBarIface().showMessage( u"...done." )
        QCoreApplication.processEvents()

        
    def cementDataFields(self):
        """
        this function converts any custom fields the user has just created
        to being fields on the active redistricting plan
        """
#        print("cementing Data Fields")
        for d in dataFieldList:
            d.plan = self.planName
            print('	cemented!' + self.planName)
                
    def refreshTable(self):
        self.updateFieldValues()
        self.updateTable()
        
    def updatePanelAndSaveParameters(self):
        self.dlgparameters.hide()
        self.saveParameters()
        self.dockwidget.btnCurrentPlan.setEnabled(True)
        self.dockwidget.btnToolbox.setEnabled(True)
        self.dockwidget.btnActiveDistrictMinus.setEnabled(True)
        self.dockwidget.btnActiveDistrictPlus.setEnabled(True)
        self.dockwidget.btnEraser.setEnabled(True)
        self.dockwidget.btnFindDistrict.setEnabled(True)
        self.dockwidget.btnSelect.setEnabled(True)
        self.dockwidget.btnGeoSelect.setEnabled(True)
        self.dockwidget.btnFloodFill.setEnabled(True)
        self.dockwidget.btnPreview.setEnabled(True)
        self.dockwidget.btnUpdate.setEnabled(True)
        
    def closeParameters(self):
        self.dlgparameters.hide()
        
    def createNewDistrictField(self):
        layers = [tree_layer.layer() for tree_layer in QgsProject.instance().layerTreeRoot().findLayers()]
        selectedLayerIndex = self.dlgparameters.cmbActiveLayer.currentIndex()
        selectedLayer = layers[selectedLayerIndex]
        if hasattr(selectedLayer, 'fields'):
            fields = selectedLayer.fields()
            field_names = [field.name() for field in fields]
            fieldname = 'DISTRICT'
            if fieldname in field_names:
                for i in range(1, 100):
                    fieldstring = ('00' + str(i))
                    fieldstring = fieldstring[-2:]
                    fieldname = 'DIST' + fieldstring
                    if fieldname not in field_names:
                        break
            pr = selectedLayer.dataProvider()
            attr = pr.addAttributes([QgsField(fieldname, QVariant.String)])
            selectedLayer.updateFields()
            self.dlgparameters.cmbDistField.addItem(fieldname)
            self.dlgparameters.cmbDistField.setCurrentIndex((self.dlgparameters.cmbDistField.findText(fieldname)))

