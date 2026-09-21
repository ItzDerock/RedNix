# RedNix tool group: crypto — CTF cryptography
{ pkgs, lib, ... }:
{
  environment.systemPackages = with pkgs; [
    sage
    openssl
    python3Packages.pycryptodome
    python3Packages.pyasn1
    xortool
    # TODO(unverified): RsaCtfTool
  ];
}
