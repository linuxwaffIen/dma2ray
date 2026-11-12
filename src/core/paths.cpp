#include "dma2ray/paths.hpp"

#include <cstdlib>
#include <sys/utsname.h>

namespace dma2ray::paths {

const std::string APP_ID = "org.dma2ray.Dma2ray";
const std::string APP_TITLE = "Dma2ray";
const std::string VERSION = "0.2.1";

static std::filesystem::path get_home() {
    const char* home = std::getenv("HOME");
    return home ? std::filesystem::path(home) : std::filesystem::current_path();
}

std::filesystem::path config_dir() {
    const char* xdg = std::getenv("XDG_CONFIG_HOME");
    if (xdg && *xdg) return std::filesystem::path(xdg) / "dma2ray";
    return get_home() / ".config" / "dma2ray";
}

std::filesystem::path cache_dir() {
    const char* xdg = std::getenv("XDG_CACHE_HOME");
    if (xdg && *xdg) return std::filesystem::path(xdg) / "dma2ray";
    return get_home() / ".cache" / "dma2ray";
}

std::filesystem::path data_dir() {
    const char* xdg = std::getenv("XDG_DATA_HOME");
    if (xdg && *xdg) return std::filesystem::path(xdg) / "dma2ray";
    return get_home() / ".local" / "share" / "dma2ray";
}

std::filesystem::path state_file() {
    return config_dir() / "state.json";
}

std::filesystem::path config_file() {
    return cache_dir() / "config.json";
}

std::filesystem::path hy_config_file() {
    return cache_dir() / "hysteria.yaml";
}

std::filesystem::path log_file() {
    return cache_dir() / "xray.log";
}

std::filesystem::path priv_socket() {
    return cache_dir() / "privileged.sock";
}

std::filesystem::path core_bin_dir() {
    return data_dir() / "bin";
}

std::string current_arch() {
    struct utsname buf;
    if (uname(&buf) == 0) {
        std::string m = buf.machine;
        for (auto& c : m) c = std::tolower(c);
        return m;
    }
    return "x86_64";
}

std::filesystem::path core_dir(const std::string& kernel_type, const std::string& arch) {
    std::string m = arch.empty() ? current_arch() : arch;
    std::string kind = kernel_type.rfind("amnezia", 0) == 0 ? "amnezia" : (kernel_type == "hysteria" ? "hysteria" : "xray");
    return core_bin_dir() / m / kind;
}

std::filesystem::path core_path(const std::string& kernel_type, const std::string& arch) {
    std::string bin_name = (kernel_type == "hysteria") ? "hysteria" : "xray";
    return core_dir(kernel_type, arch) / bin_name;
}

void ensure_dirs() {
    std::filesystem::create_directories(config_dir());
    std::filesystem::create_directories(cache_dir());
    std::filesystem::create_directories(data_dir());
    std::filesystem::create_directories(core_bin_dir());
}

} // namespace dma2ray::paths
