#include "dma2ray/system.hpp"

#include <cstdlib>
#include <string>

namespace dma2ray::system {

bool set_sysproxy(bool enabled, int http_port, int socks_port) {
    if (enabled) {
        std::string cmd = 
            "gsettings set org.gnome.system.proxy mode 'manual' && "
            "gsettings set org.gnome.system.proxy.http host '127.0.0.1' && "
            "gsettings set org.gnome.system.proxy.http port " + std::to_string(http_port) + " && "
            "gsettings set org.gnome.system.proxy.https host '127.0.0.1' && "
            "gsettings set org.gnome.system.proxy.https port " + std::to_string(http_port) + " && "
            "gsettings set org.gnome.system.proxy.socks host '127.0.0.1' && "
            "gsettings set org.gnome.system.proxy.socks port " + std::to_string(socks_port);
        return ::system(cmd.c_str()) == 0;
    } else {
        std::string cmd = "gsettings set org.gnome.system.proxy mode 'none'";
        return ::system(cmd.c_str()) == 0;
    }
}

bool is_sysproxy_enabled() {
    FILE* p = popen("gsettings get org.gnome.system.proxy mode 2>/dev/null", "r");
    if (!p) return false;
    char buf[64];
    std::string res;
    if (fgets(buf, sizeof(buf), p)) res = buf;
    pclose(p);
    return res.find("'manual'") != std::string::npos;
}

} // namespace dma2ray::system
