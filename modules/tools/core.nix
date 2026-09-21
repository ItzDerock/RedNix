# RedNix tool group: core — shell, build, and archive utilities
{ pkgs, lib, ... }:
{
  environment.systemPackages = with pkgs; [
    bashInteractive
    zsh
    starship
    tmux
    git
    python3
    python3Packages.pip
    python3Packages.requests
    python3Packages.beautifulsoup4
    python3Packages.virtualenv
    nodejs
    gcc
    clang
    gnumake
    curl
    wget
    rsync
    jq
    file
    unzip
    p7zip
    vim
    neovim
    xxd
    hexyl
    tree
    htop
    zip
  ];
}
