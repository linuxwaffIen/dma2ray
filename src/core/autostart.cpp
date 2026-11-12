#include "dma2ray/system.hpp"
#include "dma2ray/paths.hpp"

#include <filesystem>
#include <fstream>
#include <cstdlib>

namespace dma2ray::system {

static std::filesystem::path autostart_desktop_path() {
    const char* home = std::getenv("HOME");
    std::filesystem::path p = home ? std::filesystem::path(home) : std::filesystem::current_path();
    return p / ".config" / "autostart" / "dma2ray.desktop";
}

bool is_autostart_enabled() {
    return std::filesystem::exists(autostart_desktop_path());
}

bool set_autostart(bool enabled) {
    auto p = autostart_desktop_path();
    if (enabled) {
        std::filesystem::create_directories(p.parent_path());
        std::ofstream f(p);
        if (!f.is_open()) return false;
        f << "[Desktop Entry]\n"
          << "Type=Application\n"
          << "Name=Dma2ray\n"
          << "Exec=dma2ray\n"
          << "Icon=dma2ray\n"
          << "Terminal=false\n"
          << "Categories=Network;VPN;\n"
          << "X-GNOME-Autostart-enabled=true\n";
        return true;
    } else {
        std::error_code ec;
        std::filesystem::remove(p, ec);
        return !ec;
    }
}

} // namespace dma2ray::system
