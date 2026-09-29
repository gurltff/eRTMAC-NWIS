# Put real downloaded datasets here (not committed)

The loaders in `backend/loaders/` use these folders when they exist, otherwise the
sample files in `data/samples/`. After adding data, rebuild the database:
`cd backend && python -m seed.seed`.

| Folder | What to put in it | Where to get it |
|---|---|---|
| `gem/` | GEM Oil & Gas Extraction Tracker as CSV | globalenergymonitor.org or Kaggle `alialmulla97/global-oil-and-gas-extraction-tracker` |
| `volve_ddr/` | Volve daily drilling report XML files | equinor.com/energy/volve-data-sharing |
| `bhukosh/` | GSI lithology shapefiles (.shp/.dbf/.shx, WGS84) | bhukosh.gsi.gov.in (free registration) |
| `nasa_glc/` | NASA Global Landslide Catalog CSV | data.nasa.gov (h9d8-neg4) |
| `srtm/` | SRTM 30 m GeoTIFF tiles (needs `pip install rasterio`) | opentopography.org |
| `wdpa/` | WDPA protected areas for India (.shp or .geojson) | protectedplanet.net |
| `osm/` | Geofabrik India `gis_osm_landuse_a_free_1.shp` | download.geofabrik.de/asia/india.html |
