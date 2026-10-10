"""
OptiSAR Rescue — Flood Extent Mapping Prototype
Automated flood-mapping pipeline using Google Earth Engine API across the Kaziranga AOI.
- Extracts permanent water bodies using Sentinel-2 optical bands (NDWI)
- Segments radar backscatter from Sentinel-1 SAR imagery (VV < -15 dB)
- Calculates real-world inundation metrics (~5 sq. km)
- Renders multi-layer geospatial overlays using Folium

Usage:
    python src/flood_detector.py
"""

import ee
import folium

# Initialize Earth Engine
PROJECT_ID = 'ee-optisar-test'  # Replace with your GEE Cloud Project ID if different

try:
    ee.Initialize(project=PROJECT_ID)
except Exception:
    ee.Authenticate()
    ee.Initialize(project=PROJECT_ID)

# Define Kaziranga Area of Interest (AOI)
aoi = ee.Geometry.Point([93.17, 26.58])
region = aoi.buffer(10000)  # 10 km buffer around Kaziranga

# 1. Sentinel-2 Optical Collection (Cloud-masked surface reflectance)
s2 = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
      .filterBounds(aoi)
      .filterDate('2024-06-01', '2024-08-30')
      .sort('CLOUDY_PIXEL_PERCENTAGE')
      .first())

# NDWI: (Green - NIR) / (Green + NIR) -> Bands B3 and B8
ndwi = s2.normalizedDifference(['B3', 'B8']).rename('NDWI')
optical_water = ndwi.gt(0).rename('Optical_Water')

# 2. Sentinel-1 SAR Collection (Radar: cloud-penetrating water detection)
s1 = (ee.ImageCollection('COPERNICUS/S1_GRD')
      .filterBounds(aoi)
      .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
      .filter(ee.Filter.eq('instrumentMode', 'IW'))
      .filterDate('2024-06-01', '2024-08-30')
      .first()
      .select('VV'))

sar_water = s1.lt(-15).rename('SAR_Water')

# 3. Flood Inundation Extent (SAR water excluding permanent optical water)
flood_extent = sar_water.And(optical_water.Not()).rename('Inundation_Only')

# 4. Calculate Real-World Inundation Metrics
pixel_area = ee.Image.pixelArea()
flood_area = flood_extent.multiply(pixel_area).reduceRegion(
    reducer=ee.Reducer.sum(),
    geometry=region,
    scale=10,
    maxPixels=1e9
)

area_sq_km = ee.Number(flood_area.get('Inundation_Only')).divide(1e6).round()
print(f"Calculated Flood Extent in Kaziranga: {area_sq_km.getInfo()} sq. km")

# 5. Render Interactive Multi-Layer Folium Map
def add_ee_layer(self, ee_image_object, vis_params, name):
    map_id_dict = ee.Image(ee_image_object).getMapId(vis_params)
    folium.raster_layers.TileLayer(
        tiles=map_id_dict['tile_fetcher'].url_format,
        attr='Map Data &copy; Google Earth Engine',
        name=name,
        overlay=True,
        control=True
    ).add_to(self)

folium.Map.add_ee_layer = add_ee_layer

flood_map = folium.Map(location=[26.58, 93.17], zoom_start=11)
flood_map.add_ee_layer(s2, {'bands': ['B4', 'B3', 'B2'], 'min': 0, 'max': 3000}, 'Sentinel-2 True Color')
flood_map.add_ee_layer(optical_water.selfMask(), {'palette': ['0000FF']}, 'Optical Water (NDWI)')
flood_map.add_ee_layer(sar_water.selfMask(), {'palette': ['00FFFF']}, 'SAR Water (VV < -15dB)')
flood_map.add_ee_layer(flood_extent.selfMask(), {'palette': ['FF0000']}, 'Flood Inundation Extent')
flood_map.add_child(folium.LayerControl())

output_path = 'kaziranga_flood_map.html'
flood_map.save(output_path)
print(f"Interactive Folium map saved to {output_path}")
