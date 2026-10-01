{ pkgs, postgresql ? pkgs.postgresql }:
let
  inherit (pkgs) lib;
  rev = "523e5179043a5b6ae1bbcc1990d774f23166319b";
  version = "unstable-2025-10-06";
  src = pkgs.fetchzip {
    url = "https://github.com/OpenAttackDefenseTools/tulip/archive/${rev}.tar.gz";
    hash = "sha256-NyvBTZx+LmU1VzxzYn4HbUTxCkwBH8yRWnr0/NdPRoY=";
  };
  meta = {
    description = "Traffic flow analyzer for attack/defense CTFs";
    homepage = "https://github.com/OpenAttackDefenseTools/tulip";
    license = lib.licenses.gpl3Plus;
    platforms = [ "x86_64-linux" ];
  };
  python = pkgs.python3.withPackages (ps: with ps; [
    flask flask-cors requests gunicorn python-dateutil psycopg psycopg-pool
  ]);
in rec {
  inherit src;

  importer = pkgs.buildGoModule {
    pname = "tulip-importer";
    inherit version src meta;
    modRoot = "services/go-importer";
    vendorHash = "sha256-UivOdntMHAa3/nLkSaV8u60Jfq6+9osirPuVHx0qqCs=";
    subPackages = [ "cmd/assembler" ];
    nativeBuildInputs = [ pkgs.pkg-config ];
    buildInputs = [ pkgs.libpcap ];
  };

  frontend = pkgs.stdenv.mkDerivation {
    pname = "tulip-frontend";
    inherit version src meta;
    postUnpack = ''sourceRoot="$sourceRoot/frontend"'';
    yarnOfflineCache = pkgs.fetchYarnDeps {
      yarnLock = "${src}/frontend/yarn.lock";
      hash = "sha256-dned/D4GnNrDFb7JD23Z0/+HZiRBvG4OwF0Pytf9HAo=";
    };
    nativeBuildInputs = [ pkgs.nodejs pkgs.yarnConfigHook pkgs.yarnBuildHook ];
    postPatch = ''
      # Upstream loads its font from Google; serve the pinned font locally.
      mkdir -p public/fonts
      cp ${pkgs.recursive}/share/fonts/truetype/Recursive_VF_1.085.ttf public/fonts/recursive.ttf
      substituteInPlace src/index.css \
        --replace-fail "@import url('https://fonts.googleapis.com/css2?family=Recursive:wght,MONO@300..800,0..1&display=swap');" \
        "@font-face { font-family: 'Recursive'; src: url('/fonts/recursive.ttf') format('truetype'); font-weight: 300 1000; font-display: swap; }"
    '';
    installPhase = ''
      runHook preInstall
      mkdir -p $out
      cp -r dist/. $out/
      runHook postInstall
    '';
  };

  api = pkgs.stdenvNoCC.mkDerivation {
    pname = "tulip-api";
    inherit version src meta;
    nativeBuildInputs = [ pkgs.makeWrapper ];
    dontBuild = true;
    installPhase = ''
      runHook preInstall
      mkdir -p $out/share/tulip $out/bin
      cp -r services/api $out/share/tulip/api
      # Replace the upstream example services with event-local configuration.
      cat >> $out/share/tulip/api/configurations.py <<'PY'

import json
services = json.loads(Path(os.environ["TULIP_SERVICES_FILE"]).read_text())
PY
      makeWrapper ${python}/bin/gunicorn $out/bin/tulip-api \
        --set PYTHONPATH $out/share/tulip/api \
        --add-flags "'webservice:create_app()'"
      runHook postInstall
    '';
  };

  extension = postgresql.pkgs.callPackage ({ postgresqlBuildExtension }: postgresqlBuildExtension {
    pname = "tulip-postgresql";
    inherit version src meta;
    postUnpack = ''sourceRoot="$sourceRoot/services/timescale/tulip"'';
  }) {};

  # A focused build target, also useful for inspecting binaries without a VM.
  package = pkgs.symlinkJoin {
    name = "tulip-ctf-${version}";
    paths = [ importer api ];
    passthru = { inherit frontend extension src; };
    inherit meta;
  };
}
