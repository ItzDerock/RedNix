# RedNix tool group: forensics — disk, image, and memory analysis
{ pkgs, lib, ... }:
{
  environment.systemPackages = with pkgs; [
    sleuthkit
    foremost
    binwalk
    exiftool
    volatility3
    testdisk
    ntfs3g
    sqlite
    recoverjpeg
    steghide
    zbar
    yara
    pngcheck
    imagemagick
  ];
}
