{ pkgs, ... }:
{
  # Waypipe server side and xwayland-satellite (--xwls for X11 clients like
  # Burp/Ghidra) must be in the guest PATH; the client half runs on the host.
  environment.systemPackages = with pkgs; [
    waypipe
    xwayland-satellite
  ];
}
