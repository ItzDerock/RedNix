{ pkgs, ... }:
let
  fhs = pkgs.buildFHSEnv {
    name = "fhs";
    targetPkgs = pkgs: with pkgs; [
      glibc
      zlib
      openssl
      stdenv.cc.cc
      curl
      glib
      dbus
      gtk3
      gdk-pixbuf
      fontconfig
      freetype
      libx11
      libxext
      libxrender
      libxtst
      libxi
      libxcb
      ncurses
      which
    ];
    multiPkgs = pkgs: with pkgs; [
      zlib
    ];
    runScript = "bash";
  };
in
{
  environment.systemPackages = [ fhs ];
}
