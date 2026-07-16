"""PlatformIO build adjustments shared by all uNode environments."""

from pathlib import Path

Import("env")


# ESP8266 Arduino 3.1.2 ships an elf2bin helper with two Python regex strings
# that Python 3.12 reports as invalid-escape SyntaxWarnings. They are harmless,
# originate outside this repository, and otherwise obscure real build warnings.
env["ENV"]["PYTHONWARNINGS"] = (
    "ignore:invalid escape sequence:SyntaxWarning"
)


# Preserve the map file used for post-mortem ESP8266 exception decoding.
map_path = Path(env.subst("$BUILD_DIR")) / "firmware.map"
env.Append(LINKFLAGS=[f"-Wl,-Map,{map_path}"])


# arduinoWebSockets 2.7.2 includes ESP8266WiFi from its own source files but
# does not declare the framework library in library.json. Add the framework
# include path explicitly so PlatformIO also exposes it while compiling that
# dependency. Using the resolved package path keeps this portable across hosts.
framework_dir = env.PioPlatform().get_package_dir(
    "framework-arduinoespressif8266"
)

if framework_dir:
    wifi_include = (
        Path(framework_dir)
        / "libraries"
        / "ESP8266WiFi"
        / "src"
    )
    env.AppendUnique(CPPPATH=[str(wifi_include)])

    # PlatformIO builds each dependency in an isolated construction
    # environment. Pass the include path specifically to WebSockets as well;
    # otherwise a top-level include path is intentionally not inherited.
    for library_builder in env.GetLibBuilders():
        if library_builder.name == "WebSockets":
            library_builder.env.AppendUnique(
                CPPPATH=[str(wifi_include)]
            )
