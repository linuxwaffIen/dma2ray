cmake_minimum_required(VERSION 3.25)
project(dma2ray_native LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

find_package(PkgConfig REQUIRED)
pkg_check_modules(GTK4 REQUIRED IMPORTED_TARGET gtk4)
pkg_check_modules(ADW REQUIRED IMPORTED_TARGET libadwaita-1)
pkg_check_modules(JSON REQUIRED IMPORTED_TARGET nlohmann_json)
pkg_check_modules(CURL REQUIRED IMPORTED_TARGET libcurl)
pkg_check_modules(OPENSSL REQUIRED IMPORTED_TARGET openssl)

include_directories(include)

set(CORE_SOURCES
    src/core/paths.cpp
    src/core/vless.cpp
    src/core/hysteria.cpp
    src/core/config.cpp
    src/core/state.cpp
    src/core/ping.cpp
    src/core/speedtest.cpp
    src/core/subscriptions.cpp
    src/core/sysproxy.cpp
    src/core/autostart.cpp
    src/core/installer.cpp
    src/core/manager.cpp
)

set(UI_SOURCES
    src/ui/theme.cpp
    src/ui/widgets.cpp
    src/ui/window.cpp
    src/ui/dialogs.cpp
    src/ui/tray.cpp
)

add_library(dma2ray_core STATIC ${CORE_SOURCES})
target_link_libraries(dma2ray_core PUBLIC
    PkgConfig::GTK4
    PkgConfig::ADW
    PkgConfig::JSON
    PkgConfig::CURL
    PkgConfig::OPENSSL
)

add_executable(dma2ray src/main.cpp ${UI_SOURCES})
target_link_libraries(dma2ray PRIVATE
    dma2ray_core
    PkgConfig::GTK4
    PkgConfig::ADW
    PkgConfig::JSON
    PkgConfig::CURL
    PkgConfig::OPENSSL
)

# Test runner in isolated sandbox
enable_testing()
add_executable(dma2ray_tests tests/cpp/test_main.cpp)
target_link_libraries(dma2ray_tests PRIVATE
    dma2ray_core
    PkgConfig::JSON
)
add_test(NAME AllTests COMMAND dma2ray_tests)
