# qgis3redistricter
Redistricting plugin for QGIS v3. This now exists as part of the QGIS repository and can be downloaded through the QGIS Plugins library.

This plugin takes a vector layer and allows you to graphically update a "district" column, and instantly see how many people live within that district.

Full install and instructions for use are available at https://www.qgisredistricting.com

# Quick setup
You will need to provide a vector layer with a population column. Create a new project and add your vector layer to the project.

Download and install this plugin, preferably directly through the QGIS plugin library.

Start the plugin by clicking "Plan Manager" and then select "Create New Plan." A list of parameters will come up, including plan name, layer name, number of target districts, population field, population tolerance, district field, and any data fields, discussed in detail below.

Plan name: The name of your redistricting plan. Choose carefully as old plans may be overwritten if you have a plan with the same name.
Layer to district: Your target vector layer that you've loaded above
Number of districts: The target number of districts you want to create - for instance, if you are reapportioning the Victorian Legislative Assembly, which has 88 seats, this number would be 88.
Population field: The attribute column on the layer which contains the number of people represented by each polygon. (If you don't know what this is, right-click your layer and look at your vector's attribute fields. Depending on your data source, you may not have a population field, in which case you can't really redistrict with that layer.)
Equal population tolerance: Many states have an equal population threshold, where districts can have plus or minus x% of people and still be considered "equal population." Enter that number here. For maps for the United States Congress, which has a 0% variance, or to make your map where districts must be equal, leave at 0%.
Optional second population field: Works exactly the same way as the population field, designed for countries which use multiple population fields for reapportionment. If you do not need this, you may be able to use this field creatively in order to add a constraint to your map.
District field: The column with the district name or number. If you are creating a new plan, you may not have this column on your map, since you have to create it yourself. If that's the case, select "Create New Field" and the plugin will attempt to add a new field to your layer.
Data field: You can add any number of data fields to your redistricting plan, depending on what data exists on your layer's attribute table. These fields will update with the map to let you know real time statistics about your map. For instance, if you have a column on your layer with a secondary population count, such as number of non-native English speakers in the polygon, you can easily sum that information using the data field. Click on the "+" to add a field to the list.

You can automatically colour your map using the "Create map styles from districts" button.

Once you have set up your plan, all you have to do to update your plan is to select polygons on the map using the built in QGIS select tool, select the active district using the active district slider, and then click "Update Selected Polygons." Larger selections may take a few seconds to update.

One of the more valuable advanced tools worth mentioning is the geographic selection field tool. However, in order for this to work, the geography must be on the attribute table for your current redistricting layer. This may require advanced procedures such as joining other boundary files if your data set does not have this on the file.
