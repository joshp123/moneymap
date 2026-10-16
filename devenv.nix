{ pkgs, ... }: {
  packages = [
    pkgs.nodejs
    (pkgs.python3.withPackages (python: [ python.numpy python.rasterio python.fiona python.shapely python.openpyxl ]))
  ];
}
