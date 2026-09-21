# RedNix tool group: net — scanning, sniffing, and web enumeration
{ pkgs, lib, ... }:
{
  environment.systemPackages = with pkgs; [
    nmap
    masscan
    netcat
    socat
    tcpdump
    wireshark
    mitmproxy
    ffuf
    gobuster
    sqlmap
    whatweb
    nikto
    firefox
  ];
}
