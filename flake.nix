{
  description = "Development environment for Tsumiki";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forEachSystem = nixpkgs.lib.genAttrs systems;
    in {
      devShells = forEachSystem (system:
        let
          pkgs = import nixpkgs { inherit system; };
          python = pkgs.python314;
          giPackages = with pkgs; [
            cairo
            gtk3
            gtk-layer-shell
            gobject-introspection
            libnotify
            networkmanager
            playerctl
          ];
          basePackages = with pkgs; [
            python
            uv
            pkg-config
            dart-sass
            brightnessctl
            pipewire
            power-profiles-daemon
          ];
          optionalPackages = name:
            nixpkgs.lib.optional (builtins.hasAttr name pkgs) (builtins.getAttr name pkgs);
          fontPackages = nixpkgs.lib.optional
            (builtins.hasAttr "nerd-fonts" pkgs)
            pkgs.nerd-fonts.jetbrains-mono;
        in {
          default = pkgs.mkShell {
            packages = basePackages ++ giPackages ++ nixpkgs.lib.concatMap optionalPackages [
              "wf-recorder"
              "kitty"
              "libqalculate"
              "cliphist"
              "satty"
              "nvtop"
              "gnome-bluetooth"
              "slurp"
              "imagemagick"
              "tesseract"
              "grimblast"
              "matugen"
              "cinnamon-desktop"
              "noto-fonts-color-emoji"
            ] ++ fontPackages;

            env = {
              GI_TYPELIB_PATH = pkgs.lib.makeSearchPath "lib/girepository-1.0" giPackages;
            };

            shellHook = ''
              export UV_PYTHON=${python}/bin/python
              export UV_PROJECT_ENVIRONMENT="$PWD/.venv"
            '';
          };
        });
    };
}
